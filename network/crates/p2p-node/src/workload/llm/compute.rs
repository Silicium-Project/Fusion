//! Answering and checking the items of a fragment.
//!
//! A fragment is a byte range of whole item lines of the batch. The worker
//! answers all its items and publishes the answers; a verifier checks their
//! ids and shape, then recomputes the items drawn from its acceptance seed
//! and compares the answers by similarity
//! ([`silicium_llm::similarity`]).

use super::{Llm, runtime};
use crate::{
    processing::NodeContext, results::CONTENT_SCHEME, task::NetworkTask, workload::ComputeOutcome,
};
use silicium_embedding::sampling::sample_indices;
use silicium_llm::{
    answers,
    batch::{self, BatchHeader, Item},
    compute,
    similarity::{Thresholds, answer_similarity, sample_size},
};
use silicium_node_core::taskbook::ResultState;

/// Answers the items of `task` into its output path.
pub(super) async fn execute(
    workload: &'static Llm,
    context: &NodeContext,
    task: &NetworkTask,
) -> Option<ComputeOutcome> {
    let Some(ollama) = runtime::client(workload, &context.data_dir).await else {
        println!(" Model for {} not ready", task.task_id);
        return None;
    };
    let (header, items) = local_items(workload, context, task)
        .map_err(|err| println!(" Items of {} unreadable: {err}", task.task_id))
        .ok()?;
    let started = std::time::Instant::now();
    let answers = match compute::answer_all(&ollama, workload.model, &header, &items).await {
        Ok(answers) => answers,
        Err(err) => {
            println!(" Answers of {} not computed: {err}", task.task_id);
            return None;
        }
    };
    println!(
        " Answered {} items of {} in {:.1} s",
        answers.len(),
        task.task_id,
        started.elapsed().as_secs_f64()
    );
    let bytes = answers::to_bytes(&answers).ok()?;
    let output = context.content.absolute(&task.output_path);
    if let Err(err) = crate::jobs::store::write_atomic(&output, &bytes) {
        println!(" Could not write the answers of {}: {err}", task.task_id);
        return None;
    }
    Some(ComputeOutcome {
        milestones: Vec::new(),
    })
}

/// Verdict on another node's answers for `task`, or `None` when the check
/// could not run here (Ollama or the model not ready, result or batch
/// unavailable, a generation failed).
pub(super) async fn verify(
    workload: &'static Llm,
    context: &NodeContext,
    task: &NetworkTask,
    result: &ResultState,
    seed: &str,
) -> Option<bool> {
    let ollama = runtime::client(workload, &context.data_dir).await?;
    let (header, items) = local_items(workload, context, task).ok()?;
    let sha256 = result.result.uri.strip_prefix(CONTENT_SCHEME)?;
    if !context.content.ensure(sha256).await {
        println!(" Answers of {} not downloaded; no verdict", task.task_id);
        return None;
    }
    let bytes = context.content.get(sha256)?;
    let published = match answers::check(
        &bytes,
        items[0].id,
        items.len() as u64,
        &header.output,
        header.max_tokens,
    ) {
        Ok(published) => published,
        Err(err) => {
            println!(" Answers of {} rejected: {err}", task.task_id);
            return Some(false);
        }
    };
    let picks = sample_indices(seed, items.len(), sample_size(&header.output, items.len()));
    let mut scores = Vec::with_capacity(picks.len());
    for index in picks {
        let expected = match compute::answer(&ollama, workload.model, &header, &items[index]).await
        {
            Ok(answer) => answer,
            Err(err) => {
                println!(" Could not recompute an answer of {}: {err}", task.task_id);
                return None;
            }
        };
        scores.push(answer_similarity(
            &header.output,
            &published[index].output,
            &expected.output,
        ));
    }
    let agrees = Thresholds::for_output(&header.output).accept(&scores);
    if !agrees {
        println!(
            " Answers of {} differ from recomputation: {scores:?}",
            task.task_id
        );
    }
    Some(agrees)
}

/// The header of the batch and the items of `task`, read from the local
/// copy of the batch.
fn local_items(
    workload: &Llm,
    context: &NodeContext,
    task: &NetworkTask,
) -> Result<(BatchHeader, Vec<Item>), String> {
    let range = task.byte_range.ok_or("task without item range")?;
    let bytes =
        std::fs::read(context.content.absolute(&task.scene_path)).map_err(|err| err.to_string())?;
    let (header, _) = batch::read_header(&bytes).map_err(|err| err.to_string())?;
    if header.model != workload.model.id {
        return Err(format!(
            "batch for model {}, not {}",
            header.model, workload.model.id
        ));
    }
    let items = batch::read_range(&bytes, range.start, range.end).map_err(|err| err.to_string())?;
    if items.is_empty() {
        return Err("empty item range".into());
    }
    Ok((header, items))
}
