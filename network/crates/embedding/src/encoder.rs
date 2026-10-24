//! The model: texts to unit vectors, on the CPU with Candle.
//!
//! Each text gets its prefix (`passage: ` or `query: `), is tokenized and
//! truncated to the model's input length, then the BERT encoder runs on a
//! batch of texts padded to the longest one. The vector of a text is the
//! mean of its token states (padding excluded), scaled to length 1, so that
//! the similarity of two texts is the dot product of their vectors.
//!
//! An [`Encoder`] is immutable once loaded and can be shared between
//! threads; loading the multilingual e5 model takes about half a gigabyte
//! of memory, so a process keeps one.

use crate::{
    Error, Result,
    model::{
        ModelSpec,
        store::{ModelPaths, verify_file},
    },
};
use candle_core::{DType, Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::bert::{BertModel, Config};
use tokenizers::{Tokenizer, TruncationParams};

/// Texts encoded per model call.
pub const BATCH_SIZE: usize = 16;

/// A loaded model.
pub struct Encoder {
    spec: ModelSpec,
    model: BertModel,
    tokenizer: Tokenizer,
    pad_id: u32,
    device: Device,
}

impl Encoder {
    /// Loads the model of `spec` from its files, after checking their
    /// hashes (a file changed on disk is refused).
    pub fn load(spec: &ModelSpec, paths: &ModelPaths) -> Result<Self> {
        verify_file(&paths.weights, &spec.weights)?;
        verify_file(&paths.tokenizer, &spec.tokenizer)?;
        let device = Device::Cpu;
        let tensors = candle_core::safetensors::load(&paths.weights, &device)?;
        let weights = VarBuilder::from_tensors(tensors, DType::F32, &device);
        let tokenizer = Tokenizer::from_file(&paths.tokenizer)
            .map_err(|err| Error::Model(format!("tokenizer: {err}")))?;
        Self::from_parts(spec, weights, tokenizer)
    }

    /// Builds an encoder from weights and a tokenizer already in memory.
    pub fn from_parts(
        spec: &ModelSpec,
        weights: VarBuilder,
        mut tokenizer: Tokenizer,
    ) -> Result<Self> {
        let config: Config = serde_json::from_value(spec.bert_config())
            .map_err(|err| Error::Model(format!("architecture: {err}")))?;
        let device = weights.device().clone();
        let model = BertModel::load(weights, &config)?;
        tokenizer
            .with_truncation(Some(TruncationParams {
                max_length: spec.max_tokens,
                ..Default::default()
            }))
            .map_err(|err| Error::Model(format!("tokenizer: {err}")))?;
        tokenizer.with_padding(None);
        let pad_id = tokenizer.token_to_id("<pad>").unwrap_or(0);
        Ok(Self {
            spec: *spec,
            model,
            tokenizer,
            pad_id,
            device,
        })
    }

    /// The model this encoder runs.
    pub fn spec(&self) -> &ModelSpec {
        &self.spec
    }

    /// Vectors of document passages.
    pub fn embed_passages(&self, texts: &[&str]) -> Result<Vec<Vec<f32>>> {
        self.embed_with_prefix(self.spec.passage_prefix, texts)
    }

    /// Vector of a search query.
    pub fn embed_query(&self, text: &str) -> Result<Vec<f32>> {
        let mut vectors = self.embed_with_prefix(self.spec.query_prefix, &[text])?;
        vectors
            .pop()
            .ok_or_else(|| Error::Compute("no vector for the query".into()))
    }

    fn embed_with_prefix(&self, prefix: &str, texts: &[&str]) -> Result<Vec<Vec<f32>>> {
        let mut vectors = Vec::with_capacity(texts.len());
        for batch in texts.chunks(BATCH_SIZE) {
            let inputs: Vec<String> = batch.iter().map(|text| format!("{prefix}{text}")).collect();
            vectors.extend(self.embed_batch(inputs)?);
        }
        Ok(vectors)
    }

    /// Runs the model on one batch.
    fn embed_batch(&self, inputs: Vec<String>) -> Result<Vec<Vec<f32>>> {
        let encodings = self
            .tokenizer
            .encode_batch(inputs, true)
            .map_err(|err| Error::Compute(format!("tokenize: {err}")))?;
        let batch = encodings.len();
        let length = encodings
            .iter()
            .map(|e| e.get_ids().len())
            .max()
            .unwrap_or(0)
            .max(1);
        let mut ids = Vec::with_capacity(batch * length);
        let mut mask = Vec::with_capacity(batch * length);
        for encoding in &encodings {
            let tokens = encoding.get_ids();
            ids.extend_from_slice(tokens);
            ids.extend(std::iter::repeat_n(self.pad_id, length - tokens.len()));
            mask.extend(std::iter::repeat_n(1u32, tokens.len()));
            mask.extend(std::iter::repeat_n(0u32, length - tokens.len()));
        }
        let ids = Tensor::from_vec(ids, (batch, length), &self.device)?;
        let mask = Tensor::from_vec(mask, (batch, length), &self.device)?;
        let token_types = ids.zeros_like()?;
        let states = self.model.forward(&ids, &token_types, Some(&mask))?;
        let pooled = mean_pool(&states, &mask)?;
        Ok(normalize(&pooled)?.to_vec2::<f32>()?)
    }
}

/// Mean of the token states of each text, padding excluded.
fn mean_pool(states: &Tensor, mask: &Tensor) -> candle_core::Result<Tensor> {
    let mask = mask.to_dtype(DType::F32)?.unsqueeze(2)?;
    let summed = states.broadcast_mul(&mask)?.sum(1)?;
    let counts = mask.sum(1)?.clamp(1e-9, f64::MAX)?;
    summed.broadcast_div(&counts)
}

/// Rows scaled to length 1.
fn normalize(rows: &Tensor) -> candle_core::Result<Tensor> {
    let norms = rows.sqr()?.sum_keepdim(1)?.sqrt()?.clamp(1e-12, f64::MAX)?;
    rows.broadcast_div(&norms)
}

#[cfg(test)]
pub(crate) mod tests;
