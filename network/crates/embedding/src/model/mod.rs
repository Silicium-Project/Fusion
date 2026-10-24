//! The embedding models the network runs, pinned.
//!
//! Every node of a job must use exactly the same model, or the vectors of
//! two workers would not be comparable and a verifier could not check a
//! worker. A [`ModelSpec`] therefore fixes:
//! - the source repository and its revision (a commit, never a branch);
//! - the SHA-256 and size of every downloaded file, checked after download
//!   and again when the model is loaded;
//! - the architecture, compiled in (the repository's `config.json` is not
//!   downloaded, so it cannot be swapped);
//! - how texts are prepared (the e5 models expect `passage: ` and `query: `
//!   prefixes) and pooled.
//!
//! Changing any of these is a new model, under a new identifier, hence a
//! new workload identifier: old and new vectors are never mixed.
//!
//! Files are downloaded once per machine into a [`store::ModelStore`].

pub mod store;

use serde_json::{Value, json};

/// A file of a model.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ModelFile {
    pub name: &'static str,
    pub sha256: &'static str,
    pub size: u64,
}

/// BERT architecture of a model (the fields of its `config.json`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BertShape {
    pub vocab_size: usize,
    pub hidden_size: usize,
    pub num_hidden_layers: usize,
    pub num_attention_heads: usize,
    pub intermediate_size: usize,
    pub max_position_embeddings: usize,
    pub type_vocab_size: usize,
    pub layer_norm_eps: f64,
    pub pad_token_id: usize,
}

/// One pinned embedding model.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ModelSpec {
    /// Identifier, part of the workload identifier.
    pub id: &'static str,
    /// Repository on the model hub (`owner/name`).
    pub repository: &'static str,
    /// Commit of the repository the files come from.
    pub revision: &'static str,
    /// Weights (`safetensors`), then tokenizer (`tokenizer.json`).
    pub weights: ModelFile,
    pub tokenizer: ModelFile,
    pub shape: BertShape,
    /// Size of a vector.
    pub dimension: usize,
    /// Longest input, in tokens (longer texts are truncated).
    pub max_tokens: usize,
    pub passage_prefix: &'static str,
    pub query_prefix: &'static str,
    /// Smallest cosine similarity between a worker's vector and the
    /// verifier's recomputation for the worker to be right. Two honest CPUs
    /// differ by rounding only (cosine above 0.99999); a vector made
    /// otherwise (another model, a quantized model, noise) falls well below.
    pub min_verification_cosine: f32,
}

impl ModelSpec {
    /// Files to download, in order.
    pub fn files(&self) -> [ModelFile; 2] {
        [self.weights, self.tokenizer]
    }

    /// Candle configuration of the architecture.
    pub fn bert_config(&self) -> Value {
        let shape = &self.shape;
        json!({
            "vocab_size": shape.vocab_size,
            "hidden_size": shape.hidden_size,
            "num_hidden_layers": shape.num_hidden_layers,
            "num_attention_heads": shape.num_attention_heads,
            "intermediate_size": shape.intermediate_size,
            "hidden_act": "gelu",
            "hidden_dropout_prob": 0.0,
            "max_position_embeddings": shape.max_position_embeddings,
            "type_vocab_size": shape.type_vocab_size,
            "initializer_range": 0.02,
            "layer_norm_eps": shape.layer_norm_eps,
            "pad_token_id": shape.pad_token_id,
            "position_embedding_type": "absolute",
            "use_cache": false,
            "classifier_dropout": null,
            "model_type": "bert",
        })
    }
}

/// `intfloat/multilingual-e5-small`: 384-dimension vectors, about 100
/// languages (French and English included), 118 M parameters (470 MB of
/// weights in f32), MIT licence.
pub const MULTILINGUAL_E5_SMALL: ModelSpec = ModelSpec {
    id: "multilingual-e5-small",
    repository: "intfloat/multilingual-e5-small",
    revision: "614241f622f53c4eeff9890bdc4f31cfecc418b3",
    weights: ModelFile {
        name: "model.safetensors",
        sha256: "1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477",
        size: 470_641_600,
    },
    tokenizer: ModelFile {
        name: "tokenizer.json",
        sha256: "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
        size: 17_082_730,
    },
    shape: BertShape {
        vocab_size: 250_037,
        hidden_size: 384,
        num_hidden_layers: 12,
        num_attention_heads: 12,
        intermediate_size: 1_536,
        max_position_embeddings: 512,
        type_vocab_size: 2,
        layer_norm_eps: 1e-12,
        pad_token_id: 0,
    },
    dimension: 384,
    max_tokens: 512,
    passage_prefix: "passage: ",
    query_prefix: "query: ",
    min_verification_cosine: 0.999,
};

/// Every model the network runs.
pub const MODELS: &[&ModelSpec] = &[&MULTILINGUAL_E5_SMALL];

/// The model `id`.
pub fn find(id: &str) -> Option<&'static ModelSpec> {
    MODELS.iter().copied().find(|model| model.id == id)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn models_are_pinned_to_a_commit_and_hashes() {
        for model in MODELS {
            assert_eq!(
                model.revision.len(),
                40,
                "{}: a commit, not a branch",
                model.id
            );
            for file in model.files() {
                assert_eq!(file.sha256.len(), 64);
                assert!(file.sha256.bytes().all(|b| b.is_ascii_hexdigit()));
                assert!(file.size > 0);
            }
            assert_eq!(model.dimension, model.shape.hidden_size);
            assert_eq!(find(model.id), Some(*model));
        }
    }

    #[test]
    fn the_architecture_is_a_valid_candle_config() {
        let config: candle_transformers::models::bert::Config =
            serde_json::from_value(MULTILINGUAL_E5_SMALL.bert_config()).unwrap();
        assert_eq!(config.hidden_size, 384);
        assert_eq!(config.vocab_size, 250_037);
    }
}
