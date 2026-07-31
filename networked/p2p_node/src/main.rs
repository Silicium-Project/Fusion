use futures::prelude::*;
use libp2p::{
    autonat, gossipsub, identify, kad, mdns, noise, relay,
    swarm::{NetworkBehaviour, SwarmEvent},
    tcp, yamux, PeerId,
};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::time::Duration;
use tokio::select;

/// Combined network behaviour for the Silicium P2P Node.
///
/// Protocols:
/// - **Gossipsub**: pub/sub message propagation (tasks, reputation)
/// - **Kademlia**: DHT-based peer discovery (WAN)
/// - **mDNS**: local network peer discovery
/// - **Identify**: peer capability exchange (needed for NAT traversal)
/// - **AutoNAT**: detects whether this node is behind NAT
/// - **Relay**: Circuit Relay v2 — allows restricted peers (mobile, NAT) to
///              connect through a relay server
#[derive(NetworkBehaviour)]
struct P2pBehaviour {
    gossipsub: gossipsub::Behaviour,
    kademlia: kad::Behaviour<kad::store::MemoryStore>,
    mdns: mdns::tokio::Behaviour,
    identify: identify::Behaviour,
    autonat: autonat::Behaviour,
    relay: relay::Behaviour,
}

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
            // — Gossipsub —
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

            // — Kademlia DHT —
            let store = kad::store::MemoryStore::new(local_peer_id);
            let mut kademlia = kad::Behaviour::new(local_peer_id, store);
            kademlia.set_mode(Some(kad::Mode::Server));

            // — mDNS —
            let mdns = mdns::tokio::Behaviour::new(mdns::Config::default(), local_peer_id)
                .expect("Valid mdns");

            // — Identify (required for AutoNAT & Relay) —
            let identify = identify::Behaviour::new(identify::Config::new(
                "/silicium/1.0.0".into(),
                key.public(),
            ));

            // — AutoNAT: detect if behind NAT —
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

            // — Circuit Relay v2: act as relay for restricted peers (mobile, NAT) —
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

    println!("🚀 Silicium P2P Node running (Gossipsub + Kademlia + mDNS + AutoNAT + Relay v2)");

    loop {
        select! {
            event = swarm.select_next_some() => match event {
                SwarmEvent::NewListenAddr { address, .. } => {
                    println!("📡 Listening on {address}");
                }
                // — mDNS peer discovery —
                SwarmEvent::Behaviour(P2pBehaviourEvent::Mdns(mdns::Event::Discovered(list))) => {
                    for (peer_id, _multiaddr) in list {
                        println!("✅ mDNS discovered peer: {peer_id}");
                        swarm.behaviour_mut().gossipsub.add_explicit_peer(&peer_id);
                    }
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Mdns(mdns::Event::Expired(list))) => {
                    for (peer_id, _multiaddr) in list {
                        println!("⏰ mDNS peer expired: {peer_id}");
                        swarm.behaviour_mut().gossipsub.remove_explicit_peer(&peer_id);
                    }
                }
                // — Gossipsub messages —
                SwarmEvent::Behaviour(P2pBehaviourEvent::Gossipsub(gossipsub::Event::Message {
                    propagation_source: peer_id,
                    message_id: id,
                    message,
                })) => {
                    println!(
                        "📩 Message '{}' [id={id}] from {peer_id}",
                        String::from_utf8_lossy(&message.data),
                    );
                }
                // — Identify: feed Kademlia with peer addresses —
                SwarmEvent::Behaviour(P2pBehaviourEvent::Identify(identify::Event::Received {
                    peer_id,
                    info,
                    ..
                })) => {
                    for addr in info.listen_addrs {
                        swarm.behaviour_mut().kademlia.add_address(&peer_id, addr);
                    }
                }
                // — AutoNAT status changes —
                SwarmEvent::Behaviour(P2pBehaviourEvent::Autonat(autonat::Event::StatusChanged {
                    old,
                    new,
                })) => {
                    println!("🔍 AutoNAT status: {old:?} → {new:?}");
                }
                // — Circuit Relay v2 events —
                SwarmEvent::Behaviour(P2pBehaviourEvent::Relay(relay::Event::ReservationReqAccepted {
                    src_peer_id,
                    ..
                })) => {
                    println!("🔗 Relay reservation accepted for {src_peer_id}");
                }
                SwarmEvent::Behaviour(P2pBehaviourEvent::Relay(relay::Event::CircuitReqAccepted {
                    src_peer_id,
                    dst_peer_id,
                })) => {
                    println!("⚡ Circuit relay: {src_peer_id} → {dst_peer_id}");
                }
                _ => {}
            }
        }
    }
}
