//! Document search for Silicium ("Recherche dans mes documents").
//!
//! A user drops documents; the network turns every passage of them into a
//! vector with a pinned embedding model; the user then searches the
//! passages by meaning. This crate holds everything that is not network
//! plumbing, so that the node (`p2p_node`, workload
//! `ai/embedding/multilingual-e5-small`) and the `silicium-embed` CLI share
//! exactly the same code:
//!
//! | Module | Role |
//! | --- | --- |
//! | [`documents`] | PDF, Word, text, Markdown and ZIP files to plain text pages |
//! | [`passages`] | pages to overlapping passages of a few hundred words |
//! | [`corpus`] | the canonical input of a job (`passages.jsonl`) and its split into fragments |
//! | [`model`] | the pinned models (revision and SHA-256 of every file) and their local cache |
//! | [`encoder`] | the model itself (Candle, CPU): text to normalized vectors |
//! | [`vectors`] | the binary vector block a worker publishes, and its checks |
//! | [`sampling`] | which passages a verifier recomputes |
//! | [`index`] | the assembled result and the similarity search over it |
//!
//! The formats are described in `docs/architecture/embedding-workload.md`
//! (Network repository) and in the module documentation.

pub mod corpus;
pub mod documents;
pub mod encoder;
pub mod error;
pub mod index;
pub mod model;
pub mod passages;
pub mod sampling;
#[cfg(any(test, feature = "test-model"))]
pub mod testing;
pub mod vectors;

pub use error::{Error, Result};
