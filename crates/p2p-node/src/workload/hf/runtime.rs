//! The Silicium AI runtime on this node, and the models prepared for it.
//!
//! The node talks to the runtime at `SILICIUM_AI_RUNTIME_URL` (the desktop
//! app starts it on `http://127.0.0.1:11436` when the user turns AI tasks
//! on); without that variable the node never takes `ai/hf/…` tasks. The
//! runtime runs the models; it never downloads anything: the node gives it a
//! directory of files it has checked.
//!
//! Preparing a model (first task that needs it, in the background): every
//! pinned file is downloaded into the model store (hash checked, see
//! `silicium_embedding::model::store::pinned`), then linked into
//! `<data dir>/ai/hf/models/<key>/` with the repository layout, then the
//! runtime loads it once (an architecture it does not know is refused
//! there). Meanwhile the node does not claim the task; the publisher
//! announces it again.
//!
//! Models whose files are here are "warm": the node announces their keys in
//! its heartbeat ([`warm_models`]), and the site prices a job lower when
//! enough workers have the model.

use super::manifest::Manifest;
use serde::Deserialize;
use serde_json::{Value, json};
use silicium_embedding::model::store::ModelStore;
use std::{
    collections::{BTreeSet, HashMap},
    path::{Path, PathBuf},
    sync::{LazyLock, Mutex},
    time::{Duration, Instant},
};

pub(crate) const HEALTH_TTL: Duration = Duration::from_secs(60);
pub(crate) const FAILED_RETRY: Duration = Duration::from_secs(10 * 60);
/// Name of the file written in a model directory once every file is there.
const READY_MARKER: &str = ".silicium-ready";
/// Longest call to the runtime (a fragment on a CPU).
const RUN_TIMEOUT: Duration = Duration::from_secs(55 * 60);

/// Runtime and Hub of the tests (one fake for the whole test process).
#[cfg(test)]
pub(crate) static TEST_URLS: std::sync::OnceLock<(String, String)> = std::sync::OnceLock::new();

/// `SILICIUM_AI_RUNTIME_URL`, when set.
pub(crate) fn runtime_url() -> Option<String> {
    #[cfg(test)]
    if let Some((runtime, _)) = TEST_URLS.get() {
        return Some(runtime.clone());
    }
    env_value("SILICIUM_AI_RUNTIME_URL")
}

fn env_value(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().trim_end_matches('/').to_string())
        .filter(|value| !value.is_empty())
}

fn model_store(data_dir: &Path) -> Result<ModelStore, String> {
    #[cfg(test)]
    if let Some((_, hub)) = TEST_URLS.get() {
        return Ok(ModelStore::new(
            data_dir.join("models"),
            hub,
            Box::new(
                silicium_embedding::model::store::HttpFetcher::new()
                    .map_err(|err| err.to_string())?,
            ),
        ));
    }
    ModelStore::from_env(data_dir).map_err(|err| err.to_string())
}

/// Directory of the model `key` for the runtime.
pub(crate) fn model_dir(data_dir: &Path, key: &str) -> PathBuf {
    data_dir.join("ai").join("hf").join("models").join(key)
}

/// A client of the runtime.
#[derive(Clone)]
pub(crate) struct Runtime {
    url: String,
    token: Option<String>,
    client: reqwest::Client,
}

#[derive(Debug, Deserialize)]
struct Health {
    format: String,
    #[serde(default)]
    tasks: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct RunResponse {
    outputs: Vec<Value>,
}

impl Runtime {
    pub(crate) fn new(url: String) -> Option<Self> {
        let client = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(5))
            .timeout(RUN_TIMEOUT)
            .build()
            .ok()?;
        Some(Self {
            url,
            token: env_value("SILICIUM_AI_RUNTIME_TOKEN"),
            client,
        })
    }

    fn post(&self, path: &str, body: &Value) -> reqwest::RequestBuilder {
        let request = self.client.post(format!("{}{path}", self.url)).json(body);
        match &self.token {
            Some(token) => request.bearer_auth(token),
            None => request,
        }
    }

    async fn health(&self) -> Result<Health, String> {
        let mut request = self.client.get(format!("{}/v1/health", self.url));
        if let Some(token) = &self.token {
            request = request.bearer_auth(token);
        }
        let response = request
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .and_then(|response| response.error_for_status())
            .map_err(|err| err.to_string())?;
        let health: Health = response.json().await.map_err(|err| err.to_string())?;
        if health.format != "silicium-ai-runtime/1" {
            return Err(format!("unknown runtime format {}", health.format));
        }
        Ok(health)
    }

    /// Loads the model of `dir` (the runtime keeps it loaded).
    async fn load(&self, dir: &Path, manifest: &Manifest) -> Result<(), String> {
        let response = self
            .post("/v1/load", &json!({"model_dir": dir, "manifest": manifest}))
            .send()
            .await
            .map_err(|err| err.to_string())?;
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(format!(
                "runtime refused the model ({status}): {}",
                truncate(&body)
            ));
        }
        Ok(())
    }

    /// Runs `items` (`{"id", "inputs"}`) and returns one output per item.
    pub(crate) async fn run(
        &self,
        dir: &Path,
        manifest: &Manifest,
        parameters: &serde_json::Map<String, Value>,
        seed: u64,
        items: &[super::batch::Item],
    ) -> Result<Vec<Value>, String> {
        let response = self
            .post(
                "/v1/run",
                &json!({
                    "task": manifest.task,
                    "model_dir": dir,
                    "manifest": manifest,
                    "parameters": parameters,
                    "seed": seed,
                    "items": items,
                }),
            )
            .send()
            .await
            .map_err(|err| err.to_string())?;
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(format!("runtime error ({status}): {}", truncate(&body)));
        }
        let answer: RunResponse = response.json().await.map_err(|err| err.to_string())?;
        if answer.outputs.len() != items.len() {
            return Err(format!(
                "runtime answered {} outputs for {} items",
                answer.outputs.len(),
                items.len()
            ));
        }
        Ok(answer.outputs)
    }
}

fn truncate(text: &str) -> &str {
    let end = text.char_indices().nth(300).map_or(text.len(), |(i, _)| i);
    &text[..end]
}

/// Tasks of the runtime at a URL, and when they were read.
struct CachedHealth {
    at: Instant,
    url: String,
    tasks: BTreeSet<String>,
}

/// Tasks of the runtime, checked at most every [`HEALTH_TTL`].
static HEALTH: LazyLock<Mutex<Option<CachedHealth>>> = LazyLock::new(Mutex::default);

/// The runtime when it answers and runs `task`.
pub(crate) async fn runtime_for(task: &str) -> Option<Runtime> {
    let url = runtime_url()?;
    let cached = HEALTH.lock().ok().and_then(|health| {
        health
            .as_ref()
            .filter(|cached| cached.at.elapsed() < HEALTH_TTL && cached.url == url)
            .map(|cached| cached.tasks.contains(task))
    });
    let runtime = Runtime::new(url.clone())?;
    let supported = match cached {
        Some(supported) => supported,
        None => {
            let tasks: BTreeSet<String> = match runtime.health().await {
                Ok(health) => health.tasks.into_iter().collect(),
                Err(err) => {
                    println!(" AI runtime at {url} unavailable: {err}");
                    BTreeSet::new()
                }
            };
            let supported = tasks.contains(task);
            if let Ok(mut health) = HEALTH.lock() {
                *health = Some(CachedHealth {
                    at: Instant::now(),
                    url,
                    tasks,
                });
            }
            supported
        }
    };
    supported.then_some(runtime)
}

enum Slot {
    Preparing,
    Ready,
    Failed { at: Instant },
}

/// Preparation of the models of this process, by key.
static SLOTS: LazyLock<Mutex<HashMap<String, Slot>>> = LazyLock::new(Mutex::default);

/// Keys of the models whose files are on this node.
static WARM: LazyLock<Mutex<BTreeSet<String>>> = LazyLock::new(Mutex::default);

/// Models whose files are on this node, announced in the heartbeat.
pub(crate) fn warm_models() -> Vec<String> {
    WARM.lock()
        .map(|warm| warm.iter().cloned().collect())
        .unwrap_or_default()
}

/// Finds the models prepared by an earlier run of the node.
pub(crate) fn scan_warm_models(data_dir: &Path) {
    let Ok(entries) = std::fs::read_dir(data_dir.join("ai").join("hf").join("models")) else {
        return;
    };
    if let Ok(mut warm) = WARM.lock() {
        for entry in entries.flatten() {
            if entry.path().join(READY_MARKER).is_file()
                && let Some(key) = entry.file_name().to_str()
            {
                warm.insert(key.to_string());
            }
        }
    }
}

/// True when the model of `manifest` is ready on the runtime; otherwise
/// starts preparing it (in the background) and answers false.
pub(crate) async fn ensure_model(runtime: &Runtime, manifest: &Manifest, data_dir: &Path) -> bool {
    let start = {
        let Ok(mut slots) = SLOTS.lock() else {
            return false;
        };
        match slots.get(&manifest.key) {
            Some(Slot::Ready) => return true,
            Some(Slot::Preparing) => return false,
            Some(Slot::Failed { at }) if at.elapsed() < FAILED_RETRY => return false,
            _ => {
                slots.insert(manifest.key.clone(), Slot::Preparing);
                true
            }
        }
    };
    if start {
        let (runtime, manifest, data_dir) =
            (runtime.clone(), manifest.clone(), data_dir.to_path_buf());
        tokio::spawn(async move {
            let key = manifest.key.clone();
            let slot = match prepare(&runtime, &manifest, &data_dir).await {
                Ok(()) => {
                    println!(" Model {key} ready");
                    Slot::Ready
                }
                Err(err) => {
                    println!(" Model {key} not prepared: {err}");
                    Slot::Failed { at: Instant::now() }
                }
            };
            if let Ok(mut slots) = SLOTS.lock() {
                slots.insert(key, slot);
            }
        });
    }
    false
}

async fn prepare(runtime: &Runtime, manifest: &Manifest, data_dir: &Path) -> Result<(), String> {
    let dir = model_dir(data_dir, &manifest.key);
    let (files, data) = (manifest.clone(), data_dir.to_path_buf());
    let dir_for_files = dir.clone();
    tokio::task::spawn_blocking(move || install_files(&files, &data, &dir_for_files))
        .await
        .map_err(|err| err.to_string())??;
    if let Ok(mut warm) = WARM.lock() {
        warm.insert(manifest.key.clone());
    }
    runtime.load(&dir, manifest).await
}

/// Downloads the pinned files (or finds them in the store) and links them
/// into the model directory with the repository layout.
fn install_files(manifest: &Manifest, data_dir: &Path, dir: &Path) -> Result<(), String> {
    let marker = dir.join(READY_MARKER);
    if std::fs::read_to_string(&marker).is_ok_and(|digest| digest.trim() == manifest.digest) {
        return Ok(());
    }
    let store = model_store(data_dir)?;
    println!(
        " Downloading model {} ({} files, {} MB)",
        manifest.key,
        manifest.files.len(),
        manifest.total_bytes / (1 << 20)
    );
    for file in &manifest.files {
        if !super::manifest::safe_path(&file.path) {
            return Err(format!("unsafe path {}", file.path));
        }
        let stored = store
            .ensure_pinned(&manifest.repository, &manifest.revision, &file.pinned())
            .map_err(|err| err.to_string())?;
        let target = dir.join(&file.path);
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent).map_err(|err| err.to_string())?;
        }
        if std::fs::metadata(&target).is_ok_and(|meta| meta.len() == file.size) {
            continue;
        }
        let _ = std::fs::remove_file(&target);
        if std::fs::hard_link(&stored, &target).is_err() {
            std::fs::copy(&stored, &target).map_err(|err| err.to_string())?;
        }
    }
    std::fs::write(&marker, &manifest.digest).map_err(|err| err.to_string())
}
