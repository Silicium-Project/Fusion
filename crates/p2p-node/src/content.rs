//! Content-addressed store shared with peers: scenes and result images are
//! kept as `content/<sha256>` inside the compute daemon's work directory (so
//! the daemon can read a scene at that path), announced in the DHT, and
//! served to peers that ask for them (see [`crate::fetch`]).

use sha2::{Digest, Sha256};
use std::{fs, path::PathBuf};
use tokio::sync::{mpsc, oneshot};

/// Largest content a node stores or sends (a full-HD PPM is ~6 MiB).
pub(crate) const MAX_CONTENT_BYTES: usize = 64 * 1024 * 1024;

/// Requests from the node's tasks to the event loop, which owns the swarm.
pub(crate) enum ContentCommand {
    /// Find a peer holding `sha256`, download it, answer once stored.
    Fetch {
        sha256: String,
        reply: oneshot::Sender<bool>,
    },
    /// Announce in the DHT that this node holds `sha256`.
    Provide { sha256: String },
}

/// Content-addressed store inside the compute daemon's work directory.
#[derive(Clone)]
pub(crate) struct ContentStore {
    root: PathBuf,
    commands: mpsc::Sender<ContentCommand>,
}

impl ContentStore {
    pub(crate) fn new(root: PathBuf, commands: mpsc::Sender<ContentCommand>) -> Self {
        Self { root, commands }
    }

    /// Path of a content relative to the work directory (what tasks carry).
    pub(crate) fn relative_path(sha256: &str) -> String {
        format!("content/{sha256}")
    }

    /// Absolute path of a file given relative to the work directory.
    pub(crate) fn absolute(&self, relative: &str) -> PathBuf {
        self.root.join(relative)
    }

    /// Copies the file at `relative` into the store, announces it, and
    /// returns its hash.
    pub(crate) async fn add_file(&self, relative: &str) -> Result<String, String> {
        let bytes =
            fs::read(self.absolute(relative)).map_err(|err| format!("unreadable: {err}"))?;
        self.add_bytes(&bytes).await
    }

    /// Imports a BackEnd-uploaded file whose path is outside the compute root.
    /// The path is read once and never sent to peers; only the resulting
    /// content hash is carried in the signed task envelope.
    pub(crate) async fn add_external_file(&self, path: &std::path::Path) -> Result<String, String> {
        let bytes = fs::read(path).map_err(|err| format!("unreadable: {err}"))?;
        self.add_bytes(&bytes).await
    }

    async fn add_bytes(&self, bytes: &[u8]) -> Result<String, String> {
        if bytes.len() > MAX_CONTENT_BYTES {
            return Err(format!("larger than {MAX_CONTENT_BYTES} bytes"));
        }
        let sha256 = sha256_hex(bytes);
        self.write(&sha256, bytes)?;
        let _ = self
            .commands
            .send(ContentCommand::Provide {
                sha256: sha256.clone(),
            })
            .await;
        Ok(sha256)
    }

    /// Bytes of a stored content, when present and intact.
    pub(crate) fn get(&self, sha256: &str) -> Option<Vec<u8>> {
        if !is_sha256(sha256) {
            return None;
        }
        let bytes = fs::read(self.absolute(&Self::relative_path(sha256))).ok()?;
        (sha256_hex(&bytes) == sha256).then_some(bytes)
    }

    /// True when the content is stored and intact.
    pub(crate) fn has(&self, sha256: &str) -> bool {
        self.get(sha256).is_some()
    }

    /// Stores downloaded bytes when they hash to `sha256` (and announces them).
    pub(crate) fn put_verified(&self, sha256: &str, bytes: &[u8]) -> bool {
        bytes.len() <= MAX_CONTENT_BYTES
            && is_sha256(sha256)
            && sha256_hex(bytes) == sha256
            && self.write(sha256, bytes).is_ok()
    }

    /// Makes sure `sha256` is stored locally, downloading it from a peer
    /// if needed; false when no peer delivered it in time.
    pub(crate) async fn ensure(&self, sha256: &str) -> bool {
        if self.has(sha256) {
            return true;
        }
        let (reply, answer) = oneshot::channel();
        let command = ContentCommand::Fetch {
            sha256: sha256.to_string(),
            reply,
        };
        if self.commands.send(command).await.is_err() {
            return false;
        }
        matches!(
            tokio::time::timeout(std::time::Duration::from_secs(120), answer).await,
            Ok(Ok(true))
        ) && self.has(sha256)
    }

    fn write(&self, sha256: &str, bytes: &[u8]) -> Result<(), String> {
        let path = self.absolute(&Self::relative_path(sha256));
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|err| err.to_string())?;
        }
        // Write then rename, so a reader never sees a half-written file.
        let partial = path.with_extension("partial");
        fs::write(&partial, bytes).map_err(|err| err.to_string())?;
        #[cfg(windows)]
        if path.exists() {
            fs::remove_file(&path).map_err(|err| err.to_string())?;
        }
        fs::rename(&partial, &path).map_err(|err| err.to_string())
    }
}

pub(crate) fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub(crate) fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store(name: &str) -> (ContentStore, mpsc::Receiver<ContentCommand>) {
        let root =
            std::env::temp_dir().join(format!("silicium-content-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let (tx, rx) = mpsc::channel(8);
        (ContentStore::new(root, tx), rx)
    }

    #[tokio::test]
    async fn added_files_are_announced_and_downloads_are_checked() {
        let (publisher, mut announced) = store("pub");
        fs::write(publisher.absolute("demo.cfg"), b"camera : {}").unwrap();
        let sha256 = publisher.add_file("demo.cfg").await.unwrap();
        assert!(
            matches!(announced.recv().await, Some(ContentCommand::Provide { sha256: s }) if s == sha256)
        );
        let bytes = publisher.get(&sha256).unwrap();

        let (worker, _commands) = store("worker");
        assert!(!worker.put_verified(&sha256, b"tampered"));
        assert!(worker.put_verified(&sha256, &bytes));
        assert!(worker.ensure(&sha256).await, "already stored: no download");
    }
}
