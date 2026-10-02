//! On-disk node state under the data directory: the libp2p identity key and
//! the signed task book (`taskbook.events.jsonl`).

use ed25519_dalek::SigningKey;
use sha2::{Digest, Sha256};
use silicium_node_core::taskbook::{
    DerivedTaskState, EventHeader, Received, TaskBook, TaskBookError, TaskEvent, TaskEventBody,
};
use std::{
    fs, io,
    path::{Path, PathBuf},
    sync::{Arc, Mutex, MutexGuard},
    time::{SystemTime, UNIX_EPOCH},
};

/// Current Unix time in milliseconds (task book timestamps and lease checks).
pub(crate) fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_millis() as u64)
        .unwrap_or(0)
}

#[derive(Clone)]
pub(crate) struct TaskBookState {
    pub(crate) book: Arc<Mutex<TaskBook>>,
    pub(crate) signing_key: Arc<SigningKey>,
    pub(crate) path: PathBuf,
}

impl TaskBookState {
    /// Task book author id of this node (hex Ed25519 public key).
    pub(crate) fn author(&self) -> String {
        TaskEvent::author_id(&self.signing_key)
    }

    /// Task identifier owned by this node for a task `name`.
    pub(crate) fn owned_task_id(&self, name: &str) -> String {
        let author = self.author();
        if TaskEvent::owns_task(&author, name) {
            name.to_string()
        } else {
            TaskEvent::task_id_for(&author, name)
        }
    }

    fn lock(&self) -> Result<MutexGuard<'_, TaskBook>, TaskBookError> {
        self.book
            .lock()
            .map_err(|_| TaskBookError::Io("task book lock poisoned".to_string()))
    }

    /// Signs the next event of this node's chain, stores and persists it.
    pub(crate) fn append_signed(
        &self,
        task_id: &str,
        body: TaskEventBody,
    ) -> Result<TaskEvent, TaskBookError> {
        let mut book = self.lock()?;
        let author = self.author();
        let header = EventHeader {
            sequence: book.next_sequence(&author),
            previous_event_hash: book.head(&author).unwrap_or_default().to_string(),
            issued_at_ms: now_ms(),
            task_id: task_id.to_string(),
        };
        let event = TaskEvent::signed(&self.signing_key, header, body);
        book.append_persisted(&self.path, event.clone())?;
        Ok(event)
    }

    /// Takes an event received from a peer (any order; see
    /// [`TaskBook::receive`]) and persists what it adds.
    pub(crate) fn append_remote(&self, event: TaskEvent) -> Result<Received, TaskBookError> {
        self.lock()?.receive_persisted(&self.path, event)
    }

    /// Derived state of `task_id` now.
    pub(crate) fn state(&self, task_id: &str) -> Result<Option<DerivedTaskState>, TaskBookError> {
        Ok(self.lock()?.task_state(task_id, now_ms()))
    }
}

pub(crate) fn load_or_generate_identity(
    data_dir: &Path,
) -> Result<libp2p::identity::Keypair, io::Error> {
    fs::create_dir_all(data_dir)?;
    let key_path = data_dir.join("identity.key");

    if key_path.exists() {
        let bytes = fs::read(&key_path)?;
        let keypair = libp2p::identity::Keypair::from_protobuf_encoding(&bytes)
            .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;
        return Ok(keypair);
    }

    let keypair = libp2p::identity::Keypair::generate_ed25519();
    let bytes = keypair
        .to_protobuf_encoding()
        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;
    fs::write(&key_path, bytes)?;
    Ok(keypair)
}

pub(crate) fn load_taskbook_state(
    data_dir: &Path,
    local_key: &libp2p::identity::Keypair,
) -> Result<TaskBookState, io::Error> {
    let identity_bytes = local_key
        .to_protobuf_encoding()
        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;
    let seed = Sha256::digest(identity_bytes);
    let signing_key = SigningKey::from_bytes(&seed.into());
    let path = data_dir.join("taskbook.events.jsonl");
    let (book, report) = TaskBook::load_with_report(&path)
        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;
    if report.skipped_last_line {
        println!(" Task book: skipped a torn last line in {}", path.display()); // i18n:ignore -- operator log
    }

    Ok(TaskBookState {
        book: Arc::new(Mutex::new(book)),
        signing_key: Arc::new(signing_key),
        path,
    })
}
