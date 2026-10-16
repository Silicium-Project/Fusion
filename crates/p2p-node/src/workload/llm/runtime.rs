//! Ollama and the pinned model on this node.
//!
//! The node talks to the Ollama server of `SILICIUM_OLLAMA_URL` (the desktop
//! app starts one on `http://127.0.0.1:11435` when the user turns AI tasks
//! on). Without that variable the node never takes AI tasks.
//!
//! The first time a task needs the model, a background task checks that
//! Ollama answers and holds the model; if not, it downloads the pinned GGUF
//! file into the model store (hash checked, like the embedding models),
//! imports it into Ollama, then deletes the downloaded copy (Ollama keeps
//! its own). Meanwhile [`client`] answers `None` and the node does not claim
//! the task: the publisher announces it again every 10 s.
//!
//! A ready model is checked again after [`RECHECK_AFTER`] (Ollama may have
//! been stopped or its models deleted). An unreachable Ollama is tried again
//! after [`UNREACHABLE_RETRY`], a failed preparation after [`FAILED_RETRY`].

use super::Llm;
use silicium_embedding::model::{ModelFile, store::ModelStore};
use silicium_llm::ollama::Ollama;
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::{LazyLock, Mutex},
    time::{Duration, Instant},
};

pub(crate) const RECHECK_AFTER: Duration = Duration::from_secs(60);
pub(crate) const UNREACHABLE_RETRY: Duration = Duration::from_secs(30);
pub(crate) const FAILED_RETRY: Duration = Duration::from_secs(10 * 60);

enum Slot {
    Preparing,
    /// Ready on the server of `url`. The client is built for each use: an
    /// HTTP client keeps connections on the runtime that created it.
    Ready {
        url: String,
        checked: Instant,
    },
    Unreachable {
        at: Instant,
    },
    Failed {
        at: Instant,
    },
}

/// State of the models of this process, by workload identifier.
static SLOTS: LazyLock<Mutex<HashMap<&'static str, Slot>>> = LazyLock::new(Mutex::default);

/// Ollama server of the tests (one fake for the whole test process).
#[cfg(test)]
pub(crate) static TEST_OLLAMA_URL: std::sync::OnceLock<String> = std::sync::OnceLock::new();

/// `SILICIUM_OLLAMA_URL`, when set.
pub(crate) fn ollama_url() -> Option<String> {
    #[cfg(test)]
    if let Some(url) = TEST_OLLAMA_URL.get() {
        return Some(url.clone());
    }
    std::env::var("SILICIUM_OLLAMA_URL")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

enum Next {
    Use(Ollama),
    Recheck(Ollama),
    Start,
    Wait,
}

/// The Ollama client of `workload` when its model is ready; otherwise
/// starts preparing it (in the background) and answers `None`.
pub(crate) async fn client(workload: &'static Llm, data_dir: &Path) -> Option<Ollama> {
    let url = ollama_url()?;
    let next = {
        let mut slots = SLOTS.lock().ok()?;
        let next = match slots.get(workload.id) {
            Some(Slot::Ready {
                url: ready,
                checked,
            }) if *ready == url => {
                let client = Ollama::new(&url).ok()?;
                if checked.elapsed() < RECHECK_AFTER {
                    Next::Use(client)
                } else {
                    Next::Recheck(client)
                }
            }
            Some(Slot::Preparing) => Next::Wait,
            Some(Slot::Unreachable { at }) if at.elapsed() < UNREACHABLE_RETRY => Next::Wait,
            Some(Slot::Failed { at }) if at.elapsed() < FAILED_RETRY => Next::Wait,
            _ => Next::Start,
        };
        if matches!(next, Next::Start) {
            slots.insert(workload.id, Slot::Preparing);
        }
        next
    };
    match next {
        Next::Use(client) => Some(client),
        Next::Wait => None,
        Next::Recheck(client) => {
            if client.has_model(workload.model).await.unwrap_or(false) {
                set(
                    workload,
                    Slot::Ready {
                        url,
                        checked: Instant::now(),
                    },
                );
                Some(client)
            } else {
                println!(
                    " Model {} no longer in Ollama; preparing it again",
                    workload.model.id
                );
                set(workload, Slot::Preparing);
                tokio::spawn(prepare(workload, url, data_dir.to_path_buf()));
                None
            }
        }
        Next::Start => {
            tokio::spawn(prepare(workload, url, data_dir.to_path_buf()));
            None
        }
    }
}

fn set(workload: &'static Llm, slot: Slot) {
    if let Ok(mut slots) = SLOTS.lock() {
        slots.insert(workload.id, slot);
    }
}

async fn prepare(workload: &'static Llm, url: String, data_dir: PathBuf) {
    // In a task of its own: a panic marks the model failed (retried later)
    // instead of leaving it "preparing" forever.
    let attempt = {
        let url = url.clone();
        tokio::spawn(async move { ready(workload, &url, &data_dir).await })
    };
    let outcome = attempt
        .await
        .unwrap_or_else(|err| Err(Failure::Other(format!("preparation crashed: {err}"))));
    let slot = match outcome {
        Ok(()) => {
            println!(" Model {} ready in Ollama ({url})", workload.model.id);
            Slot::Ready {
                url: url.clone(),
                checked: Instant::now(),
            }
        }
        Err(Failure::Unreachable(error)) => {
            println!(" Ollama unreachable at {url}: {error}; AI tasks skipped for now");
            Slot::Unreachable { at: Instant::now() }
        }
        Err(Failure::Other(error)) => {
            println!(" Model {} unavailable: {error}", workload.model.id);
            Slot::Failed { at: Instant::now() }
        }
    };
    set(workload, slot);
}

enum Failure {
    Unreachable(String),
    Other(String),
}

async fn ready(workload: &'static Llm, url: &str, data_dir: &Path) -> Result<(), Failure> {
    let client = Ollama::new(url).map_err(|err| Failure::Other(err.to_string()))?;
    client
        .version()
        .await
        .map_err(|err| Failure::Unreachable(err.to_string()))?;
    if client.has_model(workload.model).await.map_err(other)? {
        return Ok(());
    }
    println!(" Preparing model {} for {}", workload.model.id, workload.id);
    let path = gguf_file(workload, data_dir).await?;
    client.import(workload.model, &path).await.map_err(other)?;
    // Ollama keeps its own copy of the weights.
    let _ = std::fs::remove_file(&path);
    Ok(())
}

/// The pinned GGUF file on disk: downloaded into the model store (or, for
/// the test model, written from memory).
async fn gguf_file(workload: &'static Llm, data_dir: &Path) -> Result<PathBuf, Failure> {
    let weights = workload.model.weights;
    let file = ModelFile {
        name: weights.name,
        sha256: weights.sha256,
        size: weights.size,
    };
    let data_dir = data_dir.to_path_buf();
    // The store's HTTP client is a blocking one: never on the async runtime.
    tokio::task::spawn_blocking(move || {
        let store = ModelStore::from_env(&data_dir).map_err(other)?;
        #[cfg(any(test, feature = "test-ollama"))]
        if let Some(bytes) = super::test_model_bytes(workload) {
            let path = store.file_path(&file);
            std::fs::create_dir_all(store.root()).map_err(other)?;
            std::fs::write(&path, bytes).map_err(other)?;
            return Ok(path);
        }
        store
            .ensure_file(workload.model.repository, workload.model.revision, &file)
            .map_err(other)
    })
    .await
    .map_err(other)?
}

fn other(err: impl std::fmt::Display) -> Failure {
    Failure::Other(err.to_string())
}

/// Waits until the model of `workload` is ready, or `timeout` (tests).
#[cfg(test)]
pub(crate) async fn wait_for(
    workload: &'static Llm,
    data_dir: &Path,
    timeout: Duration,
) -> Option<Ollama> {
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(client) = client(workload, data_dir).await {
            return Some(client);
        }
        if Instant::now() >= deadline {
            return None;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}
