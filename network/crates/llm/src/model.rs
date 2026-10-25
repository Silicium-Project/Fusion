//! The language model the network runs, pinned, and how it decodes.
//!
//! Every worker and verifier of a job must run exactly the same model with
//! exactly the same prompt and decoding options, or a verifier could not
//! check a worker. An [`LlmModel`] therefore fixes:
//! - the GGUF file, by repository, revision (a commit) and SHA-256: the node
//!   downloads it into its model store and imports it into Ollama under a
//!   name that contains the hash ([`LlmModel::ollama_name`]), so a model of
//!   another file is never mistaken for it;
//! - the chat format, written by this crate ([`crate::prompt`]) and sent in
//!   Ollama's `raw` mode: the template of the Ollama version installed does
//!   not matter;
//! - the decoding options ([`LlmModel::options`]): greedy decoding (the most
//!   likely token every time), so two honest machines give the same answer
//!   up to rounding differences between processors.
//!
//! Changing any of these is a new model, under a new identifier, hence a
//! new workload identifier.

use serde_json::{Value, json};

/// The weights of a model: one GGUF file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GgufFile {
    pub name: &'static str,
    pub sha256: &'static str,
    pub size: u64,
}

/// One pinned language model.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LlmModel {
    /// Identifier, part of the workload identifier.
    pub id: &'static str,
    /// Repository on the model hub (`owner/name`).
    pub repository: &'static str,
    /// Commit of the repository the file comes from.
    pub revision: &'static str,
    pub weights: GgufFile,
    /// Licence of the weights, shown in the result.
    pub licence: &'static str,
    /// Context window given to Ollama, in tokens.
    pub context_tokens: u32,
    /// Tokens that end an answer.
    pub stop: &'static [&'static str],
    /// Seed of the sampler (unused by greedy decoding, pinned anyway).
    pub seed: u32,
    pub repeat_penalty: f32,
}

impl LlmModel {
    /// Name of the model inside Ollama: the identifier and the first 16
    /// characters of the weights' hash.
    pub fn ollama_name(&self) -> String {
        format!("silicium-{}-{}", self.id, &self.weights.sha256[..16])
    }

    /// Ollama options of a generation of at most `max_tokens` tokens.
    pub fn options(&self, max_tokens: u32) -> Value {
        json!({
            "temperature": 0.0,
            "top_k": 1,
            "top_p": 1.0,
            "min_p": 0.0,
            "seed": self.seed,
            "num_ctx": self.context_tokens,
            "num_predict": max_tokens,
            "repeat_penalty": self.repeat_penalty,
            "repeat_last_n": 64,
            "stop": self.stop,
        })
    }
}

/// `Qwen/Qwen2.5-1.5B-Instruct-GGUF`, quantized `q4_k_m`: 1.5 B parameters
/// (1.1 GB), about 30 languages (French, English and German included),
/// Apache 2.0 licence. Runs on a CPU at a few to tens of tokens per second,
/// much faster on a GPU.
pub const QWEN2_5_1_5B_INSTRUCT: LlmModel = LlmModel {
    id: "qwen2.5-1.5b-instruct",
    repository: "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    revision: "91cad51170dc346986eccefdc2dd33a9da36ead9",
    weights: GgufFile {
        name: "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        sha256: "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        size: 1_117_320_736,
    },
    licence: "Apache-2.0",
    context_tokens: 8192,
    stop: &["<|im_end|>", "<|endoftext|>"],
    seed: 7,
    repeat_penalty: 1.05,
};

/// Every model the network runs.
pub const MODELS: &[&LlmModel] = &[&QWEN2_5_1_5B_INSTRUCT];

/// The model `id`.
pub fn find(id: &str) -> Option<&'static LlmModel> {
    MODELS.iter().copied().find(|model| model.id == id)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn models_are_pinned_to_a_commit_and_a_hash() {
        for model in MODELS {
            assert_eq!(model.revision.len(), 40, "{}: a commit", model.id);
            assert_eq!(model.weights.sha256.len(), 64);
            assert!(model.weights.sha256.bytes().all(|b| b.is_ascii_hexdigit()));
            assert!(model.weights.size > 0);
            assert_eq!(find(model.id), Some(*model));
        }
    }

    #[test]
    fn the_ollama_name_names_the_file() {
        let name = QWEN2_5_1_5B_INSTRUCT.ollama_name();
        assert_eq!(name, "silicium-qwen2.5-1.5b-instruct-6a1a2eb6d15622bf");
        assert!(
            name.bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"._-".contains(&b))
        );
    }

    #[test]
    fn decoding_is_greedy() {
        let options = QWEN2_5_1_5B_INSTRUCT.options(128);
        assert_eq!(options["temperature"], 0.0);
        assert_eq!(options["top_k"], 1);
        assert_eq!(options["num_predict"], 128);
    }
}
