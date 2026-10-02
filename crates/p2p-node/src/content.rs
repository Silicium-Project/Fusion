//! Content transfer between peers, addressed by SHA-256: the publisher stores
//! a copy of each task's scene under `scenes/<sha256>.cfg` in the compute
//! work directory and announces its hash in the task; a peer that lacks it
//! asks the topic (`ContentRequest`) and any holder answers
//! (`ContentResponse`). Received bytes are kept only when this node asked for
//! them and they hash to the requested value.
//!
//! Content travels inside gossip messages, so it is capped at
//! [`MAX_CONTENT_BYTES`] (scenes are small text files).

use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    path::PathBuf,
    sync::{Arc, Mutex},
};

/// Largest content exchanged over gossip (hex doubles it on the wire, which
/// must stay under gossipsub's 64 KiB message limit).
pub(crate) const MAX_CONTENT_BYTES: usize = 24 * 1024;

/// Content-addressed scene store inside the compute daemon's work directory.
#[derive(Clone)]
pub(crate) struct ContentStore {
    root: PathBuf,
    wanted: Arc<Mutex<BTreeSet<String>>>,
}

impl ContentStore {
    pub(crate) fn new(root: PathBuf) -> Self {
        Self {
            root,
            wanted: Arc::default(),
        }
    }

    /// Path of a scene relative to the work directory (what tasks carry).
    pub(crate) fn scene_path(sha256: &str) -> String {
        format!("scenes/{sha256}.cfg")
    }

    /// Absolute path of a file given relative to the work directory.
    pub(crate) fn absolute(&self, relative: &str) -> PathBuf {
        self.root.join(relative)
    }

    /// Stores the scene at `relative` (publisher side) and returns its hash
    /// and its content-addressed path.
    pub(crate) fn add_scene(&self, relative: &str) -> Result<(String, String), String> {
        let bytes =
            fs::read(self.absolute(relative)).map_err(|err| format!("scene unreadable: {err}"))?;
        if bytes.len() > MAX_CONTENT_BYTES {
            return Err(format!("scene larger than {MAX_CONTENT_BYTES} bytes"));
        }
        let sha256 = sha256_hex(&bytes);
        self.write(&sha256, &bytes)?;
        Ok((sha256.clone(), Self::scene_path(&sha256)))
    }

    /// Bytes of a stored scene, when present and intact.
    pub(crate) fn get(&self, sha256: &str) -> Option<Vec<u8>> {
        if !is_sha256(sha256) {
            return None;
        }
        let bytes = fs::read(self.absolute(&Self::scene_path(sha256))).ok()?;
        (sha256_hex(&bytes) == sha256).then_some(bytes)
    }

    /// Marks a hash as requested by this node.
    pub(crate) fn want(&self, sha256: &str) {
        if let Ok(mut wanted) = self.wanted.lock() {
            wanted.insert(sha256.to_string());
        }
    }

    /// Stores received bytes if this node asked for them and they match.
    pub(crate) fn receive(&self, sha256: &str, bytes: &[u8]) -> bool {
        let asked = self
            .wanted
            .lock()
            .map(|mut wanted| wanted.remove(sha256))
            .unwrap_or(false);
        asked
            && bytes.len() <= MAX_CONTENT_BYTES
            && sha256_hex(bytes) == sha256
            && self.write(sha256, bytes).is_ok()
    }

    fn write(&self, sha256: &str, bytes: &[u8]) -> Result<(), String> {
        let path = self.absolute(&Self::scene_path(sha256));
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|err| err.to_string())?;
        }
        fs::write(path, bytes).map_err(|err| err.to_string())
    }
}

pub(crate) fn sha256_hex(bytes: &[u8]) -> String {
    hex_encode(&Sha256::digest(bytes))
}

pub(crate) fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// Lowercase hex of `bytes` (content is sent as hex in JSON gossip).
pub(crate) fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// Inverse of [`hex_encode`]; `None` on odd length or invalid digits.
pub(crate) fn hex_decode(text: &str) -> Option<Vec<u8>> {
    if !text.len().is_multiple_of(2) {
        return None;
    }
    (0..text.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(text.get(index..index + 2)?, 16).ok())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store(name: &str) -> ContentStore {
        let root =
            std::env::temp_dir().join(format!("silicium-content-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        ContentStore::new(root)
    }

    #[test]
    fn a_published_scene_can_be_served_and_received_elsewhere() {
        let publisher = store("pub");
        fs::write(publisher.absolute("demo.cfg"), b"camera : {}").unwrap();
        let (sha256, path) = publisher.add_scene("demo.cfg").unwrap();
        assert_eq!(path, format!("scenes/{sha256}.cfg"));
        let served = publisher.get(&sha256).unwrap();

        let worker = store("worker");
        assert!(
            !worker.receive(&sha256, &served),
            "unsolicited content is dropped"
        );
        worker.want(&sha256);
        assert!(!worker.receive(&sha256, b"tampered"));
        worker.want(&sha256);
        assert!(worker.receive(&sha256, &served));
        assert_eq!(worker.get(&sha256).unwrap(), served);
    }

    #[test]
    fn hex_round_trips_and_rejects_garbage() {
        assert_eq!(
            hex_decode(&hex_encode(&[0, 15, 255])).unwrap(),
            vec![0, 15, 255]
        );
        assert!(hex_decode("abc").is_none());
        assert!(hex_decode("zz").is_none());
    }

    #[test]
    fn oversized_scenes_are_refused() {
        let publisher = store("big");
        fs::write(
            publisher.absolute("big.cfg"),
            vec![b'x'; MAX_CONTENT_BYTES + 1],
        )
        .unwrap();
        assert!(publisher.add_scene("big.cfg").is_err());
    }
}
