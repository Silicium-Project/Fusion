//! The models of this node, loaded on demand and shared.
//!
//! The first time a node needs a model (to compute, verify or search), a
//! background thread downloads its files if needed, checks their hashes and
//! loads it; meanwhile [`encoder`] answers [`Readiness::Preparing`] and the
//! node does not claim the task (the publisher announces it again every
//! 10 s, so the node claims it once ready). A loaded model is shared by
//! every task and unloaded after [`idle_unload`] without use (it holds about
//! half a gigabyte). A failed load is retried after [`RETRY_AFTER`].

use super::{Embedding, ModelSource};
use silicium_embedding::{encoder::Encoder, model::store::ModelStore};
use std::{
    collections::HashMap,
    path::Path,
    sync::{Arc, LazyLock, Mutex},
    time::{Duration, Instant},
};

/// Delay before a failed model load is tried again.
pub(crate) const RETRY_AFTER: Duration = Duration::from_secs(10 * 60);
/// Default of `SILICIUM_EMBEDDING_IDLE_UNLOAD_S`.
const DEFAULT_IDLE_UNLOAD: Duration = Duration::from_secs(15 * 60);

/// Whether a model can be used now.
pub(crate) enum Readiness {
    Ready(Arc<Encoder>),
    /// Being downloaded or loaded.
    Preparing,
    /// The last load failed (message), not retried yet.
    Unavailable(String),
}

impl Readiness {
    pub(crate) fn is_ready(&self) -> bool {
        matches!(self, Readiness::Ready(_))
    }
}

enum Slot {
    Loading,
    Ready {
        encoder: Arc<Encoder>,
        last_used: Instant,
    },
    Failed {
        error: String,
        at: Instant,
    },
}

/// Models of this process, by workload identifier.
static SLOTS: LazyLock<Mutex<HashMap<&'static str, Slot>>> = LazyLock::new(Mutex::default);

/// The model of `workload`, starting to load it when needed (files kept
/// under `<data_dir>/models`, or `SILICIUM_MODEL_DIR`).
pub(crate) fn encoder(workload: &'static Embedding, data_dir: &Path) -> Readiness {
    let Ok(mut slots) = SLOTS.lock() else {
        return Readiness::Unavailable("model registry poisoned".into());
    };
    unload_idle(&mut slots, idle_unload());
    match slots.get_mut(workload.id) {
        Some(Slot::Ready { encoder, last_used }) => {
            *last_used = Instant::now();
            return Readiness::Ready(encoder.clone());
        }
        Some(Slot::Loading) => return Readiness::Preparing,
        Some(Slot::Failed { error, at }) if at.elapsed() < RETRY_AFTER => {
            return Readiness::Unavailable(error.clone());
        }
        _ => {}
    }
    slots.insert(workload.id, Slot::Loading);
    let data_dir = data_dir.to_path_buf();
    std::thread::spawn(move || {
        println!(" Preparing model {} for {}", workload.model.id, workload.id);
        let slot = match load(workload, &data_dir) {
            Ok(encoder) => {
                println!(" Model {} ready", workload.model.id);
                Slot::Ready {
                    encoder: Arc::new(encoder),
                    last_used: Instant::now(),
                }
            }
            Err(error) => {
                println!(" Model {} unavailable: {error}", workload.model.id);
                Slot::Failed {
                    error,
                    at: Instant::now(),
                }
            }
        };
        let loaded = matches!(slot, Slot::Ready { .. });
        if let Ok(mut slots) = SLOTS.lock() {
            slots.insert(workload.id, slot);
        }
        if loaded {
            watch_idle(workload.id);
        }
    });
    Readiness::Preparing
}

/// Unloads the model `id` once idle, even if nothing asks for it again;
/// returns when it is unloaded.
fn watch_idle(id: &'static str) {
    loop {
        std::thread::sleep(Duration::from_secs(60));
        let Ok(mut slots) = SLOTS.lock() else { return };
        unload_idle(&mut slots, idle_unload());
        if !matches!(slots.get(id), Some(Slot::Ready { .. })) {
            return;
        }
    }
}

fn load(workload: &Embedding, data_dir: &Path) -> Result<Encoder, String> {
    match workload.source {
        ModelSource::Download => {
            let store = ModelStore::from_env(data_dir).map_err(|err| err.to_string())?;
            let paths = store
                .ensure(workload.model)
                .map_err(|err| err.to_string())?;
            Encoder::load(workload.model, &paths).map_err(|err| err.to_string())
        }
        #[cfg(any(test, feature = "test-model"))]
        ModelSource::Builtin => {
            silicium_embedding::testing::tiny_encoder().map_err(|err| err.to_string())
        }
    }
}

/// Drops the models unused for `idle` and not held by a running task.
fn unload_idle(slots: &mut HashMap<&'static str, Slot>, idle: Duration) {
    slots.retain(|id, slot| match slot {
        Slot::Ready { encoder, last_used } => {
            let keep = last_used.elapsed() < idle || Arc::strong_count(encoder) > 1;
            if !keep {
                println!(" Model of {id} unloaded after {} s unused", idle.as_secs());
            }
            keep
        }
        _ => true,
    });
}

/// `SILICIUM_EMBEDDING_IDLE_UNLOAD_S`, default 15 minutes.
fn idle_unload() -> Duration {
    std::env::var("SILICIUM_EMBEDDING_IDLE_UNLOAD_S")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .map(Duration::from_secs)
        .unwrap_or(DEFAULT_IDLE_UNLOAD)
}

/// Waits until the model of `workload` is ready or failed (tests and the
/// search API's first query).
pub(crate) async fn wait_for(
    workload: &'static Embedding,
    data_dir: &Path,
    timeout: Duration,
) -> Readiness {
    let deadline = Instant::now() + timeout;
    loop {
        let readiness = encoder(workload, data_dir);
        if !matches!(readiness, Readiness::Preparing) || Instant::now() >= deadline {
            return readiness;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
}
