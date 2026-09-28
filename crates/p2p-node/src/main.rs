//! `p2p_node`: prototype of the Rust Silicium node.
//!
//! Runs a libp2p swarm (TCP/QUIC, Noise, Yamux, Gossipsub, Kademlia, mDNS,
//! Identify, AutoNAT, relay server), exposes a local HTTP API (`/publish`,
//! `/tasks/{id}`, `/health`) and processes every task it receives by calling the
//! local compute daemon and reputation bridge.
//!
//! Status: prototype, not used in production. Configuration, API and known
//! limitations are documented in `crates/p2p-node/README.md`.
//!
//! Modules: [`config`] (CLI + environment), [`storage`] (identity key, task
//! book), [`swarm`] (libp2p behaviour and DHT/gossipsub publishing), [`api`]
//! (local HTTP API), [`processing`] (task execution pipeline), [`task`]
//! (network payloads).

mod api;
mod config;
mod processing;
mod storage;
mod swarm;
mod task;

use crate::{
    api::ApiState,
    config::{NodeConfig, read_hardware_bucket},
    processing::{NodeContext, process_task},
    storage::{load_or_generate_identity, load_taskbook_state},
    swarm::{
        P2pBehaviourEvent, TOPIC, build_swarm, publish_hardware_record, publish_task_record,
        publish_taskbook_event,
    },
    task::{GossipMessage, NetworkTask},
};
use futures::prelude::*;
use libp2p::{PeerId, gossipsub, identify, mdns, swarm::SwarmEvent};
use silicium_node_core::{
    beta::BetaPosterior,
    dispatch::{DispatchCandidate, Dispatcher},
    p2p::{DhtRecordEnvelope, TaskEnvelope},
    taskbook::{TaskEvent, TaskEventKind},
};
use tokio::{net::TcpListener, select, sync::mpsc};

/// Starts the node, then runs the event loop: task-book events to publish,
/// tasks queued by the API, and swarm events.
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let config = NodeConfig::from_env_and_args();
    let bootstrap_peers = config.bootstrap_peers.clone();
    let api_port = config.api_port;
    let enable_quic_listener = config.enable_quic_listener;
    let dispatcher_seed = config.dispatcher_seed;
    let data_dir = config.data_dir.clone();
    let local_key = load_or_generate_identity(&data_dir)?;
    let local_peer_id = PeerId::from(local_key.public());
    let taskbook = load_taskbook_state(&data_dir, &local_key)?;
    println!(" Local peer id: {local_peer_id}");
    println!(" Data dir: {}", data_dir.display());
    println!(" Task book: {}", taskbook.path.display());

    let (tx_events, mut rx_events) = mpsc::channel(64);

    let context = NodeContext {
        local_peer_id,
        hardware: read_hardware_bucket(),
        dispatcher_seed,
        taskbook: taskbook.clone(),
        tx_events,
    };

    let mut swarm = build_swarm(local_key.clone(), local_peer_id)?;
    let topic = gossipsub::IdentTopic::new(TOPIC);

    swarm.listen_on("/ip4/0.0.0.0/tcp/0".parse()?)?;
    if enable_quic_listener {
        let _ = swarm.listen_on("/ip4/0.0.0.0/udp/0/quic-v1".parse()?);
    }

    println!(" Silicium P2P Node running");

    for bootstrap_addr in bootstrap_peers {
        let _ = swarm.dial(bootstrap_addr);
    }

    publish_hardware_record(&mut swarm, &context);

    let (tx_publish, mut rx_publish) = mpsc::channel(32);
    let api_state = ApiState {
        tx_publish,
        taskbook: taskbook.clone(),
    };
    let app = api::router(api_state);

    let api_addr = format!("127.0.0.1:{}", api_port);
    let api_listener = TcpListener::bind(&api_addr).await?;
    println!(" API for P2P injection listening on {}", api_port); // i18n:ignore -- operator log with the bound port
    tokio::spawn(async move {
        if let Err(error) = axum::serve(api_listener, app).await {
            eprintln!("P2P API server stopped: {error}"); // i18n:ignore -- operator log with the runtime error
        }
    });

    let dispatcher = Dispatcher::with_seed(context.dispatcher_seed);
    let mut pending = Vec::<NetworkTask>::new();

    loop {
        select! {
            Some(event) = rx_events.recv() => {
                publish_taskbook_event(&mut swarm, &topic, &event);
            }
            Some(task) = rx_publish.recv() => {
                let task_envelope: TaskEnvelope = task.clone().into();
                let task_bytes = serde_json::to_vec(&task_envelope).expect("task envelope serializes");
                if let Ok(event) = taskbook.append_signed(
                    TaskEventKind::TaskProposed,
                    &task.task_id,
                    DhtRecordEnvelope::task_record_key(&task.task_id),
                    TaskEvent::payload_hash(&task_bytes),
                ) {
                    publish_taskbook_event(&mut swarm, &topic, &event);
                }
                publish_task_record(&mut swarm, &task);
                let data = serde_json::to_vec(&GossipMessage::Task(task_envelope)).unwrap();
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
                    if let Ok(gossip) = serde_json::from_slice::<GossipMessage>(&message.data) {
                        match gossip {
                            GossipMessage::TaskEvent(event) => {
                                match taskbook.append_remote(event) {
                                    Ok(hash) => println!(" Accepted task book event {hash} from {peer_id}"),
                                    Err(err) => println!(" Rejected task book event from {peer_id}: {err}"),
                                }
                            }
                            GossipMessage::Task(task_envelope) => {
                                let task: NetworkTask = task_envelope.into();
                                let context_clone = context.clone();
                                tokio::spawn(async move {
                                    process_task(context_clone, task).await;
                                });
                            }
                        }
                    } else if let Ok(task_envelope) = serde_json::from_slice::<TaskEnvelope>(&message.data) {
                        let task: NetworkTask = task_envelope.into();
                        let context_clone = context.clone();
                        tokio::spawn(async move {
                            process_task(context_clone, task).await;
                        });
                    } else {
                        println!(" Could not parse task book or NetworkTask message");
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
