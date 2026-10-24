//! The Ollama HTTP client of a node.
//!
//! Ollama runs on the worker's machine (started by the desktop app, see
//! `apps/silicium-node` in Fusion) and is reached on the loopback interface.
//! The node never asks Ollama to download a model from its own registry:
//! it downloads the pinned GGUF file itself (hash checked), uploads it as a
//! blob (Ollama checks the hash again) and creates the model from it
//! ([`Ollama::import`]). [`Ollama::has_model`] checks that a model of that
//! name exists and is made of that file.
//!
//! Every call has a timeout.

use crate::{Error, Result, model::LlmModel};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{path::Path, time::Duration};

const QUICK: Duration = Duration::from_secs(5);
const IMPORT: Duration = Duration::from_secs(30 * 60);

/// An Ollama server.
#[derive(Clone)]
pub struct Ollama {
    base: String,
    client: reqwest::Client,
}

/// A generated answer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Generation {
    pub text: String,
    /// Stopped by the length limit rather than by the model.
    pub truncated: bool,
    /// Tokens generated.
    pub tokens: u64,
}

#[derive(Deserialize)]
struct GenerateResponse {
    #[serde(default)]
    response: String,
    #[serde(default)]
    done_reason: String,
    #[serde(default)]
    eval_count: u64,
}

impl Ollama {
    /// The server at `base_url` (`http://127.0.0.1:11435`).
    pub fn new(base_url: &str) -> Result<Ollama> {
        let client = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(3))
            .no_proxy()
            .build()
            .map_err(|err| Error::Ollama(format!("http client: {err}")))?;
        Ok(Ollama {
            base: base_url.trim().trim_end_matches('/').to_string(),
            client,
        })
    }

    pub fn base_url(&self) -> &str {
        &self.base
    }

    /// The version of the server, when it answers.
    pub async fn version(&self) -> Result<String> {
        let value: Value = self
            .client
            .get(self.url("/api/version"))
            .timeout(QUICK)
            .send()
            .await
            .and_then(|response| response.error_for_status())
            .map_err(|err| Error::Ollama(format!("unreachable: {err}")))?
            .json()
            .await
            .map_err(|err| Error::Ollama(format!("version: {err}")))?;
        Ok(value["version"].as_str().unwrap_or_default().to_string())
    }

    /// True when the model `model` exists in Ollama and is made of its
    /// pinned GGUF file.
    pub async fn has_model(&self, model: &LlmModel) -> Result<bool> {
        let response = self
            .client
            .post(self.url("/api/show"))
            .json(&json!({"model": model.ollama_name()}))
            .timeout(QUICK * 6)
            .send()
            .await
            .map_err(|err| Error::Ollama(format!("show: {err}")))?;
        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(false);
        }
        let value: Value = response
            .error_for_status()
            .map_err(|err| Error::Ollama(format!("show: {err}")))?
            .json()
            .await
            .map_err(|err| Error::Ollama(format!("show: {err}")))?;
        let modelfile = value["modelfile"].as_str().unwrap_or_default();
        let sha256 = model.weights.sha256;
        Ok(modelfile.contains(&format!("sha256-{sha256}"))
            || modelfile.contains(&format!("sha256:{sha256}")))
    }

    /// Imports the pinned model from its GGUF file at `gguf` (already
    /// checked against its hash): uploads it as a blob unless Ollama has
    /// it, then creates the model.
    pub async fn import(&self, model: &LlmModel, gguf: &Path) -> Result<()> {
        let digest = format!("sha256:{}", model.weights.sha256);
        let blob_url = self.url(&format!("/api/blobs/{digest}"));
        let present = self
            .client
            .head(&blob_url)
            .timeout(QUICK * 6)
            .send()
            .await
            .is_ok_and(|response| response.status().is_success());
        if !present {
            let file = tokio::fs::File::open(gguf).await?;
            self.client
                .post(&blob_url)
                .body(reqwest::Body::from(file))
                .timeout(IMPORT)
                .send()
                .await
                .and_then(|response| response.error_for_status())
                .map_err(|err| Error::Ollama(format!("blob upload: {err}")))?;
        }
        self.client
            .post(self.url("/api/create"))
            .json(&json!({
                "model": model.ollama_name(),
                "files": {model.weights.name: digest},
                "stream": false,
            }))
            .timeout(IMPORT)
            .send()
            .await
            .and_then(|response| response.error_for_status())
            .map_err(|err| Error::Ollama(format!("create: {err}")))?;
        if !self.has_model(model).await? {
            return Err(Error::Ollama(
                "model created but not found with its file".into(),
            ));
        }
        Ok(())
    }

    /// Generates the answer to the raw prompt `prompt`, constrained by the
    /// JSON schema `format` when there is one.
    pub async fn generate(
        &self,
        model: &LlmModel,
        prompt: &str,
        max_tokens: u32,
        format: Option<&Value>,
        timeout: Duration,
    ) -> Result<Generation> {
        let mut body = json!({
            "model": model.ollama_name(),
            "prompt": prompt,
            "raw": true,
            "stream": false,
            "keep_alive": "10m",
            "options": model.options(max_tokens),
        });
        if let Some(format) = format {
            body["format"] = format.clone();
        }
        let response: GenerateResponse = self
            .client
            .post(self.url("/api/generate"))
            .json(&body)
            .timeout(timeout)
            .send()
            .await
            .and_then(|response| response.error_for_status())
            .map_err(|err| Error::Ollama(format!("generate: {err}")))?
            .json()
            .await
            .map_err(|err| Error::Ollama(format!("generate: {err}")))?;
        Ok(Generation {
            text: response.response,
            truncated: response.done_reason == "length",
            tokens: response.eval_count,
        })
    }

    fn url(&self, path: &str) -> String {
        format!("{}{path}", self.base)
    }
}
