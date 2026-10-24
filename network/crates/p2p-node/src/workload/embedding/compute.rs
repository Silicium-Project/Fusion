//! Computing and checking the vectors of a fragment.
//!
//! A fragment is a byte range of whole passage lines of the corpus. The
//! worker embeds all its passages and publishes a vector block; a verifier
//! checks the block's shape and unit vectors, then recomputes the passages
//! drawn from its acceptance seed
//! ([`silicium_embedding::sampling`]) and compares them by cosine
//! similarity with the model's threshold.

use super::{Embedding, runtime};
use crate::{
    processing::NodeContext, results::CONTENT_SCHEME, task::NetworkTask, workload::ComputeOutcome,
};
use silicium_embedding::{
    corpus::{self, DocumentEntry, PassageRecord},
    encoder::Encoder,
    model::ModelSpec,
    sampling::{sample_indices, sample_size},
    vectors::{VectorBlock, cosine},
};
use silicium_node_core::taskbook::ResultState;
use std::sync::Arc;

/// Computes the vectors of `task`'s passages into its output path.
pub(super) async fn execute(
    workload: &'static Embedding,
    context: &NodeContext,
    task: &NetworkTask,
) -> Option<ComputeOutcome> {
    let encoder = ready_encoder(workload, context, &task.task_id)?;
    let (documents, passages) = local_passages(context, task)
        .map_err(|err| println!(" Passages of {} unreadable: {err}", task.task_id))
        .ok()?;
    let first_id = passages.first()?.id;
    let dimension = workload.model.dimension;
    let computed = tokio::task::spawn_blocking(move || {
        let inputs: Vec<_> = passages
            .iter()
            .map(|passage| passage.embedding_input(&documents))
            .collect();
        let texts: Vec<&str> = inputs.iter().map(String::as_str).collect();
        let vectors = encoder.embed_passages(&texts)?;
        Ok::<_, silicium_embedding::Error>(
            VectorBlock::new(dimension, first_id, &vectors)?.to_bytes(),
        )
    })
    .await;
    let bytes = match computed {
        Ok(Ok(bytes)) => bytes,
        Ok(Err(err)) => {
            println!(" Vectors of {} not computed: {err}", task.task_id);
            return None;
        }
        Err(err) => {
            println!(" Vector task of {} failed: {err}", task.task_id);
            return None;
        }
    };
    let output = context.content.absolute(&task.output_path);
    if let Err(err) = crate::jobs::store::write_atomic(&output, &bytes) {
        println!(" Could not write the vectors of {}: {err}", task.task_id);
        return None;
    }
    Some(ComputeOutcome {
        milestones: Vec::new(),
    })
}

/// Verdict on another node's vectors for `task`, or `None` when the check
/// could not run here (model not ready, result or corpus unavailable).
pub(super) async fn verify(
    workload: &'static Embedding,
    context: &NodeContext,
    task: &NetworkTask,
    result: &ResultState,
    seed: &str,
) -> Option<bool> {
    let encoder = ready_encoder(workload, context, &task.task_id)?;
    let (documents, passages) = local_passages(context, task).ok()?;
    let first_id = passages.first()?.id;
    let sha256 = result.result.uri.strip_prefix(CONTENT_SCHEME)?;
    if !context.content.ensure(sha256).await {
        println!(" Vectors of {} not downloaded; no verdict", task.task_id);
        return None;
    }
    let bytes = context.content.get(sha256)?;
    let block = match checked_block(workload.model, &bytes, first_id, passages.len() as u64) {
        Ok(block) => block,
        Err(err) => {
            println!(" Vectors of {} rejected: {err}", task.task_id);
            return Some(false);
        }
    };
    let picks = sample_indices(seed, passages.len(), sample_size(passages.len()));
    let threshold = workload.model.min_verification_cosine;
    let checked = tokio::task::spawn_blocking(move || {
        recompute_agrees(&encoder, &documents, &passages, &block, &picks, threshold)
    })
    .await;
    match checked {
        Ok(Ok(agrees)) => Some(agrees),
        Ok(Err(err)) => {
            println!(" Could not recompute vectors of {}: {err}", task.task_id);
            None
        }
        Err(_) => None,
    }
}

/// The vector block `bytes` if it holds unit vectors of `model` for the
/// passages `first_id..first_id + count`.
pub(super) fn checked_block(
    model: &ModelSpec,
    bytes: &[u8],
    first_id: u64,
    count: u64,
) -> Result<VectorBlock, silicium_embedding::Error> {
    let block = VectorBlock::parse(bytes)?;
    block.check_shape(model.dimension, first_id, count)?;
    block.check_unit()?;
    Ok(block)
}

/// True when every picked passage, recomputed here, is within `threshold`
/// cosine of the published vector.
fn recompute_agrees(
    encoder: &Encoder,
    documents: &[DocumentEntry],
    passages: &[PassageRecord],
    block: &VectorBlock,
    picks: &[usize],
    threshold: f32,
) -> silicium_embedding::Result<bool> {
    let inputs: Vec<_> = picks
        .iter()
        .map(|&index| passages[index].embedding_input(documents))
        .collect();
    let texts: Vec<&str> = inputs.iter().map(String::as_str).collect();
    let expected = encoder.embed_passages(&texts)?;
    Ok(picks.iter().zip(&expected).all(|(&index, expected)| {
        block
            .vector(index)
            .is_some_and(|published| cosine(expected, published) >= threshold)
    }))
}

/// The model, when ready; logs why not otherwise.
fn ready_encoder(
    workload: &'static Embedding,
    context: &NodeContext,
    task_id: &str,
) -> Option<Arc<Encoder>> {
    match runtime::encoder(workload, &context.data_dir) {
        runtime::Readiness::Ready(encoder) => Some(encoder),
        runtime::Readiness::Preparing => {
            println!(" Model for {task_id} still preparing");
            None
        }
        runtime::Readiness::Unavailable(error) => {
            println!(" Model for {task_id} unavailable: {error}");
            None
        }
    }
}

/// The documents of the corpus and the passages of `task`, read from the
/// local copy of the corpus.
fn local_passages(
    context: &NodeContext,
    task: &NetworkTask,
) -> Result<(Vec<DocumentEntry>, Vec<PassageRecord>), String> {
    let range = task.byte_range.ok_or("task without passage range")?;
    let corpus_bytes =
        std::fs::read(context.content.absolute(&task.scene_path)).map_err(|err| err.to_string())?;
    let (header, _) = corpus::read_header(&corpus_bytes).map_err(|err| err.to_string())?;
    let passages =
        corpus::read_range(&corpus_bytes, range.start, range.end).map_err(|err| err.to_string())?;
    if passages.is_empty() {
        return Err("empty passage range".into());
    }
    Ok((header.documents, passages))
}
