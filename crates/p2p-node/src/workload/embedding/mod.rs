//! The document-search workload (`ai/embedding/<model>`): the passages of
//! the documents a person submitted are turned into vectors by the
//! network, then searched by meaning. The formats, the model and the
//! search live in the `silicium-embedding` crate; this module is the
//! network side:
//!
//! - **publisher**: turns the submitted files into a corpus
//!   ([`prepare`], in a child process), splits it into fragments of whole
//!   passages, then assembles the index from the fragments' vectors;
//! - **worker**: gets the pinned model once ([`runtime`]: download, hash
//!   check, kept in memory while used), claims a fragment only once the
//!   model is ready, and publishes the vectors of its passages
//!   ([`compute`]);
//! - **verifier**: recomputes a few passages drawn from the publisher's
//!   acceptance and compares by cosine similarity, since two honest CPUs
//!   differ by rounding;
//! - **search**: the publisher answers queries over assembled indexes
//!   ([`search`], `POST /v1/embedding/search`).
//!
//! The workload identifier names the model: a new model is a new workload,
//! so vectors of different models are never mixed.

mod compute;
pub(crate) mod prepare;
pub(crate) mod runtime;
pub(crate) mod search;

use super::{ComputeOutcome, OutputFile, PublishedOutput, Workload};
use crate::{
    jobs::{FragmentRef, ItemRange, JobManifest, JobSettings, fragment_task_id},
    processing::NodeContext,
    task::NetworkTask,
};
use futures::future::BoxFuture;
use silicium_embedding::{
    corpus, index,
    model::{self, ModelSpec},
    vectors::VectorBlock,
};
use silicium_node_core::{
    p2p::{ByteRange, TaskEnvelope},
    taskbook::{MilestoneSample, ResultState},
};
use std::path::Path;

/// Passages per fragment when the BackEnd asks for no count
/// (`SILICIUM_EMBEDDING_PASSAGES_PER_FRAGMENT`).
const DEFAULT_PASSAGES_PER_FRAGMENT: usize = 128;

/// Where a workload's model comes from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ModelSource {
    /// Downloaded once into the model store, checked against its hashes.
    Download,
    /// Built in memory (the tiny test model).
    #[cfg(any(test, feature = "test-model"))]
    Builtin,
}

/// A document-search workload: one pinned model.
pub(crate) struct Embedding {
    pub(crate) id: &'static str,
    pub(crate) model: &'static ModelSpec,
    pub(crate) source: ModelSource,
}

/// `ai/embedding/multilingual-e5-small`, the workload the site submits.
pub(crate) static MULTILINGUAL_E5_SMALL: Embedding = Embedding {
    id: "ai/embedding/multilingual-e5-small",
    model: &model::MULTILINGUAL_E5_SMALL,
    source: ModelSource::Download,
};

/// `ai/embedding/test-tiny`: the same workload with a tiny model built in
/// memory, for tests and the local end-to-end check.
#[cfg(any(test, feature = "test-model"))]
pub(crate) static TEST_TINY: Embedding = Embedding {
    id: "ai/embedding/test-tiny",
    model: &silicium_embedding::testing::TINY,
    source: ModelSource::Builtin,
};

/// The index files, written in this order (the manifest last: it marks the
/// job done for the BackEnd).
const OUTPUTS: &[PublishedOutput] = &[
    PublishedOutput {
        extension: "passages.jsonl",
        target: "index/passages.jsonl",
        summary_keys: &["passages_path"],
    },
    PublishedOutput {
        extension: "vectors.f32",
        target: "index/vectors.f32",
        summary_keys: &["vectors_path"],
    },
    PublishedOutput {
        extension: "index.json",
        target: "index/index.json",
        summary_keys: &["index_path", "result_path"],
    },
];

impl Workload for Embedding {
    fn id(&self) -> &'static str {
        self.id
    }

    fn storage_dir(&self) -> &'static str {
        "embedding"
    }

    fn fragment_extension(&self) -> &'static str {
        "vec"
    }

    fn published_outputs(&self) -> &'static [PublishedOutput] {
        OUTPUTS
    }

    fn prepare_input(&self, submitted: &Path) -> Result<Option<Vec<u8>>, String> {
        prepare::prepare(submitted).map(Some)
    }

    fn requires_split(&self) -> bool {
        true
    }

    fn ensure_ready<'a>(&'a self, context: &'a NodeContext) -> BoxFuture<'a, bool> {
        let ready = runtime::encoder(self.as_static(), &context.data_dir).is_ready();
        Box::pin(async move { ready })
    }

    fn split(
        &self,
        task: &NetworkTask,
        input: &Path,
        settings: &JobSettings,
    ) -> Option<(JobManifest, Vec<NetworkTask>)> {
        if task.byte_range.is_some() {
            return None;
        }
        let bytes = std::fs::read(input).ok()?;
        if bytes.len() as u64 > ByteRange::MAX_END {
            return None;
        }
        let plans = corpus::plan_fragments(
            &bytes,
            passages_per_fragment(),
            settings.max_fragments,
            task.requested_fragment_count,
        )
        .map_err(|err| println!(" Corpus of {} not split: {err}", task.task_id))
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
        compute::checked_block(self.model, bytes, items.first, items.count).is_ok()
    }

    fn assemble(
        &self,
        job: &JobManifest,
        input: &Path,
        fragments: &[Vec<u8>],
    ) -> Result<Vec<OutputFile>, String> {
        let corpus_bytes = std::fs::read(input).map_err(|err| format!("corpus: {err}"))?;
        let blocks = fragments
            .iter()
            .map(|bytes| VectorBlock::parse(bytes).map_err(|err| err.to_string()))
            .collect::<Result<Vec<_>, _>>()?;
        if blocks.len() != job.fragments.len() {
            return Err("missing fragment".to_string());
        }
        let files =
            index::assemble(&corpus_bytes, &blocks, self.model).map_err(|err| err.to_string())?;
        Ok(vec![
            OutputFile {
                extension: "passages.jsonl",
                bytes: files.passages,
            },
            OutputFile {
                extension: "vectors.f32",
                bytes: files.vectors,
            },
            OutputFile {
                extension: "index.json",
                bytes: files.manifest,
            },
        ])
    }
}

impl Embedding {
    /// This workload as the static it is declared as (the model runtime
    /// keeps models by workload for the life of the process).
    fn as_static(&self) -> &'static Embedding {
        find(self.id).expect("every document-search workload is a static listed in find")
    }
}

/// The document-search workload `id`, when `id` is one.
pub(crate) fn find(id: &str) -> Option<&'static Embedding> {
    let all: &[&'static Embedding] = &[
        &MULTILINGUAL_E5_SMALL,
        #[cfg(any(test, feature = "test-model"))]
        &TEST_TINY,
    ];
    all.iter().copied().find(|workload| workload.id == id)
}

fn passages_per_fragment() -> usize {
    std::env::var("SILICIUM_EMBEDDING_PASSAGES_PER_FRAGMENT")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_PASSAGES_PER_FRAGMENT)
}

#[cfg(test)]
mod tests;
