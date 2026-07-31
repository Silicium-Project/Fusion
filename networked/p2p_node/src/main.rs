use axum::{
    extract::{Json, State},
    http::StatusCode,
    response::IntoResponse,
    routing::post,
    Router,
};
use futures::prelude::*;
use libp2p::{
    autonat, gossipsub, identify, kad, mdns, noise, relay,
    swarm::{NetworkBehaviour, SwarmEvent},
    tcp, yamux, PeerId,
};
use serde::{Deserialize, Serialize};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::select;
use tokio::sync::mpsc;

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
}

// ── HTTP API for injecting tasks into P2P ────────────────────────────────────

#[derive(Clone)]
struct ApiState {
    tx_publish: mpsc::Sender<NetworkTask>,
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

// ── Gossipsub Task Processor ─────────────────────────────────────────────────

async fn process_task(peer_id: String, task: NetworkTask) {
    let client = reqwest::Client::new();
    println!("⚙️  Processing task {} from {}", task.task_id, peer_id);

    // 1. Call Compute Daemon
    let compute_payload = serde_json::json!({
        "scene_path": task.scene_path,
        "output_path": task.output_path,
        "y_start": null,
        "y_end": null,
        "x_start": null,
        "x_end": null
    });

    let compute_res = match client
        .post("http://127.0.0.1:9090/compute")
        .json(&compute_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!("❌ Compute call failed: {e}");
            return;
        }
    };

    let compute_data: serde_json::Value = match compute_res.json().await {
        Ok(d) => d,
        Err(_) => return,
    };

    let hash = match compute_data.get("hash").and_then(|v| v.as_str()) {
        Some(h) => h,
        None => {
            println!("❌ Compute failed: {:?}", compute_data);
            return;
        }
    };

    println!("✅ Compute successful. Hash: {}", hash);

    // 2. Call Verify (Compute Daemon)
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
        .post("http://127.0.0.1:9090/verify")
        .json(&verify_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!("❌ Verify call failed: {e}");
            return;
        }
    };

    let verify_data: serde_json::Value = match verify_res.json().await {
        Ok(d) => d,
        Err(_) => return,
    };

    let success = verify_data.get("verified").and_then(|v| v.as_bool()).unwrap_or(false);
    println!("✅ Verify result: {}", success);

    // 3. Call Reputation Bridge
    let observe_payload = serde_json::json!({
        "peer_id": peer_id,
        "success": success,
        "weight": 1.0
    });

    let rep_res = match client
        .post("http://127.0.0.1:9091/reputation/observe")
        .json(&observe_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!("❌ Reputation call failed: {e}");
            return;
        }
    };

    let rep_data: serde_json::Value = match rep_res.json().await {
        Ok(d) => d,
        Err(_) => return,
    };
    println!("🏅 Reputation updated: {:?}", rep_data);
}

// ── Main P2P Event Loop ──────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let local_key = libp2p::identity::Keypair::generate_ed25519();
    let local_peer_id = PeerId::from(local_key.public());
    println!("🔑 Local peer id: {local_peer_id}");

    let mut swarm = libp2p::SwarmBuilder::with_existing_identity(local_key.clone())
        .with_tokio()
        .with_tcp(
            tcp::Config::default(),
            noise::Config::new,
            yamux::Config::default,
        )?
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

    swarm.listen_on("/ip4/0.0.0.0/tcp/0".parse()?)?;

    println!("🚀 Silicium P2P Node running");

    // Start local HTTP server to inject tasks
    let (tx_publish, mut rx_publish) = mpsc::channel(32);
    let api_state = ApiState { tx_publish };
    let app = Router::new()
        .route("/publish", post(publish_task))
        .with_state(api_state);

    let api_port = std::env::var("API_PORT").unwrap_or_else(|_| "9092".to_string());
    tokio::spawn(async move {
        let addr = format!("127.0.0.1:{}", api_port);
        let listener = TcpListener::bind(&addr).await.unwrap();
        println!("📡 API for P2P injection listening on {}", api_port);
        axum::serve(listener, app).await.unwrap();
    });

    loop {
        select! {
            // Read from injection API
            Some(task) = rx_publish.recv() => {
                let data = serde_json::to_vec(&task).unwrap();
                if let Err(e) = swarm.behaviour_mut().gossipsub.publish(topic.clone(), data) {
                    println!("❌ Failed to publish to gossipsub: {e:?}");
                } else {
                    println!("📢 Published task {} to gossipsub", task.task_id);
                }
            }
            event = swarm.select_next_some() => match event {
                SwarmEvent::NewListenAddr { address, .. } => {
                    println!("📡 Listening on {address}");
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Mdns(mdns::Event::Discovered(list))) => {
                    for (peer_id, multiaddr) in list {
                        println!("✅ mDNS discovered peer: {peer_id}");
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
                    println!("📩 Received message from {peer_id}");
                    if let Ok(task) = serde_json::from_slice::<NetworkTask>(&message.data) {
                        tokio::spawn(process_task(peer_id.to_string(), task));
                    } else {
                        println!("⚠️ Could not parse message as NetworkTask");
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
                }
                _ => {}
            }
        }
    }
}
