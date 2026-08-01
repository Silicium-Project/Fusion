use axum::{
    Router,
    extract::{Json, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
};
use futures::prelude::*;
use libp2p::{
    Multiaddr, PeerId, autonat, gossipsub, identify, kad, mdns, noise, relay,
    swarm::{NetworkBehaviour, SwarmEvent},
    tcp, yamux,
};
use serde::{Deserialize, Serialize};
use silicium_node_core::{
    beta::BetaPosterior,
    dispatch::{DispatchCandidate, Dispatcher},
    hardware::{
        GpuAcceleration, HardwareBucket, HardwareProfile, OperatingSystem, SimdWidth, VramClass,
    },
    p2p::{DhtRecordEnvelope, TaskEnvelope},
};
use std::{
    collections::BTreeMap,
    collections::hash_map::DefaultHasher,
    env, fs,
    hash::{Hash, Hasher},
    io,
    path::Path,
    path::PathBuf,
    time::Duration,
};
use tokio::{net::TcpListener, select, sync::mpsc};

#[derive(NetworkBehaviour)]
struct P2pBehaviour {
    gossipsub: gossipsub::Behaviour,
    kademlia: kad::Behaviour<kad::store::MemoryStore>,
    mdns: mdns::tokio::Behaviour,
    identify: identify::Behaviour,
    autonat: autonat::Behaviour,
    relay: relay::Behaviour,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct NetworkTask {
    task_id: String,
    scene_path: String,
    output_path: String,
    seed: String,
    #[serde(default)]
    hardware_hint: Option<HardwareBucket>,
    #[serde(default)]
    runtime_hint: Option<String>,
    #[serde(default)]
    runtime_args: Vec<String>,
    #[serde(default)]
    runtime_env: BTreeMap<String, String>,
    #[serde(default)]
    runtime_workdir: Option<PathBuf>,
    #[serde(default)]
    runtime_module_path: Option<PathBuf>,
    #[serde(default)]
    runtime_image: Option<String>,
}

impl From<TaskEnvelope> for NetworkTask {
    fn from(value: TaskEnvelope) -> Self {
        Self {
            task_id: value.task_id,
            scene_path: value.scene_path,
            output_path: value.output_path,
            seed: value.seed,
            hardware_hint: value.hardware_hint,
            runtime_hint: value.runtime_hint,
            runtime_args: value.runtime_args,
            runtime_env: value.runtime_env,
            runtime_workdir: value.runtime_workdir,
            runtime_module_path: value.runtime_module_path,
            runtime_image: value.runtime_image,
        }
    }
}

impl From<NetworkTask> for TaskEnvelope {
    fn from(value: NetworkTask) -> Self {
        Self {
            task_id: value.task_id,
            scene_path: value.scene_path,
            output_path: value.output_path,
            seed: value.seed,
            hardware_hint: value.hardware_hint,
            runtime_hint: value.runtime_hint,
            runtime_args: value.runtime_args,
            runtime_env: value.runtime_env,
            runtime_workdir: value.runtime_workdir,
            runtime_module_path: value.runtime_module_path,
            runtime_image: value.runtime_image,
        }
    }
}

impl NetworkTask {
    fn runtime_envelope(
        &self,
        peer_id: &str,
    ) -> Option<silicium_node_core::runtime::RuntimeEnvelope> {
        let task: TaskEnvelope = self.clone().into();
        task.runtime_envelope(peer_id)
    }
}

#[derive(Clone)]
struct ApiState {
    tx_publish: mpsc::Sender<NetworkTask>,
}

#[derive(Clone)]
struct NodeContext {
    local_peer_id: PeerId,
    hardware: HardwareBucket,
    dispatcher_seed: u64,
}

async fn publish_task(
    State(state): State<ApiState>,
    Json(task): Json<NetworkTask>,
) -> impl IntoResponse {
    match state.tx_publish.send(task).await {
        Ok(_) => (StatusCode::OK, "Task queued for publish").into_response(),
        Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "Channel closed").into_response(),
    }
}

async fn health() -> impl IntoResponse {
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "service": "p2p_node"})),
    )
}

fn default_hardware_profile() -> HardwareBucket {
    let profile = HardwareProfile::new(
        VramClass::Vram4096,
        GpuAcceleration {
            cuda: false,
            metal: false,
            rocm: false,
            vulkan: false,
            opencl: false,
        },
        SimdWidth::Avx2,
        OperatingSystem::Linux,
    );
    HardwareBucket::from_profile(profile)
}

fn read_hardware_bucket() -> HardwareBucket {
    env::var("SILICIUM_HW_BUCKET")
        .ok()
        .and_then(|raw| raw.parse::<u32>().ok())
        .map(HardwareBucket::new)
        .unwrap_or_else(default_hardware_profile)
}

fn read_bootstrap_peers() -> Vec<Multiaddr> {
    env::var("SILICIUM_BOOTSTRAP_PEERS")
        .ok()
        .map(|value| {
            value
                .split(',')
                .filter_map(|item| item.trim().parse::<Multiaddr>().ok())
                .collect()
        })
        .unwrap_or_default()
}

fn read_data_dir() -> PathBuf {
    env::var("SILICIUM_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/data"))
}

fn load_or_generate_identity(data_dir: &Path) -> Result<libp2p::identity::Keypair, io::Error> {
    fs::create_dir_all(data_dir)?;
    let key_path = data_dir.join("identity.key");

    if key_path.exists() {
        let bytes = fs::read(&key_path)?;
        let keypair = libp2p::identity::Keypair::from_protobuf_encoding(&bytes)
            .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;
        return Ok(keypair);
    }

    let keypair = libp2p::identity::Keypair::generate_ed25519();
    let bytes = keypair
        .to_protobuf_encoding()
        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;
    fs::write(&key_path, bytes)?;
    Ok(keypair)
}

fn record_from_envelope(envelope: &DhtRecordEnvelope) -> Option<kad::Record> {
    let key = kad::RecordKey::new(&envelope.key);
    Some(kad::Record {
        key,
        value: envelope.payload.clone(),
        publisher: None,
        expires: None,
    })
}

fn compute_score_context(context: &NodeContext, task: &NetworkTask) -> BetaPosterior {
    let task_scale = if task.task_id.is_empty() {
        1.0
    } else {
        let hardware_hint = task.hardware_hint.unwrap_or(context.hardware);
        hardware_hint.similarity(context.hardware)
    };
    BetaPosterior::with_scale_hint(task_scale)
}

async fn process_task(context: NodeContext, task: NetworkTask) {
    let client = reqwest::Client::new();
    let compute_url =
        env::var("COMPUTE_DAEMON_URL").unwrap_or_else(|_| "http://127.0.0.1:9090".to_string());
    let reputation_url =
        env::var("REPUTATION_BRIDGE_URL").unwrap_or_else(|_| "http://127.0.0.1:9091".to_string());
    println!(
        "  Processing task {} from {}",
        task.task_id, context.local_peer_id
    );

    if let Some(runtime) = task.runtime_envelope(&context.local_peer_id.to_string()) {
        let runtime_kind = runtime.kind;
        let runtime_task_id = task.task_id.clone();
        let timeout_ms = runtime.limits.cpu_timeout_ms;
        match tokio::time::timeout(
            Duration::from_millis(timeout_ms),
            tokio::task::spawn_blocking(move || runtime.execute()),
        )
        .await
        {
            Ok(join_result) => match join_result {
                Ok(Ok(outcome)) => {
                    println!(
                        " Runtime {:?} completed for {} with exit code {}",
                        runtime_kind, runtime_task_id, outcome.exit_code
                    );
                }
                Ok(Err(err)) => {
                    println!(
                        " Runtime {:?} failed for {}: {err}",
                        runtime_kind, runtime_task_id
                    );
                    return;
                }
                Err(err) => {
                    println!(" Runtime task join failed for {}: {err}", runtime_task_id);
                    return;
                }
            },
            Err(_) => {
                println!(
                    " Runtime {:?} timed out for {}",
                    runtime_kind, runtime_task_id
                );
                return;
            }
        }
    } else {
        println!(
            "  Task {} has no executable runtime payload; using compute fallback",
            task.task_id
        );
    }

    let compute_payload = serde_json::json!({
        "scene_path": task.scene_path,
        "output_path": task.output_path,
        "y_start": null,
        "y_end": null,
        "x_start": null,
        "x_end": null
    });

    let compute_res = match client
        .post(format!("{compute_url}/compute"))
        .json(&compute_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!(" Compute call failed: {e}");
            return;
        }
    };

    let compute_data: serde_json::Value = match compute_res.json().await {
        Ok(d) => d,
        Err(e) => {
            println!(" Compute response parse failed: {e}");
            return;
        }
    };

    let hash = match compute_data.get("hash").and_then(|v| v.as_str()) {
        Some(h) => h,
        None => {
            println!(" Compute failed: {:?}", compute_data);
            return;
        }
    };

    println!(" Compute successful. Hash: {}", hash);

    let verify_payload = serde_json::json!({
        "ppm_path": task.output_path,
        "manifest": {
            "milestone_count": 1,
            "milestones": [
                {
                    "index": 0,
                    "y_start": 0,
                    "y_end": 2,
                    "pixel_sha256": hash
                }
            ]
        },
        "seed": task.seed,
        "reputation": 50.0
    });

    let verify_res = match client
        .post(format!("{compute_url}/verify"))
        .json(&verify_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!(" Verify call failed: {e}");
            return;
        }
    };

    let verify_data: serde_json::Value = match verify_res.json().await {
        Ok(d) => d,
        Err(e) => {
            println!(" Verify response parse failed: {e}");
            return;
        }
    };

    let success = verify_data
        .get("verified")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    println!(" Verify result: {}", success);

    let observe_payload = serde_json::json!({
        "peer_id": context.local_peer_id.to_string(),
        "success": success,
        "weight": 1.0
    });

    let rep_res = match client
        .post(format!("{reputation_url}/reputation/observe"))
        .json(&observe_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!(" Reputation call failed: {e}");
            return;
        }
    };

    let rep_data: serde_json::Value = match rep_res.json().await {
        Ok(d) => d,
        Err(e) => {
            println!(" Reputation response parse failed: {e}");
            return;
        }
    };
    println!(" Reputation updated: {:?}", rep_data);

    let posterior = compute_score_context(&context, &task);
    let affinity_key =
        silicium_node_core::affinity::AffinityKey::new(context.hardware, task.task_id.clone());
    let affinity_record =
        silicium_node_core::affinity::AffinityRecord::new(affinity_key, posterior);
    let affinity_envelope = DhtRecordEnvelope::affinity(&affinity_record);
    println!(
        " Post-exec affinity record prepared for DHT key {}",
        affinity_envelope.key
    );
}
fn build_swarm(
    local_key: libp2p::identity::Keypair,
    local_peer_id: PeerId,
) -> Result<libp2p::Swarm<P2pBehaviour>, Box<dyn std::error::Error>> {
    let mut swarm = libp2p::SwarmBuilder::with_existing_identity(local_key.clone())
        .with_tokio()
        .with_tcp(
            tcp::Config::default(),
            noise::Config::new,
            yamux::Config::default,
        )?
        .with_quic()
        .with_behaviour(|key| {
            let message_id_fn = |message: &gossipsub::Message| {
                let mut s = DefaultHasher::new();
                message.data.hash(&mut s);
                gossipsub::MessageId::from(s.finish().to_string())
            };
            let gossipsub_config = gossipsub::ConfigBuilder::default()
                .heartbeat_interval(Duration::from_secs(1))
                .validation_mode(gossipsub::ValidationMode::Strict)
                .message_id_fn(message_id_fn)
                .build()
                .expect("Valid gossipsub config");

            let gossipsub = gossipsub::Behaviour::new(
                gossipsub::MessageAuthenticity::Signed(key.clone()),
                gossipsub_config,
            )
            .expect("Valid gossipsub config");

            let store = kad::store::MemoryStore::new(local_peer_id);
            let mut kademlia = kad::Behaviour::new(local_peer_id, store);
            kademlia.set_mode(Some(kad::Mode::Server));

            let mdns = mdns::tokio::Behaviour::new(mdns::Config::default(), local_peer_id)
                .expect("Valid mdns");

            let identify = identify::Behaviour::new(identify::Config::new(
                "/silicium/1.0.0".into(),
                key.public(),
            ));

            let autonat = autonat::Behaviour::new(
                local_peer_id,
                autonat::Config {
                    retry_interval: Duration::from_secs(90),
                    refresh_interval: Duration::from_secs(180),
                    boot_delay: Duration::from_secs(15),
                    throttle_server_period: Duration::from_secs(90),
                    ..Default::default()
                },
            );

            let relay = relay::Behaviour::new(
                local_peer_id,
                relay::Config {
                    max_reservations: 128,
                    max_circuits: 64,
                    max_circuit_duration: Duration::from_secs(600),
                    ..Default::default()
                },
            );

            P2pBehaviour {
                gossipsub,
                kademlia,
                mdns,
                identify,
                autonat,
                relay,
            }
        })?
        .with_swarm_config(|c| c.with_idle_connection_timeout(Duration::from_secs(60)))
        .build();

    let topic = gossipsub::IdentTopic::new("silicium-network");
    swarm.behaviour_mut().gossipsub.subscribe(&topic)?;

    Ok(swarm)
}

fn publish_task_record(swarm: &mut libp2p::Swarm<P2pBehaviour>, task: &NetworkTask) {
    let envelope =
        DhtRecordEnvelope::task_envelope(&task.task_id, serde_json::to_vec(task).unwrap());
    if let Some(record) = record_from_envelope(&envelope)
        && let Err(err) = swarm
            .behaviour_mut()
            .kademlia
            .put_record(record, kad::Quorum::One)
    {
        println!(" Failed to publish task record to DHT: {err:?}");
    }
}

fn publish_hardware_record(swarm: &mut libp2p::Swarm<P2pBehaviour>, context: &NodeContext) {
    let posterior = BetaPosterior::default();
    let envelope =
        DhtRecordEnvelope::hardware_score(&context.local_peer_id.to_string(), &posterior);
    if let Some(record) = record_from_envelope(&envelope)
        && let Err(err) = swarm
            .behaviour_mut()
            .kademlia
            .put_record(record, kad::Quorum::One)
    {
        println!(" Failed to publish hardware record to DHT: {err:?}");
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = read_data_dir();
    let local_key = load_or_generate_identity(&data_dir)?;
    let local_peer_id = PeerId::from(local_key.public());
    println!(" Local peer id: {local_peer_id}");
    println!(" Data dir: {}", data_dir.display());

    let context = NodeContext {
        local_peer_id,
        hardware: read_hardware_bucket(),
        dispatcher_seed: env::var("SILICIUM_DISPATCH_SEED")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(7),
    };

    let mut swarm = build_swarm(local_key.clone(), local_peer_id)?;
    let topic = gossipsub::IdentTopic::new("silicium-network");

    swarm.listen_on("/ip4/0.0.0.0/tcp/0".parse()?)?;
    if env::var("SILICIUM_ENABLE_QUIC_LISTENER").ok().as_deref() != Some("0") {
        let _ = swarm.listen_on("/ip4/0.0.0.0/udp/0/quic-v1".parse()?);
    }

    println!(" Silicium P2P Node running");

    for bootstrap_addr in read_bootstrap_peers() {
        let _ = swarm.dial(bootstrap_addr);
    }

    publish_hardware_record(&mut swarm, &context);

    let (tx_publish, mut rx_publish) = mpsc::channel(32);
    let api_state = ApiState { tx_publish };
    let app = Router::new()
        .route("/publish", post(publish_task))
        .route("/health", get(health))
        .with_state(api_state);

    let api_port = env::var("API_PORT").unwrap_or_else(|_| "9092".to_string());
    tokio::spawn(async move {
        let addr = format!("127.0.0.1:{}", api_port);
        let listener = TcpListener::bind(&addr).await.unwrap();
        println!(" API for P2P injection listening on {}", api_port);
        axum::serve(listener, app).await.unwrap();
    });

    let dispatcher = Dispatcher::with_seed(context.dispatcher_seed);
    let mut pending = Vec::<NetworkTask>::new();

    loop {
        select! {
            Some(task) = rx_publish.recv() => {
                let task_envelope: TaskEnvelope = task.clone().into();
                publish_task_record(&mut swarm, &task);
                let data = serde_json::to_vec(&task_envelope).unwrap();
                if let Err(e) = swarm.behaviour_mut().gossipsub.publish(topic.clone(), data) {
                    println!(" Failed to publish to gossipsub: {e:?}");
                } else {
                    println!(" Published task {} to gossipsub", task.task_id);
                }
                pending.push(task);
                if let Some(candidate) = pending.last() {
                    let candidate = DispatchCandidate {
                        peer_id: context.local_peer_id.to_string(),
                        hardware: context.hardware,
                        task_key: silicium_node_core::affinity::AffinityKey::new(context.hardware, candidate.task_id.clone()),
                        posterior: BetaPosterior::default(),
                    };
                    let _ = dispatcher.select(&[candidate]);
                }
            }
            event = swarm.select_next_some() => match event {
                SwarmEvent::NewListenAddr { address, .. } => {
                    println!(" Listening on {address}");
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Mdns(mdns::Event::Discovered(list))) => {
                    for (peer_id, multiaddr) in list {
                        println!(" mDNS discovered peer: {peer_id}");
                        let _ = swarm.dial(multiaddr.clone());
                        swarm.behaviour_mut().gossipsub.add_explicit_peer(&peer_id);
                    }
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Mdns(mdns::Event::Expired(list))) => {
                    for (peer_id, _multiaddr) in list {
                        swarm.behaviour_mut().gossipsub.remove_explicit_peer(&peer_id);
                    }
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Gossipsub(gossipsub::Event::Message {
                    propagation_source: peer_id,
                    message,
                    ..
                })) => {
                    println!(" Received message from {peer_id}");
                    if let Ok(task_envelope) = serde_json::from_slice::<TaskEnvelope>(&message.data) {
                        let task: NetworkTask = task_envelope.into();
                        let context_clone = context.clone();
                        tokio::spawn(async move {
                            process_task(context_clone, task).await;
                        });
                    } else {
                        println!(" Could not parse message as NetworkTask");
                    }
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Identify(identify::Event::Received {
                    peer_id,
                    info,
                    ..
                })) => {
                    for addr in info.listen_addrs {
                        swarm.behaviour_mut().kademlia.add_address(&peer_id, addr);
                    }
                    let _ = swarm.behaviour_mut().kademlia.bootstrap();
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Kademlia(event)) => {
                    println!(" Kademlia event: {event:?}");
                }
                _ => {}
            }
        }
    }
}
