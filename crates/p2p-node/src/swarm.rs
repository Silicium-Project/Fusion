//! libp2p swarm: the network behaviour (Gossipsub, Kademlia, mDNS, Identify,
//! AutoNAT, relay server, content and model-file request-response), its construction, and the helpers that publish
//! records to the DHT and events to gossipsub.

use crate::{
    processing::NodeContext,
    task::{GossipMessage, NetworkTask},
};
use libp2p::{
    PeerId, autonat, gossipsub, identify, kad, mdns, noise, relay,
    swarm::{NetworkBehaviour, behaviour::toggle::Toggle},
    tcp, yamux,
};
use silicium_node_core::{beta::BetaPosterior, p2p::DhtRecordEnvelope, taskbook::TaskEvent};
use std::{
    collections::hash_map::DefaultHasher,
    hash::{Hash, Hasher},
    time::Duration,
};

/// Gossipsub topic shared by every Silicium node.
pub(crate) const TOPIC: &str = "silicium-network";

#[derive(NetworkBehaviour)]
pub(crate) struct P2pBehaviour {
    pub(crate) gossipsub: gossipsub::Behaviour,
    pub(crate) kademlia: kad::Behaviour<kad::store::MemoryStore>,
    pub(crate) mdns: Toggle<mdns::tokio::Behaviour>,
    pub(crate) identify: identify::Behaviour,
    pub(crate) autonat: autonat::Behaviour,
    pub(crate) relay: relay::Behaviour,
    pub(crate) content: crate::fetch::ContentBehaviour,
    pub(crate) models: crate::model_share::ModelBehaviour,
}

#[cfg(test)]
pub(crate) fn build_swarm(
    local_key: libp2p::identity::Keypair,
    local_peer_id: PeerId,
) -> Result<libp2p::Swarm<P2pBehaviour>, Box<dyn std::error::Error>> {
    build_swarm_with_mdns(local_key, local_peer_id, true)
}

pub(crate) fn build_swarm_with_mdns(
    local_key: libp2p::identity::Keypair,
    local_peer_id: PeerId,
    enable_mdns: bool,
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
            // The id covers the signed source and sequence number, not only
            // the content: a task announced again by its publisher carries
            // the same bytes and must not be dropped as a duplicate.
            let message_id_fn = |message: &gossipsub::Message| {
                let mut s = DefaultHasher::new();
                message.data.hash(&mut s);
                message.source.hash(&mut s);
                message.sequence_number.hash(&mut s);
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

            let mdns = Toggle::from(enable_mdns.then(|| {
                mdns::tokio::Behaviour::new(mdns::Config::default(), local_peer_id)
                    .expect("Valid mdns")
            }));

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
                content: crate::fetch::behaviour(),
                models: crate::model_share::behaviour(),
            }
        })?
        .with_swarm_config(|c| c.with_idle_connection_timeout(Duration::from_secs(60)))
        .build();

    let topic = gossipsub::IdentTopic::new(TOPIC);
    swarm.behaviour_mut().gossipsub.subscribe(&topic)?;

    Ok(swarm)
}

pub(crate) fn request_record_lookup(swarm: &mut libp2p::Swarm<P2pBehaviour>, key: &str) {
    let key_owned = key.to_owned();
    let record_key = kad::RecordKey::new(&key_owned);
    let query_id = swarm.behaviour_mut().kademlia.get_record(record_key);
    println!(" Requested DHT lookup for {key} ({query_id:?})");
}

pub(crate) fn record_from_envelope(envelope: &DhtRecordEnvelope) -> Option<kad::Record> {
    let key = kad::RecordKey::new(&envelope.key);
    Some(kad::Record {
        key,
        value: envelope.payload.clone(),
        publisher: None,
        expires: None,
    })
}

pub(crate) fn publish_task_record(swarm: &mut libp2p::Swarm<P2pBehaviour>, task: &NetworkTask) {
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
    request_record_lookup(swarm, &envelope.key);
}

pub(crate) fn publish_taskbook_event(
    swarm: &mut libp2p::Swarm<P2pBehaviour>,
    topic: &gossipsub::IdentTopic,
    event: &TaskEvent,
) {
    let envelope = DhtRecordEnvelope::task_event(event);
    if let Some(record) = record_from_envelope(&envelope)
        && let Err(err) = swarm
            .behaviour_mut()
            .kademlia
            .put_record(record, kad::Quorum::One)
    {
        println!(" Failed to publish task book event to DHT: {err:?}");
    }
    request_record_lookup(swarm, &envelope.key);

    let message = serde_json::to_vec(&GossipMessage::TaskEvent(event.clone()))
        .expect("task book event serializes");
    if let Err(err) = swarm
        .behaviour_mut()
        .gossipsub
        .publish(topic.clone(), message)
    {
        println!(" Failed to publish task book event to gossipsub: {err:?}");
    }
}

/// Publishes any gossip message on the topic (logs a failure).
pub(crate) fn publish_gossip(
    swarm: &mut libp2p::Swarm<P2pBehaviour>,
    topic: &gossipsub::IdentTopic,
    message: &GossipMessage,
) {
    let data = serde_json::to_vec(message).expect("gossip message serializes");
    if let Err(err) = swarm.behaviour_mut().gossipsub.publish(topic.clone(), data) {
        println!(" Failed to publish to gossipsub: {err:?}");
    }
}

pub(crate) fn publish_hardware_record(
    swarm: &mut libp2p::Swarm<P2pBehaviour>,
    context: &NodeContext,
) {
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
    request_record_lookup(swarm, &envelope.key);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::read_hardware_bucket;
    use futures::StreamExt;
    use libp2p::swarm::SwarmEvent;
    use silicium_node_core::p2p::TaskEnvelope;
    use std::collections::BTreeMap;
    use tokio::time::timeout;

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn two_local_nodes_can_exchange_kademlia_records() {
        let key_a = libp2p::identity::Keypair::generate_ed25519();
        let key_b = libp2p::identity::Keypair::generate_ed25519();
        let peer_a = PeerId::from(key_a.public());
        let peer_b = PeerId::from(key_b.public());

        let mut swarm_a = build_swarm(key_a, peer_a).expect("swarm a");
        let mut swarm_b = build_swarm(key_b, peer_b).expect("swarm b");

        swarm_b
            .listen_on("/ip4/127.0.0.1/tcp/0".parse().expect("listen addr"))
            .expect("listen on ephemeral port");
        swarm_a
            .listen_on("/ip4/127.0.0.1/tcp/0".parse().expect("listen addr"))
            .expect("listen on ephemeral port");

        let listen_addr_b = timeout(Duration::from_secs(10), async {
            loop {
                match swarm_b.next().await {
                    Some(SwarmEvent::NewListenAddr { address, .. }) => return address,
                    Some(_) => {}
                    None => panic!("swarm b terminated before advertising a listen address"),
                }
            }
        })
        .await
        .expect("timed out waiting for listen address");

        let listen_addr_a = timeout(Duration::from_secs(10), async {
            loop {
                match swarm_a.next().await {
                    Some(SwarmEvent::NewListenAddr { address, .. }) => return address,
                    Some(_) => {}
                    None => panic!("swarm a terminated before advertising a listen address"),
                }
            }
        })
        .await
        .expect("timed out waiting for listen address");

        swarm_a
            .behaviour_mut()
            .kademlia
            .add_address(&peer_b, listen_addr_b.clone());
        swarm_b
            .behaviour_mut()
            .kademlia
            .add_address(&peer_a, listen_addr_a.clone());

        swarm_a.dial(listen_addr_b.clone()).expect("dial swarm b");

        let task = NetworkTask {
            task_id: "kademlia-smoke-task".to_string(),
            root_job_id: None,
            scene_path: "scene/smoke.blend".to_string(),
            output_path: "out/smoke.ppm".to_string(),
            seed: "1337".to_string(),
            hardware_hint: Some(read_hardware_bucket()),
            runtime_hint: None,
            runtime_args: Vec::new(),
            runtime_env: BTreeMap::new(),
            runtime_workdir: None,
            runtime_module_path: None,
            runtime_image: None,
            scene_sha256: None,
            region: None,
            workload: None,
            byte_range: None,
            requested_fragment_count: None,
        };
        let task_envelope: TaskEnvelope = task.clone().into();
        let task_record = task_envelope.to_dht_record();

        let mut saw_connection_a = false;
        let mut saw_connection_b = false;
        let mut bootstrap_a_done = false;
        let mut bootstrap_b_done = false;
        timeout(Duration::from_secs(20), async {
            while !(saw_connection_a && saw_connection_b && bootstrap_a_done && bootstrap_b_done) {
                tokio::select! {
                    event = swarm_a.next() => {
                        match event {
                            Some(SwarmEvent::ConnectionEstablished { peer_id, .. }) if peer_id == peer_b => {
                                let _ = swarm_a.behaviour_mut().kademlia.bootstrap();
                                saw_connection_a = true;
                            }
                            Some(SwarmEvent::Behaviour(P2pBehaviourEvent::Kademlia(kad::Event::OutboundQueryProgressed {
                                result: kad::QueryResult::Bootstrap(Ok(_)),
                                ..
                            }))) => {
                                bootstrap_a_done = true;
                            }
                            Some(_) => {}
                            None => panic!("swarm a terminated before exchanging identify info"),
                        }
                    }
                    event = swarm_b.next() => {
                        match event {
                            Some(SwarmEvent::ConnectionEstablished { peer_id, .. }) if peer_id == peer_a => {
                                let _ = swarm_b.behaviour_mut().kademlia.bootstrap();
                                saw_connection_b = true;
                            }
                            Some(SwarmEvent::Behaviour(P2pBehaviourEvent::Kademlia(kad::Event::OutboundQueryProgressed {
                                result: kad::QueryResult::Bootstrap(Ok(_)),
                                ..
                            }))) => {
                                bootstrap_b_done = true;
                            }
                            Some(_) => {}
                            None => panic!("swarm b terminated before exchanging identify info"),
                        }
                    }
                }
            }
        })
        .await
        .expect("timed out waiting for peer connection");

        publish_task_record(&mut swarm_a, &task);
        request_record_lookup(&mut swarm_b, &task_record.key);

        let mut saw_get_record = false;
        timeout(Duration::from_secs(20), async {
            while !saw_get_record {
                tokio::select! {
                    event = swarm_a.next() => {
                        match event {
                            Some(SwarmEvent::Behaviour(P2pBehaviourEvent::Kademlia(kad::Event::OutboundQueryProgressed { result, .. }))) => {
                                if let kad::QueryResult::PutRecord(Ok(ok)) = result {
                                    println!(" swarm a put_record ok for {:?}", ok.key);
                                }
                            }
                            Some(_) => {}
                            None => panic!("swarm a terminated before kademlia query completed"),
                        }
                    }
                    event = swarm_b.next() => {
                        match event {
                            Some(SwarmEvent::Behaviour(P2pBehaviourEvent::Kademlia(kad::Event::OutboundQueryProgressed { result, .. }))) => {
                                if let kad::QueryResult::GetRecord(Ok(kad::GetRecordOk::FoundRecord(record))) = result
                                    && record.record.key.as_ref() == task_record.key.as_bytes()
                                {
                                    saw_get_record = true;
                                }
                            }
                            Some(_) => {}
                            None => panic!("swarm b terminated before kademlia query completed"),
                        }
                    }
                }
            }
        })
        .await
        .expect("timed out waiting for kademlia record retrieval");

        assert!(saw_get_record, "expected kademlia get_record to succeed");
    }
}
