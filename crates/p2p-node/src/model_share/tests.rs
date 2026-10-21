//! Pieces, serving rules, and a model file sent between two real swarms on
//! loopback (several pieces), with a wrong copy refused.

use super::*;
use crate::swarm::{P2pBehaviourEvent, build_swarm};
use libp2p::{Multiaddr, swarm::SwarmEvent};
use sha2::{Digest, Sha256};
use silicium_embedding::model::store::PinnedHash;

fn hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn temp(name: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!("silicium-models-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).unwrap();
    root
}

#[test]
fn a_file_is_cut_into_pieces() {
    let piece = u64::from(PIECE_BYTES);
    assert!(pieces(0).is_empty());
    assert_eq!(pieces(10), vec![(0, 10)]);
    assert_eq!(pieces(piece), vec![(0, PIECE_BYTES)]);
    assert_eq!(pieces(piece + 1), vec![(0, PIECE_BYTES), (piece, 1)]);
}

#[test]
fn only_store_files_are_served_and_within_bounds() {
    let root = temp("serve");
    let sha256 = hex(b"weights");
    std::fs::write(root.join(&sha256), b"weights").unwrap();
    std::fs::write(root.join("secret.txt"), b"no").unwrap();
    let ask = |name: &str, offset, length| PieceRequest {
        name: name.to_string(),
        offset,
        length,
    };
    let piece = serve(Some(&root), ask(&sha256, 2, 3));
    assert_eq!((piece.total, piece.data.as_deref()), (7, Some(&b"igh"[..])));
    for request in [
        ask("secret.txt", 0, 2),
        ask("../secret.txt", 0, 2),
        ask(&sha256, 5, 3),
        ask(&sha256, 0, PIECE_BYTES + 1),
    ] {
        assert_eq!(serve(Some(&root), request).data, None);
    }
    assert_eq!(
        serve(None, ask(&sha256, 0, 1)).data,
        None,
        "no store, nothing shared"
    );
}

#[test]
fn a_piece_must_answer_the_request() {
    let request = PieceRequest {
        name: "a".into(),
        offset: 4,
        length: 2,
    };
    let answer = |name: &str, offset, total, data: Option<&[u8]>| PieceResponse {
        name: name.into(),
        offset,
        total,
        data: data.map(<[u8]>::to_vec),
    };
    assert_eq!(
        check_piece(&request, 6, answer("a", 4, 6, Some(b"ok"))),
        Ok(b"ok".to_vec())
    );
    assert!(check_piece(&request, 6, answer("b", 4, 6, Some(b"ok"))).is_err());
    assert!(check_piece(&request, 6, answer("a", 0, 6, Some(b"ok"))).is_err());
    assert!(check_piece(&request, 6, answer("a", 4, 9, Some(b"ok"))).is_err());
    assert!(check_piece(&request, 6, answer("a", 4, 6, Some(b"o"))).is_err());
    assert!(check_piece(&request, 6, answer("a", 4, 6, None)).is_err());
}

struct Node {
    swarm: Swarm<P2pBehaviour>,
    share: ModelShare,
    root: PathBuf,
}

fn node(name: &str) -> Node {
    let key = libp2p::identity::Keypair::generate_ed25519();
    Node {
        swarm: build_swarm(key.clone(), key.public().to_peer_id()).unwrap(),
        share: ModelShare::default(),
        root: temp(name),
    }
}

/// Drives one node's swarm once; returns its new listen address if any.
async fn step(node: &mut Node) -> Option<Multiaddr> {
    match node.swarm.select_next_some().await {
        SwarmEvent::NewListenAddr { address, .. } => Some(address),
        SwarmEvent::Behaviour(P2pBehaviourEvent::Kademlia(event)) => {
            let _ = node.share.on_kademlia(&node.swarm, event);
            None
        }
        SwarmEvent::Behaviour(P2pBehaviourEvent::Models(event)) => {
            node.share
                .on_event(&mut node.swarm, Some(&node.root), event);
            None
        }
        _ => None,
    }
}

#[tokio::test]
async fn a_node_gets_a_model_file_from_a_peer() {
    let mut holder = node("holder");
    let mut getter = node("getter");
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
    getter
        .swarm
        .behaviour_mut()
        .kademlia
        .add_address(&holder_id, address.clone());
    getter.swarm.dial(address).unwrap();

    // Two and a half pieces.
    let bytes: Vec<u8> = (0..(PIECE_BYTES as usize * 5 / 2))
        .map(|i| (i % 253) as u8)
        .collect();
    let sha256 = hex(&bytes);
    std::fs::write(holder.root.join(&sha256), &bytes).unwrap();
    // A holder whose copy has another hash than the pinned one.
    let wrong = hex(b"the pinned file");
    std::fs::write(holder.root.join(&wrong), &bytes).unwrap();

    let (tx, mut commands) = mpsc::channel(64);
    connect(tx);
    let root = getter.root.clone();
    let run = async {
        let pinned = PinnedFile {
            path: "model.safetensors",
            size: bytes.len() as u64,
            hash: PinnedHash::Sha256(&sha256),
        };
        let got = download(&root, &pinned).await;
        let tampered = PinnedFile {
            path: "other.safetensors",
            size: bytes.len() as u64,
            hash: PinnedHash::Sha256(&wrong),
        };
        let refused = !download(&root, &tampered).await;
        (got, refused)
    };
    tokio::pin!(run);
    let outcome = tokio::time::timeout(Duration::from_secs(120), async {
        loop {
            tokio::select! {
                outcome = &mut run => break outcome,
                Some(command) = commands.recv() => getter.share.handle_command(&mut getter.swarm, command),
                _ = step(&mut holder) => {}
                _ = step(&mut getter) => {}
            }
        }
    })
    .await
    .expect("transfer ended in time");
    assert_eq!(outcome, (true, true));
    assert_eq!(std::fs::read(getter.root.join(&sha256)).unwrap(), bytes);
    assert!(
        !getter.root.join(&wrong).exists(),
        "a wrong copy is not kept"
    );
}
