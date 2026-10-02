//! `p2p_node`: Rust Silicium node used by the dev cutover.
//!
//! Runs a libp2p swarm (TCP/QUIC, Noise, Yamux, Gossipsub, Kademlia, mDNS,
//! Identify, AutoNAT, relay server), exposes the legacy task API plus the
//! BackEnd control API (`/v1/tasks`, `/v1/peers`, `/v1/workloads/{id}/cancel`)
//! and shares the signed task book with its peers:
//! as a worker it claims tasks and runs them once the publisher accepts it
//! ([`worker`]); as a publisher it accepts claims, announces retries and
//! finalizes results ([`publisher`]); gaps are filled over gossip ([`backfill`]).
//!
//! Configuration, API and known limitations are documented in
//! `crates/p2p-node/README.md`.
//!
//! Modules: [`config`] (CLI + environment), [`storage`] (identity key, task
//! book), [`swarm`] (libp2p behaviour and DHT/gossipsub publishing), [`api`]
//! (local HTTP API), [`worker`] / [`publisher`] / [`backfill`] (task book
//! roles), [`verifier`] (cross-peer verification), [`content`] / [`fetch`]
//! (scenes and results shared by hash), [`jobs`] / [`publishing`] (jobs
//! split into fragments, reassembled), [`processing`] (task execution),
//! [`results`] (finalized images), [`gossip`] (incoming messages),
//! [`task`] (network payloads).

mod admission;
mod api;
mod backfill;
mod compatibility;
mod config;
mod content;
mod control;
mod fetch;
mod gossip;
mod jobs;
mod processing;
mod publisher;
mod publishing;
mod results;
mod storage;
mod swarm;
mod task;
mod verifier;
mod worker;

use crate::{
    api::ApiState,
    compatibility::CompatibilityWriter,
    config::{
        NodeConfig, read_allow_self_verification_from_env, read_compute_root_from_env,
        read_hardware_bucket, read_parallel_tasks_from_env, read_verifications_required_from_env,
        read_work_own_tasks_from_env,
    },
    content::ContentStore,
    control::ControlRegistry,
    processing::NodeContext,
    storage::{load_or_generate_identity, load_taskbook_state},
    swarm::{
        P2pBehaviourEvent, TOPIC, build_swarm, publish_gossip, publish_hardware_record,
        publish_taskbook_event,
    },
    task::{GossipMessage, NetworkTask},
};
use futures::prelude::*;
use libp2p::{PeerId, gossipsub, identify, mdns, swarm::SwarmEvent};
use silicium_node_core::{
    beta::BetaPosterior,
    dispatch::{DispatchCandidate, Dispatcher},
    taskbook::TaskTerms,
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
    let (tx_content, mut rx_content) = mpsc::channel(64);

    let context = NodeContext {
        local_peer_id,
        hardware: read_hardware_bucket(),
        dispatcher_seed,
        taskbook: taskbook.clone(),
        tx_events,
        compute_timeout_s: security.compute_timeout_s,
        known_tasks: Default::default(),
        content: ContentStore::new(read_compute_root_from_env(), tx_content),
        connected_peers: Default::default(),
        compute_slots: std::sync::Arc::new(tokio::sync::Semaphore::new(
            read_parallel_tasks_from_env(),
        )),
    };
    let known_peers = std::sync::Arc::new(std::sync::Mutex::new(
        std::iter::once(local_peer_id.to_string()).collect(),
    ));
    let control = ControlRegistry::open(data_dir.join("control.tasks.json"));
    let compatibility = CompatibilityWriter::new(&local_peer_id.to_string());
    let verifier_memory = verifier::VerifierMemory::default();
    let jobs = jobs::JobStore::open(read_compute_root_from_env());
    let publish_settings = publishing::PublishSettings {
        terms: TaskTerms {
            verifications_required: read_verifications_required_from_env(),
            allow_self_verification: read_allow_self_verification_from_env(),
            ..TaskTerms::default()
        },
        jobs: jobs::JobSettings::from_env(),
        work_own_tasks: read_work_own_tasks_from_env(),
        control: control.clone(),
    };

    let mut swarm = build_swarm(local_key.clone(), local_peer_id)?;
    let topic = gossipsub::IdentTopic::new(TOPIC);

    let p2p_protocol = match config.p2p_bind {
        std::net::IpAddr::V4(_) => "ip4",
        std::net::IpAddr::V6(_) => "ip6",
    };
    let p2p_addr = format!(
        "/{p2p_protocol}/{}/tcp/{}",
        config.p2p_bind, config.p2p_port
    )
    .parse()?;
    swarm.listen_on(p2p_addr)?;
    if enable_quic_listener {
        let quic_addr = format!(
            "/{p2p_protocol}/{}/udp/{}/quic-v1",
            config.p2p_bind, config.p2p_port
        )
        .parse()?;
        let _ = swarm.listen_on(quic_addr);
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
        jobs: jobs.clone(),
        content: context.content.clone(),
        control: control.clone(),
        tx_events: context.tx_events.clone(),
        local_peer_id: local_peer_id.to_string(),
        peers: known_peers.clone(),
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
    let mut fetcher = fetch::Fetcher::default();
    let collector = results::Collector::new(jobs.clone());

    loop {
        select! {
            _ = sweep_timer.tick() => {
                context
                    .connected_peers
                    .store(swarm.connected_peers().count(), std::sync::atomic::Ordering::Relaxed);
                if let Ok(mut peers) = known_peers.lock() {
                    peers.clear();
                    peers.insert(local_peer_id.to_string());
                    peers.extend(swarm.connected_peers().map(|peer| peer.to_string()));
                }
                verifier::sweep(&context, &verifier_memory).await;
                let outcome = publisher::sweep(&taskbook, &mut regossiped, context.is_alone());
                for event in &outcome.events {
                    publish_taskbook_event(&mut swarm, &topic, event);
                }
                for task in pending.iter().filter(|task| outcome.regossip.contains(&task.task_id)) {
                    println!(" Announcing a retry of task {}", task.task_id);
                    publish_gossip(&mut swarm, &topic, &GossipMessage::Task(task.clone().into()));
                }
                pending.retain(|task| !outcome.finished.contains(&task.task_id));
                collector.collect(&context, &outcome.finished);
                if let Ok(peers) = known_peers.lock() {
                    compatibility.refresh(&control, &taskbook, &jobs, &peers);
                }
                for (author, after_sequence) in backfill::requests_for_gaps(&taskbook, &mut gap_requests) {
                    publish_gossip(&mut swarm, &topic, &GossipMessage::TaskEventsRequest { author, after_sequence });
                }
            }
            Some(event) = rx_events.recv() => {
                publish_taskbook_event(&mut swarm, &topic, &event);
            }
            Some(command) = rx_content.recv() => {
                fetch::handle_command(&mut swarm, &mut fetcher, command);
            }
            Some(task) = rx_publish.recv() => {
                let published = publishing::publish_request(
                    &mut swarm, &topic, &context, &jobs, &publish_settings, task,
                ).await;
                pending.extend(published);
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
                        swarm.behaviour_mut().kademlia.add_address(&peer_id, multiaddr.clone());
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
                    for reply in &replies {
                        publish_gossip(&mut swarm, &topic, reply);
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
                    fetch::handle_kademlia(&mut swarm, &mut fetcher, event);
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Content(event)) => {
                    fetch::handle_content(&mut swarm, &mut fetcher, &context.content, event);
                }
                _ => {}
            }
        }
    }
}
