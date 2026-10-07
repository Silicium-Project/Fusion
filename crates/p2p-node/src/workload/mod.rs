//! Workloads: what a task computes. The task book, the scheduling, the
//! transfer of inputs and results, the verification protocol and the
//! BackEnd projections are the same for every workload; what differs is
//! behind the [`Workload`] trait:
//!
//! | Step | Who | Method |
//! | --- | --- | --- |
//! | turn the submitted file into the shared input (optional) | publisher | [`Workload::prepare_input`] |
//! | split a submitted task into fragments | publisher | [`Workload::split`] |
//! | get ready to run it (e.g. download a model) | worker, verifier | [`Workload::ensure_ready`] |
//! | compute a fragment | worker | [`Workload::execute`] |
//! | check another node's fragment | verifier | [`Workload::verify`] |
//! | check a downloaded fragment result | publisher | [`Workload::accepts_result`] |
//! | build the job result from the fragments | publisher | [`Workload::assemble`] |
//!
//! Adding a workload: write a module implementing [`Workload`] and add it to
//! [`REGISTRY`]. Its identifier travels with each task
//! (`TaskEnvelope::workload`); a node refuses tasks of a workload it does
//! not know.

pub(crate) mod embedding;
pub(crate) mod raytracer;
pub(crate) mod sha256;

use crate::{
    jobs::{FragmentRef, JobManifest, JobSettings},
    processing::NodeContext,
    task::NetworkTask,
};
use futures::future::BoxFuture;
use silicium_node_core::taskbook::{MilestoneSample, ResultState};
use std::path::Path;

/// A result computed by this node, with the commitment published with it.
pub(crate) struct ComputeOutcome {
    /// Commitment checked by verifiers and by the publisher (empty for
    /// workloads verified by recomputing the whole result).
    pub(crate) milestones: Vec<MilestoneSample>,
}

/// A file of a job's final result, written as `results/<job id>.<extension>`.
pub(crate) struct OutputFile {
    pub(crate) extension: &'static str,
    pub(crate) bytes: Vec<u8>,
}

/// Where the BackEnd finds a job's final result: the publisher copies
/// `results/<job id>.<extension>` to `<job dir>/<target>` and records the
/// path under `summary_key` in the job summary.
pub(crate) struct PublishedOutput {
    pub(crate) extension: &'static str,
    pub(crate) target: &'static str,
    pub(crate) summary_keys: &'static [&'static str],
}

/// One kind of computation (see the module documentation).
pub(crate) trait Workload: Send + Sync {
    /// Network identifier, e.g. `raytracer` or `calcul/integrity/sha256`.
    fn id(&self) -> &'static str;

    /// Directory of the job projections read by the BackEnd, under
    /// `SILICIUM_WORKLOAD_STORAGE_DIR`.
    fn storage_dir(&self) -> &'static str;

    /// Extension of a fragment result kept by the publisher
    /// (`results/<fragment id>.<extension>`).
    fn fragment_extension(&self) -> &'static str;

    /// Files of the final result, in the order [`Workload::assemble`]
    /// returns them; the last one is written last and marks the job done.
    fn published_outputs(&self) -> &'static [PublishedOutput];

    /// Turns the file submitted to the publisher into the input shared with
    /// the workers, or `Ok(None)` to share it as is (the default). Runs
    /// before the input is shared, on a blocking thread. The error is a
    /// message for the person who submitted the job.
    fn prepare_input(&self, _submitted: &Path) -> Result<Option<Vec<u8>>, String> {
        Ok(None)
    }

    /// True when this node can run the workload now. A workload that needs
    /// local resources (a model to download) starts getting them and answers
    /// false meanwhile: the node does not claim the task, and claims it when
    /// the publisher announces it again.
    fn ensure_ready<'a>(&'a self, _context: &'a NodeContext) -> BoxFuture<'a, bool> {
        Box::pin(async { true })
    }

    /// True when a task of this workload cannot run unsplit: a failed split
    /// then fails the job instead of publishing it whole.
    fn requires_split(&self) -> bool {
        false
    }

    /// Splits a submitted task whose input is the file `input` into fragment
    /// tasks. `None`: the task is published as a single task.
    fn split(
        &self,
        task: &NetworkTask,
        input: &Path,
        settings: &JobSettings,
    ) -> Option<(JobManifest, Vec<NetworkTask>)>;

    /// Computes `task` into its `output_path` (inside the work directory) and
    /// returns its commitment; `None` when it failed.
    fn execute<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
    ) -> BoxFuture<'a, Option<ComputeOutcome>>;

    /// Checks another node's `result` for `task`; `seed` is the publisher's
    /// acceptance of this verifier (unknown to the worker when it computed).
    /// `Some(verdict)`, or `None` when the check could not be run here (no
    /// verdict is then published).
    fn verify<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
        result: &'a ResultState,
        seed: &'a str,
    ) -> BoxFuture<'a, Option<bool>>;

    /// True when a downloaded fragment result (already checked against its
    /// SHA-256) matches the commitment the verifiers approved.
    fn accepts_result(
        &self,
        fragment: Option<&FragmentRef>,
        bytes: &[u8],
        milestones: &[MilestoneSample],
    ) -> bool;

    /// Builds the final result of `job` from its shared input (`input`) and
    /// its fragment results, in fragment order.
    fn assemble(
        &self,
        job: &JobManifest,
        input: &Path,
        fragments: &[Vec<u8>],
    ) -> Result<Vec<OutputFile>, String>;
}

/// Every workload this node can run.
#[cfg(not(any(test, feature = "test-model")))]
pub(crate) static REGISTRY: &[&dyn Workload] = &[
    &raytracer::Raytracer,
    &sha256::Sha256,
    &embedding::MULTILINGUAL_E5_SMALL,
];

/// With the tiny test model (tests and the local end-to-end check, never
/// released).
#[cfg(any(test, feature = "test-model"))]
pub(crate) static REGISTRY: &[&dyn Workload] = &[
    &raytracer::Raytracer,
    &sha256::Sha256,
    &embedding::MULTILINGUAL_E5_SMALL,
    &embedding::TEST_TINY,
];

/// Identifier of tasks that carry no workload (older publishers).
pub(crate) const DEFAULT_WORKLOAD: &str = "raytracer";

/// The workload `id`, also accepting the documented aliases.
pub(crate) fn find(id: &str) -> Option<&'static dyn Workload> {
    let id = match id.trim() {
        "" => DEFAULT_WORKLOAD,
        sha256::ALIAS => sha256::ID,
        other => other,
    };
    REGISTRY
        .iter()
        .copied()
        .find(|workload| workload.id() == id)
}

/// The workload of `task`.
pub(crate) fn of(task: &NetworkTask) -> Option<&'static dyn Workload> {
    find(task.workload.as_deref().unwrap_or(DEFAULT_WORKLOAD))
}

/// Identifiers of the known workloads, for error messages.
pub(crate) fn known_ids() -> String {
    REGISTRY
        .iter()
        .map(|workload| workload.id())
        .collect::<Vec<_>>()
        .join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workloads_are_found_by_id_and_alias() {
        assert_eq!(find("raytracer").unwrap().id(), "raytracer");
        assert_eq!(find("").unwrap().id(), "raytracer", "older tasks");
        assert_eq!(find(sha256::ID).unwrap().id(), sha256::ID);
        assert_eq!(find("calcul/hash/sha256").unwrap().id(), sha256::ID);
        assert!(find("calcul/unknown").is_none());
    }

    #[test]
    fn identifiers_are_unique_and_well_formed() {
        let ids: Vec<&str> = REGISTRY.iter().map(|workload| workload.id()).collect();
        let mut unique = ids.clone();
        unique.sort_unstable();
        unique.dedup();
        assert_eq!(unique.len(), ids.len());
        assert!(
            ids.iter()
                .all(|id| silicium_node_core::p2p::is_valid_workload_id(id))
        );
    }
}
