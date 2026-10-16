//! The batch AI workload (`ai/llm/<model>`, "Traitement par IA"): one
//! instruction applied to every item of a list by a pinned language model
//! that Ollama runs on the workers. The formats, the prompt, the checks and
//! the Ollama client live in the `silicium-llm` crate; this module is the
//! network side:
//!
//! - **publisher**: checks the request and turns it into the canonical
//!   batch (`prepare_input`), splits it into fragments of whole items, then
//!   assembles the answers into `answers.jsonl`, `answers.csv` and
//!   `result.json`;
//! - **worker**: claims a fragment only when Ollama answers and holds the
//!   pinned model ([`runtime`]: download, hash check, import), then answers
//!   its items one by one ([`compute`]);
//! - **verifier**: recomputes a few items drawn from the publisher's
//!   acceptance and compares the answers by similarity, since two honest
//!   machines can round differently.
//!
//! A node without Ollama (`SILICIUM_OLLAMA_URL` unset or unreachable) never
//! claims nor verifies these tasks; the other workloads are unaffected.
//!
//! The workload identifier names the model: a new model is a new workload,
//! so answers of two models are never mixed in one job.

mod compute;
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
use silicium_llm::{
    answers, batch,
    model::{self, LlmModel},
    request::Request,
    result::{self, FragmentAnswers},
};
use silicium_node_core::{
    p2p::{ByteRange, TaskEnvelope},
    taskbook::{MilestoneSample, ResultState, TaskTerms},
};
use std::{io::Read, path::Path};

/// Items per fragment when the BackEnd asks for no count
/// (`SILICIUM_LLM_ITEMS_PER_FRAGMENT`): a few minutes of a desktop CPU.
const DEFAULT_ITEMS_PER_FRAGMENT: usize = 8;
/// Most fragments of a job (`SILICIUM_LLM_MAX_FRAGMENTS`, at most 256).
const DEFAULT_MAX_FRAGMENTS: usize = 128;
/// Largest request read from the BackEnd.
const MAX_REQUEST_BYTES: u64 = 32 << 20;
/// Lease of an attempt: answering a fragment on a CPU takes minutes, and a
/// verifier recomputes a few items within one lease.
const LEASE_MS: u64 = 5 * 60_000;
const MAX_RENEWALS: u32 = 12;

/// A batch AI workload: one pinned model.
pub(crate) struct Llm {
    pub(crate) id: &'static str,
    pub(crate) model: &'static LlmModel,
}

/// `ai/llm/qwen2.5-1.5b-instruct`, the workload the site submits.
pub(crate) static QWEN2_5_1_5B_INSTRUCT: Llm = Llm {
    id: "ai/llm/qwen2.5-1.5b-instruct",
    model: &model::QWEN2_5_1_5B_INSTRUCT,
};

/// Bytes of the test model's "weights" (the fake Ollama does not read them).
#[cfg(any(test, feature = "test-ollama"))]
const TEST_GGUF: &[u8] = b"Silicium test GGUF: not a model.";

/// The test model: its file is written from memory, never downloaded.
#[cfg(any(test, feature = "test-ollama"))]
static TEST_MODEL: LlmModel = LlmModel {
    id: "test-tiny",
    repository: "silicium/test-tiny",
    revision: "0000000000000000000000000000000000000000",
    weights: model::GgufFile {
        name: "test-tiny.gguf",
        sha256: "ddf78175561bbb3789d88f324b4a8ca496109e025fe2441dcf85cdbee85978b3",
        size: 32,
    },
    licence: "none",
    ..model::QWEN2_5_1_5B_INSTRUCT
};

/// `ai/llm/test-tiny`: the same workload with the test model, answered by
/// the fake Ollama of `silicium-llm` (tests and the local end-to-end check,
/// never released).
#[cfg(any(test, feature = "test-ollama"))]
pub(crate) static TEST_TINY: Llm = Llm {
    id: "ai/llm/test-tiny",
    model: &TEST_MODEL,
};

/// The weights of `workload` when they are built in (the test model).
#[cfg(any(test, feature = "test-ollama"))]
fn test_model_bytes(workload: &Llm) -> Option<&'static [u8]> {
    (workload.id == TEST_TINY.id).then_some(TEST_GGUF)
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
        extension: "answers.csv",
        target: "answers/answers.csv",
        summary_keys: &["table_path"],
    },
    PublishedOutput {
        extension: "result.json",
        target: "answers/result.json",
        summary_keys: &["result_path"],
    },
];

impl Workload for Llm {
    fn id(&self) -> &'static str {
        self.id
    }

    fn storage_dir(&self) -> &'static str {
        "llm"
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
            return Err("La demande est trop grosse : envoie-la en plusieurs fois.".into());
        }
        let request = Request::parse(&bytes).map_err(|err| match err.user_message() {
            Some(message) => message.to_string(),
            None => "La demande n'a pas pu être lue.".to_string(),
        })?;
        batch::build(&request, self.model.id)
            .map(Some)
            .map_err(|_| "La demande n'a pas pu être préparée.".to_string())
    }

    fn requires_split(&self) -> bool {
        true
    }

    fn ensure_ready<'a>(&'a self, context: &'a NodeContext) -> BoxFuture<'a, bool> {
        Box::pin(async move {
            runtime::client(self.as_static(), &context.data_dir)
                .await
                .is_some()
        })
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
        let plans = batch::plan_fragments(
            &bytes,
            items_per_fragment(),
            max_fragments(),
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
            let items = ItemRange {
                first: plan.first_id,
                count: plan.count,
            };
            fragments.push(FragmentRef::items(task_id, range, items));
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
        Box::pin(compute::execute(self.as_static(), context, task))
    }

    fn verify<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
        result: &'a ResultState,
        seed: &'a str,
    ) -> BoxFuture<'a, Option<bool>> {
        Box::pin(compute::verify(
            self.as_static(),
            context,
            task,
            result,
            seed,
        ))
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
        answers::parse(bytes, items.first, items.count).is_ok()
    }

    fn assemble(
        &self,
        job: &JobManifest,
        input: &Path,
        fragments: &[Vec<u8>],
    ) -> Result<Vec<OutputFile>, String> {
        let batch_bytes = std::fs::read(input).map_err(|err| format!("batch: {err}"))?;
        if fragments.len() != job.fragments.len() {
            return Err("missing fragment".to_string());
        }
        let answers = job
            .fragments
            .iter()
            .zip(fragments)
            .map(|(fragment, bytes)| {
                let items = fragment.items.ok_or("fragment without items")?;
                Ok(FragmentAnswers {
                    bytes,
                    first_id: items.first,
                    count: items.count,
                })
            })
            .collect::<Result<Vec<_>, String>>()?;
        let files =
            result::assemble(&batch_bytes, &answers, self.model).map_err(|err| err.to_string())?;
        Ok(vec![
            OutputFile {
                extension: "answers.jsonl",
                bytes: files.answers,
            },
            OutputFile {
                extension: "answers.csv",
                bytes: files.csv,
            },
            OutputFile {
                extension: "result.json",
                bytes: files.manifest,
            },
        ])
    }
}

impl Llm {
    /// This workload as the static it is declared as (the runtime keeps its
    /// state by workload for the life of the process).
    fn as_static(&self) -> &'static Llm {
        find(self.id).expect("every batch AI workload is a static listed in find")
    }
}

/// The batch AI workload `id`, when `id` is one.
pub(crate) fn find(id: &str) -> Option<&'static Llm> {
    let all: &[&'static Llm] = &[
        &QWEN2_5_1_5B_INSTRUCT,
        #[cfg(any(test, feature = "test-ollama"))]
        &TEST_TINY,
    ];
    all.iter().copied().find(|workload| workload.id == id)
}

/// The answered items of a verified fragment, `{"id","input","output"}` per
/// line, for the progress page of the site; `None` when the answers or the
/// batch are unreadable.
pub(crate) fn fragment_preview(
    input: &Path,
    fragment: &FragmentRef,
    answers: &[u8],
) -> Option<Vec<u8>> {
    let range = fragment.byte_range?;
    let items_range = fragment.items?;
    let batch_bytes = std::fs::read(input).ok()?;
    let items = batch::read_range(&batch_bytes, range.start, range.end).ok()?;
    let answers = answers::parse(answers, items_range.first, items_range.count).ok()?;
    result::answers_jsonl(&items, &answers).ok()
}

fn items_per_fragment() -> usize {
    env_count("SILICIUM_LLM_ITEMS_PER_FRAGMENT").unwrap_or(DEFAULT_ITEMS_PER_FRAGMENT)
}

fn max_fragments() -> usize {
    env_count("SILICIUM_LLM_MAX_FRAGMENTS")
        .unwrap_or(DEFAULT_MAX_FRAGMENTS)
        .min(MAX_FRAGMENTS_LIMIT)
}

fn env_count(name: &str) -> Option<usize> {
    std::env::var(name)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .filter(|value| *value > 0)
}

#[cfg(test)]
mod tests;
