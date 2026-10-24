//! A fake Ollama server for tests and the local end-to-end check (feature
//! `test-ollama`, never in a release).
//!
//! It implements the calls of [`crate::ollama`]: version, show, blobs,
//! create and generate. Generation is deterministic and needs no model: a
//! text answer is the first words of the item, a label is picked from the
//! schema by a hash of the item, every field of an extraction is the first
//! word of the item. A server started with [`Behaviour::Liar`] answers
//! nonsense, as a cheating worker would.

use axum::{
    Json, Router,
    body::Bytes,
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
};
use serde_json::{Value, json};
use std::{
    collections::HashSet,
    sync::{Arc, Mutex},
};

/// How the fake answers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Behaviour {
    Honest,
    Liar,
}

#[derive(Default)]
struct Inner {
    blobs: HashSet<String>,
    models: Vec<(String, String)>,
    generations: u64,
}

/// State of a running fake, shared with the test.
#[derive(Clone)]
pub struct Fake {
    inner: Arc<Mutex<Inner>>,
    behaviour: Behaviour,
}

impl Fake {
    /// Generations served so far.
    pub fn generations(&self) -> u64 {
        self.inner
            .lock()
            .map(|inner| inner.generations)
            .unwrap_or(0)
    }

    /// Blobs uploaded so far.
    pub fn blob_count(&self) -> usize {
        self.inner
            .lock()
            .map(|inner| inner.blobs.len())
            .unwrap_or(0)
    }
}

/// Starts a fake on `bind` (`127.0.0.1:0` for any port) and returns its
/// URL; it runs until the runtime stops.
pub async fn spawn(bind: &str, behaviour: Behaviour) -> std::io::Result<(String, Fake)> {
    let fake = Fake {
        inner: Arc::default(),
        behaviour,
    };
    let app = Router::new()
        .route(
            "/api/version",
            get(|| async { Json(json!({"version": "0.0.0-fake"})) }),
        )
        .route("/api/show", post(show))
        .route("/api/blobs/{digest}", post(upload).head(blob))
        .route("/api/create", post(create))
        .route("/api/generate", post(generate))
        .with_state(fake.clone());
    let listener = tokio::net::TcpListener::bind(bind).await?;
    let url = format!("http://{}", listener.local_addr()?);
    tokio::spawn(async move {
        let _ = axum::serve(listener, app).await;
    });
    Ok((url, fake))
}

async fn show(State(fake): State<Fake>, Json(body): Json<Value>) -> (StatusCode, Json<Value>) {
    let name = body["model"].as_str().unwrap_or_default();
    let inner = fake.inner.lock().expect("fake state");
    match inner.models.iter().find(|(model, _)| model == name) {
        Some((_, digest)) => (
            StatusCode::OK,
            Json(
                json!({"modelfile": format!("FROM /models/blobs/{}\n", digest.replace(':', "-"))}),
            ),
        ),
        None => (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "model not found"})),
        ),
    }
}

async fn blob(State(fake): State<Fake>, Path(digest): Path<String>) -> StatusCode {
    let inner = fake.inner.lock().expect("fake state");
    if inner.blobs.contains(&digest) {
        StatusCode::OK
    } else {
        StatusCode::NOT_FOUND
    }
}

async fn upload(State(fake): State<Fake>, Path(digest): Path<String>, body: Bytes) -> StatusCode {
    if body.is_empty() {
        return StatusCode::BAD_REQUEST;
    }
    fake.inner.lock().expect("fake state").blobs.insert(digest);
    StatusCode::CREATED
}

async fn create(State(fake): State<Fake>, Json(body): Json<Value>) -> (StatusCode, Json<Value>) {
    let name = body["model"].as_str().unwrap_or_default().to_string();
    let Some(digest) = body["files"]
        .as_object()
        .and_then(|files| files.values().next())
        .and_then(Value::as_str)
        .map(str::to_string)
    else {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": "no files"})));
    };
    let mut inner = fake.inner.lock().expect("fake state");
    if !inner.blobs.contains(&digest) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "blob missing"})),
        );
    }
    inner.models.retain(|(model, _)| *model != name);
    inner.models.push((name, digest));
    (StatusCode::OK, Json(json!({"status": "success"})))
}

async fn generate(State(fake): State<Fake>, Json(body): Json<Value>) -> (StatusCode, Json<Value>) {
    let name = body["model"].as_str().unwrap_or_default();
    {
        let mut inner = fake.inner.lock().expect("fake state");
        if !inner.models.iter().any(|(model, _)| model == name) {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error": "model not found"})),
            );
        }
        inner.generations += 1;
    }
    let item = item_of(body["prompt"].as_str().unwrap_or_default());
    let words: Vec<&str> = item.split_whitespace().collect();
    let liar = fake.behaviour == Behaviour::Liar;
    let format = &body["format"];
    let response = if let Some(labels) = format["properties"]["label"]["enum"].as_array() {
        let index = if liar { 1 } else { item.len() } % labels.len().max(1);
        json!({"label": labels.get(index).cloned().unwrap_or(Value::Null)}).to_string()
    } else if let Some(fields) = format["properties"].as_object() {
        let value = if liar {
            "zzz"
        } else {
            words.first().copied().unwrap_or("")
        };
        Value::Object(
            fields
                .keys()
                .map(|field| (field.clone(), json!(value)))
                .collect(),
        )
        .to_string()
    } else if liar {
        "Lorem ipsum dolor sit amet.".to_string()
    } else {
        format!(
            "Réponse : {}",
            words.iter().take(8).copied().collect::<Vec<_>>().join(" ")
        )
    };
    (
        StatusCode::OK,
        Json(json!({"response": response, "done": true, "done_reason": "stop", "eval_count": 9})),
    )
}

/// The item of a prompt: between `<text>` and `</text>`, else the user
/// message.
fn item_of(prompt: &str) -> String {
    if let Some(start) = prompt.find("<text>\n")
        && let Some(end) = prompt.rfind("\n</text>")
        && start + 7 <= end
    {
        return prompt[start + 7..end].to_string();
    }
    prompt
        .split("<|im_start|>user\n")
        .nth(1)
        .and_then(|rest| rest.split("<|im_end|>").next())
        .unwrap_or_default()
        .to_string()
}
