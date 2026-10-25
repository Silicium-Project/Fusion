//! A tiny model for tests (feature `test-model`, never in a release build).
//!
//! The real model is 470 MB and has to be downloaded; tests and the local
//! end-to-end check of the network instead use [`TINY`], a 2-layer BERT of
//! dimension 32 whose weights are generated from their names
//! ([`tiny_encoder`]), so every process builds exactly the same model
//! without any file. Its vectors mean nothing, but every property the
//! network relies on holds: deterministic, unit length, the same text gives
//! the same vector on every node.

use crate::{
    Error, Result,
    encoder::Encoder,
    model::{BertShape, ModelFile, ModelSpec, store::ModelPaths},
};
use candle_core::{DType, Device, Shape, Tensor};
use candle_nn::{Init, VarBuilder, var_builder::SimpleBackend};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap},
    path::Path,
    sync::Mutex,
};
use tokenizers::Tokenizer;

/// Words of the tiny vocabulary (ids from 4).
const WORDS: &[&str] = &[
    "passage",
    "query",
    ":",
    ".",
    ",",
    "le",
    "la",
    "les",
    "un",
    "une",
    "de",
    "du",
    "et",
    "à",
    "contrat",
    "résilier",
    "résiliation",
    "abonnement",
    "préavis",
    "lettre",
    "recommandée",
    "client",
    "mettre",
    "fin",
    "chat",
    "chien",
    "voiture",
    "maison",
    "cours",
    "droit",
    "page",
    "notes",
    "mes",
    "document",
    "paris",
    "lyon",
    "train",
    "avion",
    "prix",
    "jours",
    "trente",
];

/// The tiny model. Its file hashes are placeholders: it is built in memory.
pub const TINY: ModelSpec = ModelSpec {
    id: "test-tiny",
    repository: "silicium/test-tiny",
    revision: "0000000000000000000000000000000000000000",
    weights: ModelFile {
        name: "model.safetensors",
        sha256: "",
        size: 0,
    },
    tokenizer: ModelFile {
        name: "tokenizer.json",
        sha256: "",
        size: 0,
    },
    shape: BertShape {
        vocab_size: 4 + WORDS.len(),
        hidden_size: 32,
        num_hidden_layers: 2,
        num_attention_heads: 4,
        intermediate_size: 64,
        max_position_embeddings: 64,
        type_vocab_size: 2,
        layer_norm_eps: 1e-12,
        pad_token_id: 1,
    },
    dimension: 32,
    max_tokens: 64,
    passage_prefix: "passage: ",
    query_prefix: "query: ",
    min_verification_cosine: 0.999,
};

/// The tiny model, built in memory.
pub fn tiny_encoder() -> Result<Encoder> {
    let weights =
        VarBuilder::from_backend(Box::new(NamedWeights::default()), DType::F32, Device::Cpu);
    Encoder::from_parts(&TINY, weights, tiny_tokenizer()?)
}

/// Writes the tiny model as files into `dir`, and returns a spec pinning
/// their hashes (to test loading from disk).
pub fn write_tiny_files(dir: &Path) -> Result<(ModelSpec, ModelPaths)> {
    std::fs::create_dir_all(dir)?;
    let backend = NamedWeights::default();
    let tensors = {
        let weights = VarBuilder::from_backend(Box::new(backend.clone()), DType::F32, Device::Cpu);
        let config =
            serde_json::from_value(TINY.bert_config()).map_err(|e| Error::Model(e.to_string()))?;
        candle_transformers::models::bert::BertModel::load(weights, &config)?;
        backend.generated.lock().expect("weights lock").clone()
    };
    let paths = ModelPaths {
        weights: dir.join("model.safetensors"),
        tokenizer: dir.join("tokenizer.json"),
    };
    let tensors: HashMap<String, Tensor> = tensors.into_iter().collect();
    candle_core::safetensors::save(&tensors, &paths.weights)?;
    std::fs::write(&paths.tokenizer, tokenizer_json())?;
    let pin = |name: &'static str, path: &Path| -> Result<ModelFile> {
        let bytes = std::fs::read(path)?;
        let sha256: String = Sha256::digest(&bytes)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        Ok(ModelFile {
            name,
            sha256: Box::leak(sha256.into_boxed_str()),
            size: bytes.len() as u64,
        })
    };
    let spec = ModelSpec {
        weights: pin("model.safetensors", &paths.weights)?,
        tokenizer: pin("tokenizer.json", &paths.tokenizer)?,
        ..TINY
    };
    Ok((spec, paths))
}

fn tiny_tokenizer() -> Result<Tokenizer> {
    Tokenizer::from_bytes(tokenizer_json()).map_err(|err| Error::Model(format!("tokenizer: {err}")))
}

/// A word-level tokenizer framing texts as `<s> … </s>`, like XLM-R.
fn tokenizer_json() -> String {
    let mut vocab = serde_json::Map::new();
    for (id, token) in ["<s>", "<pad>", "</s>", "<unk>"]
        .iter()
        .chain(WORDS)
        .enumerate()
    {
        vocab.insert(token.to_string(), id.into());
    }
    let special = |token: &str| serde_json::json!({"SpecialToken": {"id": token, "type_id": 0}});
    let sequence = |id: &str| serde_json::json!({"Sequence": {"id": id, "type_id": 0}});
    serde_json::json!({
        "version": "1.0",
        "truncation": null,
        "padding": null,
        "added_tokens": [],
        "normalizer": {"type": "Lowercase"},
        "pre_tokenizer": {"type": "Whitespace"},
        "post_processor": {
            "type": "TemplateProcessing",
            "single": [special("<s>"), sequence("A"), special("</s>")],
            "pair": [special("<s>"), sequence("A"), special("</s>"), sequence("B"), special("</s>")],
            "special_tokens": {
                "<s>": {"id": "<s>", "ids": [0], "tokens": ["<s>"]},
                "</s>": {"id": "</s>", "ids": [2], "tokens": ["</s>"]}
            }
        },
        "decoder": null,
        "model": {"type": "WordLevel", "vocab": vocab, "unk_token": "<unk>"}
    })
    .to_string()
}

/// Weights generated from their name: constants where the layer asks for
/// one (layer norms), else values in [-0.2, 0.2] from SHA-256 of the name.
#[derive(Clone, Default)]
struct NamedWeights {
    generated: std::sync::Arc<Mutex<BTreeMap<String, Tensor>>>,
}

impl SimpleBackend for NamedWeights {
    fn get(
        &self,
        shape: Shape,
        name: &str,
        hint: Init,
        dtype: DType,
        device: &Device,
    ) -> candle_core::Result<Tensor> {
        let count = shape.elem_count();
        let values: Vec<f32> = match hint {
            Init::Const(value) => vec![value as f32; count],
            _ => (0..count).map(|index| pseudo_random(name, index)).collect(),
        };
        let tensor = Tensor::from_vec(values, shape, device)?.to_dtype(dtype)?;
        self.generated
            .lock()
            .expect("weights lock")
            .insert(name.to_string(), tensor.clone());
        Ok(tensor)
    }

    fn get_unchecked(
        &self,
        name: &str,
        _dtype: DType,
        _device: &Device,
    ) -> candle_core::Result<Tensor> {
        candle_core::bail!("no shape for {name}")
    }

    fn contains_tensor(&self, _name: &str) -> bool {
        true
    }
}

fn pseudo_random(name: &str, index: usize) -> f32 {
    let mut hasher = Sha256::new();
    hasher.update(name.as_bytes());
    hasher.update((index as u64).to_le_bytes());
    let digest = hasher.finalize();
    let value = u32::from_le_bytes(digest[..4].try_into().expect("4 bytes"));
    (value as f32 / u32::MAX as f32 - 0.5) * 0.4
}
