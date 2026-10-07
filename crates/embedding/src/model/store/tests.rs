use super::*;
use crate::model::{BertShape, MULTILINGUAL_E5_SMALL};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};

/// Serves files from memory and counts the requests.
#[derive(Clone, Default)]
struct FakeHub {
    files: Arc<Mutex<HashMap<String, Vec<u8>>>>,
    requests: Arc<Mutex<Vec<String>>>,
}

impl Fetcher for FakeHub {
    fn fetch(&self, url: &str, sink: &mut dyn Write) -> Result<()> {
        self.requests.lock().unwrap().push(url.to_string());
        let files = self.files.lock().unwrap();
        let body = files
            .get(url)
            .ok_or_else(|| Error::Model(format!("404 {url}")))?;
        sink.write_all(body)?;
        Ok(())
    }
}

fn hex(bytes: &[u8]) -> &'static str {
    let digest = Sha256::digest(bytes);
    Box::leak(
        digest
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>()
            .into_boxed_str(),
    )
}

fn spec_for(weights: &[u8], tokenizer: &[u8]) -> ModelSpec {
    ModelSpec {
        id: "test-model",
        repository: "owner/test-model",
        weights: ModelFile {
            name: "model.safetensors",
            sha256: hex(weights),
            size: weights.len() as u64,
        },
        tokenizer: ModelFile {
            name: "tokenizer.json",
            sha256: hex(tokenizer),
            size: tokenizer.len() as u64,
        },
        shape: BertShape {
            ..MULTILINGUAL_E5_SMALL.shape
        },
        ..MULTILINGUAL_E5_SMALL
    }
}

fn temp_root(name: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!("silicium-models-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    root
}

fn store_with(hub: &FakeHub, name: &str) -> ModelStore {
    ModelStore::new(
        temp_root(name),
        "https://mirror.example/",
        Box::new(hub.clone()),
    )
}

#[test]
fn files_are_downloaded_once_checked_and_kept_by_hash() {
    let spec = spec_for(b"weights", b"{}");
    let hub = FakeHub::default();
    let store = store_with(&hub, "once");
    for (file, body) in [
        (&spec.weights, b"weights".as_slice()),
        (&spec.tokenizer, b"{}".as_slice()),
    ] {
        hub.files
            .lock()
            .unwrap()
            .insert(store.url(&spec, file), body.to_vec());
    }
    assert_eq!(
        store.url(&spec, &spec.weights),
        format!(
            "https://mirror.example/owner/test-model/resolve/{}/model.safetensors",
            spec.revision
        )
    );
    assert!(!store.is_ready(&spec));
    let paths = store.ensure(&spec).unwrap();
    assert!(store.is_ready(&spec));
    assert_eq!(paths.weights, store.root().join(spec.weights.sha256));
    assert_eq!(fs::read(&paths.weights).unwrap(), b"weights");
    verify_file(&paths.tokenizer, &spec.tokenizer).unwrap();
    store.ensure(&spec).unwrap();
    assert_eq!(
        hub.requests.lock().unwrap().len(),
        2,
        "cached files are not fetched again"
    );
}

#[test]
fn a_tampered_download_is_refused_and_not_kept() {
    let spec = spec_for(b"weights", b"{}");
    let hub = FakeHub::default();
    let store = store_with(&hub, "tampered");
    hub.files
        .lock()
        .unwrap()
        .insert(store.url(&spec, &spec.weights), b"WEIGHTS".to_vec());
    let error = store.ensure(&spec).unwrap_err();
    assert!(error.to_string().contains("expected 7 bytes"), "{error}");
    assert!(!store.root().join(spec.weights.sha256).exists());
    assert!(
        fs::read_dir(store.root()).unwrap().next().is_none(),
        "no partial file nor lock left"
    );
}

#[test]
fn a_damaged_file_is_downloaded_again_and_an_oversized_one_refused() {
    let spec = spec_for(b"weights", b"{}");
    let hub = FakeHub::default();
    let store = store_with(&hub, "repair");
    for (file, body) in [
        (&spec.weights, b"weights".as_slice()),
        (&spec.tokenizer, b"{}".as_slice()),
    ] {
        hub.files
            .lock()
            .unwrap()
            .insert(store.url(&spec, file), body.to_vec());
    }
    let paths = store.ensure(&spec).unwrap();
    fs::write(&paths.weights, b"weightz").unwrap();
    store.ensure(&spec).unwrap();
    assert_eq!(fs::read(&paths.weights).unwrap(), b"weights", "repaired");

    let other = store_with(&hub, "oversized");
    hub.files.lock().unwrap().insert(
        other.url(&spec, &spec.weights),
        b"weights and more".to_vec(),
    );
    assert!(other.ensure(&spec).is_err());
    assert!(!other.root().join(spec.weights.sha256).exists());
}

#[test]
fn a_file_changed_on_disk_fails_verification() {
    let spec = spec_for(b"weights", b"{}");
    let root = temp_root("changed");
    fs::create_dir_all(&root).unwrap();
    let path = root.join(spec.weights.sha256);
    fs::write(&path, b"weightz").unwrap();
    assert!(verify_file(&path, &spec.weights).is_err());
}

#[test]
fn a_running_download_is_not_duplicated_but_a_stale_lock_is_taken_over() {
    let spec = spec_for(b"weights", b"{}");
    let hub = FakeHub::default();
    let store = store_with(&hub, "lock");
    fs::create_dir_all(store.root()).unwrap();
    let lock = store.root().join(format!("{}.lock", spec.weights.sha256));
    fs::write(&lock, b"").unwrap();
    assert!(
        store
            .ensure(&spec)
            .unwrap_err()
            .to_string()
            .contains("already running")
    );
    let old = SystemTime::now() - STALE_LOCK - Duration::from_secs(60);
    File::options()
        .write(true)
        .open(&lock)
        .unwrap()
        .set_modified(old)
        .unwrap();
    for (file, body) in [
        (&spec.weights, b"weights".as_slice()),
        (&spec.tokenizer, b"{}".as_slice()),
    ] {
        hub.files
            .lock()
            .unwrap()
            .insert(store.url(&spec, file), body.to_vec());
    }
    store.ensure(&spec).unwrap();
    assert!(!lock.exists());
}
