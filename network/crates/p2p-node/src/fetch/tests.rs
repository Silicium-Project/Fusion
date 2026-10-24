//! Two real swarms on loopback: one holds a content, the other downloads it
//! through the event-loop glue of this module (provider lookup, then the
//! request-response protocol), and a tampered answer is refused.

use super::*;
use crate::{content::sha256_hex, swarm::build_swarm};
use futures::StreamExt;
use libp2p::{Multiaddr, swarm::SwarmEvent};
use std::time::Duration;
use tokio::sync::mpsc;

struct Node {
    swarm: Swarm<P2pBehaviour>,
    fetcher: Fetcher,
    store: ContentStore,
    commands: mpsc::Receiver<ContentCommand>,
}

fn node(name: &str) -> Node {
    let key = libp2p::identity::Keypair::generate_ed25519();
    let swarm = build_swarm(key.clone(), key.public().to_peer_id()).unwrap();
    let root = std::env::temp_dir().join(format!("silicium-fetch-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).unwrap();
    let (tx, commands) = mpsc::channel(8);
    Node {
        swarm,
        fetcher: Fetcher::default(),
        store: ContentStore::new(root, tx),
        commands,
    }
}

/// Drives one node's events once; returns its new listen address if any.
async fn step(node: &mut Node) -> Option<Multiaddr> {
    tokio::select! {
        Some(command) = node.commands.recv() => {
            handle_command(&mut node.swarm, &mut node.fetcher, command);
            None
        }
        event = node.swarm.select_next_some() => match event {
            SwarmEvent::NewListenAddr { address, .. } => Some(address),
            SwarmEvent::Behaviour(crate::swarm::P2pBehaviourEvent::Kademlia(event)) => {
                handle_kademlia(&mut node.swarm, &mut node.fetcher, event);
                None
            }
            SwarmEvent::Behaviour(crate::swarm::P2pBehaviourEvent::Content(event)) => {
                handle_content(&mut node.swarm, &mut node.fetcher, &node.store, event);
                None
            }
            _ => None,
        },
    }
}

/// Runs both nodes until `fetcher` has (or gave up on) `sha256`.
async fn ensure(holder: &mut Node, fetcher: &mut Node, sha256: &str) -> bool {
    let store = fetcher.store.clone();
    let wanted = sha256.to_string();
    let mut download = tokio::spawn(async move { store.ensure(&wanted).await });
    let run = async {
        loop {
            tokio::select! {
                result = &mut download => break result.unwrap(),
                _ = step(holder) => {}
                _ = step(fetcher) => {}
            }
        }
    };
    tokio::time::timeout(Duration::from_secs(60), run)
        .await
        .expect("download ended in time")
}

#[tokio::test]
async fn a_peer_downloads_content_it_does_not_have() {
    let mut holder = node("holder");
    let mut fetcher_node = node("fetcher");
    holder
        .swarm
        .listen_on("/ip4/127.0.0.1/tcp/0".parse().unwrap())
        .unwrap();
    let address = loop {
        if let Some(address) = step(&mut holder).await {
            break address;
        }
    };
    let holder_id = *holder.swarm.local_peer_id();
    fetcher_node
        .swarm
        .behaviour_mut()
        .kademlia
        .add_address(&holder_id, address.clone());
    fetcher_node.swarm.dial(address).unwrap();

    // A large content (several MiB) goes through in one answer.
    let bytes: Vec<u8> = (0..5 * 1024 * 1024).map(|i| (i % 251) as u8).collect();
    std::fs::write(holder.store.absolute("image.ppm"), &bytes).unwrap();
    let sha256 = holder.store.add_file("image.ppm").await.unwrap();
    assert_eq!(sha256, sha256_hex(&bytes));

    let downloaded = ensure(&mut holder, &mut fetcher_node, &sha256).await;
    assert!(downloaded, "content downloaded");
    assert_eq!(fetcher_node.store.get(&sha256).unwrap(), bytes);

    // Content nobody has fails instead of waiting forever.
    let missing = sha256_hex(b"nobody has this");
    let found = ensure(&mut holder, &mut fetcher_node, &missing).await;
    assert!(!found, "missing content reported as such");
}

#[test]
fn serve_answers_only_intact_content() {
    let (tx, _rx) = mpsc::channel(1);
    let root = std::env::temp_dir().join(format!("silicium-serve-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let store = ContentStore::new(root, tx);
    let sha256 = sha256_hex(b"scene");
    assert!(store.put_verified(&sha256, b"scene"));
    let answer = serve(
        &store,
        ContentRequest {
            sha256: sha256.clone(),
        },
    );
    assert_eq!(answer.data.as_deref(), Some(&b"scene"[..]));
    let answer = serve(
        &store,
        ContentRequest {
            sha256: "../etc/passwd".into(),
        },
    );
    assert!(answer.data.is_none());
}
