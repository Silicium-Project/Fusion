//! On-disk node state under the data directory: the libp2p identity key and
//! the signed task book (`taskbook.events.jsonl`).

use ed25519_dalek::SigningKey;
use sha2::{Digest, Sha256};
use silicium_node_core::taskbook::{
    DerivedTaskState, TaskBook, TaskBookError, TaskEvent, TaskEventKind,
};
use std::{
    fs, io,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};

#[derive(Clone)]
pub(crate) struct TaskBookState {
    pub(crate) book: Arc<Mutex<TaskBook>>,
    pub(crate) signing_key: Arc<SigningKey>,
    pub(crate) path: PathBuf,
}

impl TaskBookState {
    pub(crate) fn author(&self) -> String {
        TaskEvent::author_id(&self.signing_key)
    }

    pub(crate) fn append_signed(
        &self,
        kind: TaskEventKind,
        task_id: impl Into<String>,
        payload_ref: impl Into<String>,
        payload_hash: impl Into<String>,
    ) -> Result<TaskEvent, TaskBookError> {
        let mut book = self
            .book
            .lock()
            .map_err(|_| TaskBookError::Io("task book lock poisoned".to_string()))?;
        let author = self.author();
        let sequence = book.next_sequence(&author);
        let previous = book.head(&author).unwrap_or_default().to_string();
        let event = TaskEvent::signed(
            &self.signing_key,
            sequence,
            previous,
            kind,
            task_id,
            payload_ref,
            payload_hash,
        );
        book.append_persisted(&self.path, event.clone())?;
        Ok(event)
    }

    pub(crate) fn append_remote(&self, event: TaskEvent) -> Result<String, TaskBookError> {
        let mut book = self
            .book
            .lock()
            .map_err(|_| TaskBookError::Io("task book lock poisoned".to_string()))?;
        book.append_persisted(&self.path, event)
    }

    pub(crate) fn state(&self, task_id: &str) -> Result<Option<DerivedTaskState>, TaskBookError> {
        let book = self
            .book
            .lock()
            .map_err(|_| TaskBookError::Io("task book lock poisoned".to_string()))?;
        Ok(book.task_state(task_id))
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
    let book = TaskBook::load(&path)
        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;

    Ok(TaskBookState {
        book: Arc::new(Mutex::new(book)),
        signing_key: Arc::new(signing_key),
        path,
    })
}
