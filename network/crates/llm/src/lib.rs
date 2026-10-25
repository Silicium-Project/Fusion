//! Batch AI processing for Silicium ("Traitement par IA").
//!
//! A user gives a list of items (the rows of a spreadsheet column, the
//! lines of a text file...) and one instruction ("Résume en deux phrases",
//! "Classe cet avis : positif, négatif, neutre", "Extrais le nom et la
//! date"). The network applies the instruction to every item with a pinned
//! language model, run locally by Ollama on the workers, and returns one
//! answer per item.
//!
//! This crate holds everything that is not network plumbing, so that the
//! node (`p2p_node`, workload `ai/llm/qwen2.5-1.5b-instruct`) and the
//! `silicium-llm` CLI share exactly the same code:
//!
//! | Module | Role |
//! | --- | --- |
//! | [`model`] | the pinned model (GGUF file, revision, SHA-256) and the decoding options |
//! | [`request`] | what the site submits (`silicium-llm-request/1`) and its checks |
//! | [`batch`] | the canonical input of a job (`silicium-llm-batch/1`, JSON Lines) and its split into fragments |
//! | [`prompt`] | the exact prompt and output schema of an item, and how a raw answer is read |
//! | [`answers`] | the answers a worker publishes for a fragment (`silicium-llm-answers/1`) and their checks |
//! | [`similarity`] | how close two answers are, and the verdict of a verifier |
//! | [`result`] | the assembled result: `answers.jsonl`, `answers.csv`, `result.json` |
//! | [`ollama`] | the Ollama HTTP client (import of the pinned model, generation) |
//! | [`compute`] | answering items (workers and verifiers) |
//! | `testing` | a fake Ollama server (feature `test-ollama`, never in a release) |
//!
//! The formats are described in `docs/architecture/llm-workload.md`
//! (Network repository).

pub mod answers;
pub mod batch;
pub mod compute;
pub mod error;
pub mod model;
pub mod ollama;
pub mod prompt;
pub mod request;
pub mod result;
pub mod similarity;
#[cfg(any(test, feature = "test-ollama"))]
pub mod testing;

pub use error::{Error, Result};
