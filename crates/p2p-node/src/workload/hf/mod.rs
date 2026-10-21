//! The Hugging Face workload (`ai/hf/<task>/<model key>`, "Catalogue IA"):
//! a task of the Hub applied to every item of a list, by a model of the
//! BackEnd's catalogue, run by the Silicium AI runtime on the workers.
//!
//! The code knows the tasks ([`compare::TASKS`]), never a model: the model
//! comes with the job as a manifest (repository, commit, files and their
//! hashes, how to load it), which every node checks ([`manifest`]).
//!
//! - **publisher**: checks the request and turns it into the canonical batch
//!   (`prepare_input`), splits it into fragments of whole items, then
//!   assembles the answers (`answers.jsonl`, `result.json`);
//! - **worker**: claims a fragment only when the runtime runs the task and
//!   the model is prepared ([`runtime`]: download, hash check, load), then
//!   runs its items ([`compute`]);
//! - **verifier**: runs a few items drawn from the publisher's acceptance
//!   again and compares the outputs with the task's metric ([`compare`]).
//!
//! A node without the runtime (`SILICIUM_AI_RUNTIME_URL` unset or
//! unreachable) never claims nor verifies these tasks; the other workloads,
//! including the batch AI (`ai/llm/…`) and document search
//! (`ai/embedding/…`) ones, are unaffected.
//!
//! Each workload identifier names one model: a [`Hf`] is made the first
//! time an identifier is seen and kept for the life of the process.

mod batch;
pub(crate) mod canary;
mod compare;
mod compute;
pub(crate) mod manifest;
pub(crate) mod runtime;

use super::{ComputeOutcome, OutputFile, PublishedOutput, Workload};
use crate::{
    jobs::{
        FragmentRef, ItemRange, JobManifest, JobSettings, MAX_FRAGMENTS_LIMIT, fragment_task_id,
    },
    processing::NodeContext,
    task::NetworkTask,
};
use futures::future::BoxFuture;
use serde_json::json;
use silicium_node_core::{
    p2p::{ByteRange, TaskEnvelope},
    taskbook::{MilestoneSample, ResultState, TaskTerms},
};
use std::{
    collections::HashMap,
    io::Read,
    path::Path,
    sync::{LazyLock, Mutex},
};

pub(crate) use runtime::{model_faults, scan_warm_models, shared_store_root, warm_models};

/// Prefix of the workload identifiers.
pub(crate) const PREFIX: &str = "ai/hf/";
/// Items per fragment when the BackEnd asks for no count
/// (`SILICIUM_HF_ITEMS_PER_FRAGMENT`).
const DEFAULT_ITEMS_PER_FRAGMENT: usize = 16;
/// Most fragments of a job (`SILICIUM_HF_MAX_FRAGMENTS`, at most 256).
const DEFAULT_MAX_FRAGMENTS: usize = 128;
/// Largest request read from the BackEnd (the input is shared whole).
const MAX_REQUEST_BYTES: u64 = 60 << 20;
/// Lease of an attempt, renewable: a model download and a fragment on a CPU
/// take minutes.
const LEASE_MS: u64 = 5 * 60_000;
const MAX_RENEWALS: u32 = 12;
/// Identifiers kept by a process (each one is a small static).
const MAX_WORKLOADS: usize = 1024;

/// The workload of one model.
pub(crate) struct Hf {
    pub(crate) id: &'static str,
    pub(crate) task: &'static str,
    pub(crate) key: &'static str,
}

static WORKLOADS: LazyLock<Mutex<HashMap<String, &'static Hf>>> = LazyLock::new(Mutex::default);

/// The workload `id` when it is `ai/hf/<task>/<key>` with a task this node
/// runs and a well-formed key.
pub(crate) fn find(id: &str) -> Option<&'static Hf> {
    let rest = id.strip_prefix(PREFIX)?;
    let (task, key) = rest.split_once('/')?;
    let task = compare::TASKS.iter().find(|(known, _)| *known == task)?.0;
    let valid_key = (14..=120).contains(&key.len())
        && key.bytes().all(|b| {
            b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'.' | b'_' | b'-')
        });
    if !valid_key {
        return None;
    }
    let mut workloads = WORKLOADS.lock().ok()?;
    if let Some(workload) = workloads.get(id) {
        return Some(workload);
    }
    if workloads.len() >= MAX_WORKLOADS {
        return None;
    }
    let workload: &'static Hf = Box::leak(Box::new(Hf {
        id: Box::leak(id.to_string().into_boxed_str()),
        task,
        key: Box::leak(key.to_string().into_boxed_str()),
    }));
    workloads.insert(id.to_string(), workload);
    Some(workload)
}

/// The answer files, written in this order (the manifest last: it marks the
/// job done for the BackEnd).
const OUTPUTS: &[PublishedOutput] = &[
    PublishedOutput {
        extension: "answers.jsonl",
        target: "answers/answers.jsonl",
        summary_keys: &["answers_path"],
    },
    PublishedOutput {
        extension: "result.json",
        target: "answers/result.json",
        summary_keys: &["result_path"],
    },
];

impl Hf {
    /// A batch header is for this task and this model, and its manifest
    /// passes the checks.
    fn check_header(&self, header: &batch::Header) -> Result<(), String> {
        if header.task != self.task
            || header.model.task != self.task
            || header.model.key != self.key
        {
            return Err(format!(
                "batch for {}/{}, not {}",
                header.task, header.model.key, self.id
            ));
        }
        header.model.check()
    }
}

impl Workload for Hf {
    fn id(&self) -> &'static str {
        self.id
    }

    fn storage_dir(&self) -> &'static str {
        "hf"
    }

    fn fragment_extension(&self) -> &'static str {
        "jsonl"
    }

    fn published_outputs(&self) -> &'static [PublishedOutput] {
        OUTPUTS
    }

    fn terms(&self, base: TaskTerms) -> TaskTerms {
        TaskTerms {
            lease_ms: base.lease_ms.max(LEASE_MS),
            max_renewals: base.max_renewals.max(MAX_RENEWALS),
            ..base
        }
    }

    fn prepare_input(&self, submitted: &Path) -> Result<Option<Vec<u8>>, String> {
        let mut bytes = Vec::new();
        std::fs::File::open(submitted)
            .and_then(|file| file.take(MAX_REQUEST_BYTES + 1).read_to_end(&mut bytes))
            .map_err(|_| "La demande n'a pas pu être lue.".to_string())?;
        if bytes.len() as u64 > MAX_REQUEST_BYTES {
            return Err(
                "La demande est trop grosse (60 Mo au plus) : envoie-la en plusieurs fois.".into(),
            );
        }
        let (batch, canaries) = batch::build(&bytes, self.task, self.key)?;
        if !canaries.is_empty() {
            let sha256 = crate::content::sha256_hex(&batch);
            let plan = canary::new_plan(self.task, self.key, canaries);
            // Without its plan, the batch is still valid: the canaries are
            // then answered like any item, and not checked.
            if let Err(err) = canary::save_plan(&sha256, &plan) {
                println!(" Canaries of a {} batch not kept: {err}", self.task);
            }
        }
        Ok(Some(batch))
    }

    fn requires_split(&self) -> bool {
        true
    }

    fn ensure_ready<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
    ) -> BoxFuture<'a, bool> {
        Box::pin(async move {
            let Some(runtime) = runtime::runtime_for(self.task).await else {
                return false;
            };
            let header = match batch::read_header_file(&context.content.absolute(&task.scene_path))
                .and_then(|header| self.check_header(&header).map(|()| header))
            {
                Ok(header) => header,
                Err(err) => {
                    println!(" Model of {} refused: {err}", task.task_id);
                    return false;
                }
            };
            runtime::ensure_model(&runtime, &header.model, &context.data_dir).await
        })
    }

    fn is_warm(&self, _task: &NetworkTask) -> bool {
        runtime::is_warm(self.key)
    }

    fn split(
        &self,
        task: &NetworkTask,
        input: &Path,
        _settings: &JobSettings,
    ) -> Option<(JobManifest, Vec<NetworkTask>)> {
        if task.byte_range.is_some() {
            return None;
        }
        let bytes = std::fs::read(input).ok()?;
        if bytes.len() as u64 > ByteRange::MAX_END {
            return None;
        }
        let plans = batch::plan(
            &bytes,
            env_count("SILICIUM_HF_ITEMS_PER_FRAGMENT").unwrap_or(DEFAULT_ITEMS_PER_FRAGMENT),
            env_count("SILICIUM_HF_MAX_FRAGMENTS")
                .unwrap_or(DEFAULT_MAX_FRAGMENTS)
                .min(MAX_FRAGMENTS_LIMIT),
            task.requested_fragment_count,
        )
        .map_err(|err| println!(" Batch of {} not split: {err}", task.task_id))
        .ok()?;
        let mut fragments = Vec::with_capacity(plans.len());
        let mut tasks = Vec::with_capacity(plans.len());
        for (index, plan) in plans.into_iter().enumerate() {
            let task_id = fragment_task_id(&task.task_id, index);
            let range = ByteRange {
                start: plan.start,
                end: plan.end,
            };
            let mut fragment = task.clone();
            fragment.output_path = TaskEnvelope::local_output_path_for(&task_id, Some(self.id))?;
            fragment.task_id = task_id.clone();
            fragment.workload = Some(self.id.to_string());
            fragment.byte_range = Some(range);
            fragments.push(FragmentRef::items(
                task_id,
                range,
                ItemRange {
                    first: plan.first_id,
                    count: plan.count,
                },
            ));
            tasks.push(fragment);
        }
        let manifest = JobManifest {
            job_id: task.task_id.clone(),
            root_job_id: task
                .root_job_id
                .clone()
                .unwrap_or_else(|| task.task_id.clone()),
            workload: self.id.to_string(),
            width: 0,
            height: 0,
            input_bytes: bytes.len() as u64,
            scene_sha256: task.scene_sha256.clone(),
            fragments,
        };
        Some((manifest, tasks))
    }

    fn execute<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
    ) -> BoxFuture<'a, Option<ComputeOutcome>> {
        Box::pin(compute::execute(self, context, task))
    }

    fn verify<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
        result: &'a ResultState,
        seed: &'a str,
    ) -> BoxFuture<'a, Option<bool>> {
        Box::pin(compute::verify(self, context, task, result, seed))
    }

    fn accepts_result(
        &self,
        fragment: Option<&FragmentRef>,
        bytes: &[u8],
        _milestones: &[MilestoneSample],
    ) -> bool {
        let Some(items) = fragment.and_then(|fragment| fragment.items) else {
            return false;
        };
        batch::parse_answers(bytes, items.first, items.count).is_ok()
    }

    fn audit(&self, fragment: &FragmentRef, input: &Path, bytes: &[u8]) -> Option<String> {
        let plan = canary::plan_of(&input_sha256(input)?)?;
        let items = fragment.items?;
        let answers = batch::parse_answers(bytes, items.first, items.count).ok()?;
        canary::wrong_canary(&plan, &answers)
    }

    fn learn(&self, fragment: &FragmentRef, input: &Path, bytes: &[u8], checked: &[usize]) {
        let Some(plan) = input_sha256(input).and_then(|sha256| canary::plan_of(&sha256)) else {
            return;
        };
        let Some(items) = fragment.items else {
            return;
        };
        if let Ok(answers) = batch::parse_answers(bytes, items.first, items.count) {
            canary::learn(&plan, &answers, &canary::ids_at(items.first, checked));
        }
    }

    fn assemble(
        &self,
        job: &JobManifest,
        input: &Path,
        fragments: &[Vec<u8>],
    ) -> Result<Vec<OutputFile>, String> {
        if fragments.len() != job.fragments.len() {
            return Err("missing fragment".to_string());
        }
        let header = batch::read_header_file(input)?;
        self.check_header(&header)?;
        let mut answers = Vec::new();
        for (fragment, bytes) in job.fragments.iter().zip(fragments) {
            let items = fragment.items.ok_or("fragment without items")?;
            answers.extend(batch::parse_answers(bytes, items.first, items.count)?);
        }
        if answers.len() as u64 != header.item_count {
            return Err(format!(
                "{} answers for {} items",
                answers.len(),
                header.item_count
            ));
        }
        // The canaries are the publisher's: the user gets its items only.
        let answers = match input_sha256(input).and_then(|sha256| canary::plan_of(&sha256)) {
            Some(plan) => canary::strip(&plan, answers),
            None => answers,
        };
        let model = &header.model;
        let result = json!({
            "format": batch::RESULT_FORMAT,
            "task": header.task,
            "model": {
                "key": model.key,
                "repository": model.repository,
                "revision": model.revision,
                "licence": model.licence,
                "url": format!("https://huggingface.co/{}/tree/{}", model.repository, model.revision),
            },
            "item_count": answers.len(),
            "parameters": header.parameters,
        });
        Ok(vec![
            OutputFile {
                extension: "answers.jsonl",
                bytes: batch::answers_to_bytes(&answers)?,
            },
            OutputFile {
                extension: "result.json",
                bytes: serde_json::to_vec_pretty(&result).map_err(|err| err.to_string())?,
            },
        ])
    }
}

/// SHA-256 of the shared input, from its name in the content store
/// (`content/<sha256>`).
fn input_sha256(input: &Path) -> Option<String> {
    let name = input.file_name()?.to_str()?;
    crate::content::is_sha256(name).then(|| name.to_string())
}

fn env_count(name: &str) -> Option<usize> {
    std::env::var(name)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .filter(|value| *value > 0)
}

#[cfg(test)]
mod tests;
