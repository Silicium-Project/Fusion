//! Running and checking the items of a fragment.
//!
//! The worker sends its items to the AI runtime and publishes the outputs.
//! A verifier checks the ids and the shape of the published answers, then
//! runs the items drawn from its acceptance seed again and compares the
//! outputs with the task's metric ([`super::compare`]).

use super::{
    Hf,
    batch::{self, Answer, Header, Item},
    compare,
    runtime::{self, Runtime},
};
use crate::{
    processing::NodeContext, results::CONTENT_SCHEME, task::NetworkTask, workload::ComputeOutcome,
};
use silicium_embedding::sampling::{sample_indices, sample_size};
use silicium_node_core::taskbook::ResultState;

/// Runtime and model of `task`, when both are ready here.
async fn ready(workload: &Hf, context: &NodeContext, header: &Header) -> Option<Runtime> {
    let runtime = runtime::runtime_for(workload.task).await?;
    runtime::ensure_model(&runtime, &header.model, &context.data_dir)
        .await
        .then_some(runtime)
}

fn seed_of(task: &NetworkTask) -> u64 {
    task.seed.trim().parse().unwrap_or(0)
}

/// Answers the items of `task` into its output path.
pub(super) async fn execute(
    workload: &Hf,
    context: &NodeContext,
    task: &NetworkTask,
) -> Option<ComputeOutcome> {
    let (header, items) = local_items(workload, context, task)
        .map_err(|err| println!(" Items of {} unreadable: {err}", task.task_id))
        .ok()?;
    let Some(runtime) = ready(workload, context, &header).await else {
        println!(" Model for {} not ready", task.task_id);
        return None;
    };
    let dir = runtime::model_dir(&context.data_dir, &header.model.key);
    let started = std::time::Instant::now();
    let outputs = match runtime
        .run(
            &dir,
            &header.model,
            &header.parameters,
            seed_of(task),
            &items,
        )
        .await
    {
        Ok(outputs) => outputs,
        Err(err) => {
            println!(" Items of {} not computed: {err}", task.task_id);
            return None;
        }
    };
    println!(
        " Ran {} items of {} in {:.1} s",
        items.len(),
        task.task_id,
        started.elapsed().as_secs_f64()
    );
    let answers: Vec<Answer> = items
        .iter()
        .zip(outputs)
        .map(|(item, output)| Answer {
            id: item.id,
            output,
        })
        .collect();
    let bytes = batch::answers_to_bytes(&answers)
        .map_err(|err| println!(" Answers of {} not written: {err}", task.task_id))
        .ok()?;
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
/// could not run here.
pub(super) async fn verify(
    workload: &Hf,
    context: &NodeContext,
    task: &NetworkTask,
    result: &ResultState,
    seed: &str,
) -> Option<bool> {
    let (header, items) = local_items(workload, context, task).ok()?;
    let metric = compare::metric(workload.task)?;
    let runtime = ready(workload, context, &header).await?;
    let sha256 = result.result.uri.strip_prefix(CONTENT_SCHEME)?;
    if !context.content.ensure(sha256).await {
        println!(" Answers of {} not downloaded; no verdict", task.task_id);
        return None;
    }
    let bytes = context.content.get(sha256)?;
    let published = match batch::parse_answers(&bytes, items[0].id, items.len() as u64) {
        Ok(published) => published,
        Err(err) => {
            println!(" Answers of {} rejected: {err}", task.task_id);
            return Some(false);
        }
    };
    let picks = sample_indices(seed, items.len(), sample_size(items.len()));
    let sample: Vec<Item> = picks.iter().map(|&index| items[index].clone()).collect();
    let dir = runtime::model_dir(&context.data_dir, &header.model.key);
    let expected = match runtime
        .run(
            &dir,
            &header.model,
            &header.parameters,
            seed_of(task),
            &sample,
        )
        .await
    {
        Ok(outputs) => outputs,
        Err(err) => {
            println!(" Could not run the sample of {} again: {err}", task.task_id);
            return None;
        }
    };
    let scores: Vec<f64> = picks
        .iter()
        .zip(&expected)
        .map(|(&index, output)| metric.similarity(&published[index].output, output))
        .collect();
    let agrees = metric.accept(&scores);
    if !agrees {
        println!(
            " Answers of {} differ from the run again: {scores:?}",
            task.task_id
        );
    }
    Some(agrees)
}

/// The header of the batch and the items of `task`, from the local copy.
pub(super) fn local_items(
    workload: &Hf,
    context: &NodeContext,
    task: &NetworkTask,
) -> Result<(Header, Vec<Item>), String> {
    let range = task.byte_range.ok_or("task without item range")?;
    let bytes =
        std::fs::read(context.content.absolute(&task.scene_path)).map_err(|err| err.to_string())?;
    let (header, _) = batch::read_header(&bytes)?;
    workload.check_header(&header)?;
    let items = batch::read_range(&bytes, range.start, range.end)?;
    if items.is_empty() {
        return Err("empty item range".into());
    }
    Ok((header, items))
}
