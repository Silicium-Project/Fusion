//! `p2p_node`: prototype of the Rust Silicium node.
//!
//! Runs a libp2p swarm (TCP/QUIC, Noise, Yamux, Gossipsub, Kademlia, mDNS,
//! Identify, AutoNAT, relay server), exposes a local HTTP API (`/publish`,
//! `/tasks/{id}`, `/health`) and shares the signed task book with its peers:
//! as a worker it claims tasks and runs them once the publisher accepts it
//! ([`worker`]); as a publisher it accepts claims, announces retries and
//! finalizes results ([`publisher`]); gaps are filled over gossip ([`backfill`]).
//!
//! Status: prototype, not used in production. Configuration, API and known
//! limitations are documented in `crates/p2p-node/README.md`.
//!
//! Modules: [`config`] (CLI + environment), [`storage`] (identity key, task
//! book), [`swarm`] (libp2p behaviour and DHT/gossipsub publishing), [`api`]
//! (local HTTP API), [`worker`] / [`publisher`] / [`backfill`] (task book
//! roles), [`verifier`] (cross-peer verification), [`processing`] (task
//! execution), [`gossip`] (incoming messages),
//! [`task`] (network payloads).

mod admission;
mod api;
mod backfill;
mod config;
mod gossip;
mod processing;
mod publisher;
mod storage;
mod swarm;
mod task;
mod verifier;
mod worker;

use crate::{
    api::ApiState,
    config::{NodeConfig, read_hardware_bucket, read_verifications_required_from_env},
    processing::NodeContext,
    storage::{load_or_generate_identity, load_taskbook_state},
    swarm::{
        P2pBehaviourEvent, TOPIC, build_swarm, publish_gossip, publish_hardware_record,
        publish_task_record, publish_taskbook_event,
    },
    task::{GossipMessage, NetworkTask},
};
use futures::prelude::*;
use libp2p::{PeerId, gossipsub, identify, mdns, swarm::SwarmEvent};
use silicium_node_core::{
    beta::BetaPosterior,
    dispatch::{DispatchCandidate, Dispatcher},
    p2p::{DhtRecordEnvelope, TaskEnvelope},
    taskbook::{PayloadRef, TaskEvent, TaskEventBody, TaskTerms},
};
use std::{
    collections::{BTreeMap, BTreeSet},
    time::Duration,
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
    let security = std::sync::Arc::new(config.security.clone());
    security.check_api_exposure()?;
    if security.trusted_publishers.is_empty() && !security.accept_untrusted_tasks {
        println!(" No trusted publisher configured: tasks from other peers will be ignored"); // i18n:ignore -- operator log
    }
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
        compute_timeout_s: security.compute_timeout_s,
        known_tasks: Default::default(),
    };
    let verifier_memory = verifier::VerifierMemory::default();
    let verifications_required = read_verifications_required_from_env();

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
        security: security.clone(),
    };
    let app = api::router(api_state);

    let api_addr = std::net::SocketAddr::new(security.api_bind, api_port);
    let api_listener = TcpListener::bind(&api_addr).await?;
    println!(" API for P2P injection listening on {}", api_port); // i18n:ignore -- operator log with the bound port
    tokio::spawn(async move {
        if let Err(error) = axum::serve(api_listener, app).await {
            eprintln!("P2P API server stopped: {error}"); // i18n:ignore -- operator log with the runtime error
        }
    });

    let dispatcher = Dispatcher::with_seed(context.dispatcher_seed);
    let mut pending = Vec::<NetworkTask>::new();
    let mut sweep_timer = tokio::time::interval(Duration::from_secs(1));
    let mut regossiped = BTreeSet::new();
    let mut gap_requests = BTreeMap::new();

    loop {
        select! {
            _ = sweep_timer.tick() => {
                verifier::sweep(&context, &verifier_memory).await;
                let outcome = publisher::sweep(&taskbook, &mut regossiped);
                for event in &outcome.events {
                    publish_taskbook_event(&mut swarm, &topic, event);
                }
                for task in pending.iter().filter(|task| outcome.regossip.contains(&task.task_id)) {
                    println!(" Announcing a retry of task {}", task.task_id);
                    publish_gossip(&mut swarm, &topic, &GossipMessage::Task(task.clone().into()));
                }
                pending.retain(|task| !outcome.finished.contains(&task.task_id));
                for (author, after_sequence) in backfill::requests_for_gaps(&taskbook, &mut gap_requests) {
                    publish_gossip(&mut swarm, &topic, &GossipMessage::TaskEventsRequest { author, after_sequence });
                }
            }
            Some(event) = rx_events.recv() => {
                publish_taskbook_event(&mut swarm, &topic, &event);
            }
            Some(task) = rx_publish.recv() => {
                let task_envelope: TaskEnvelope = task.clone().into();
                let task_bytes = serde_json::to_vec(&task_envelope).expect("task envelope serializes");
                let proposal = TaskEventBody::TaskProposed {
                    spec: PayloadRef {
                        uri: DhtRecordEnvelope::task_record_key(&task.task_id),
                        sha256: TaskEvent::payload_hash(&task_bytes),
                    },
                    terms: TaskTerms { verifications_required, ..TaskTerms::default() },
                };
                match taskbook.append_signed(&task.task_id, proposal) {
                    Ok(event) => publish_taskbook_event(&mut swarm, &topic, &event),
                    Err(err) => println!(" Task book refused task {}: {err}", task.task_id),
                }
                publish_task_record(&mut swarm, &task);
                let data = serde_json::to_vec(&GossipMessage::Task(task_envelope)).unwrap();
                if let Err(e) = swarm.behaviour_mut().gossipsub.publish(topic.clone(), data) {
                    println!(" Failed to publish to gossipsub: {e:?}");
                } else {
                    println!(" Published task {} to gossipsub", task.task_id);
                }
                context.remember_task(&task);
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
                    let replies = gossip::handle(&context, &security, local_peer_id, peer_id, message);
                    for event in &replies {
                        publish_taskbook_event(&mut swarm, &topic, event);
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
