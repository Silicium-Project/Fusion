//! Jobs split into fragments: a task submitted through the API becomes a job
//! whose fragments are published as tasks `<job id>.f<NNN>`; how the input
//! is split depends on the workload ([`crate::workload::Workload::split`]:
//! image tiles for the raytracer, byte chunks for sha256). The job manifest
//! is kept in the work directory ([`store`]); once every fragment result is
//! collected, the publisher assembles the job result.

pub(crate) mod store;

use serde::{Deserialize, Serialize};
use silicium_node_core::p2p::{ByteRange, Region};
use silicium_raytracer::pipeline::tiles;

use crate::task::NetworkTask;

pub(crate) use store::JobStore;

/// Suffix of a fragment task id; its width is reserved in job ids.
pub(crate) const FRAGMENT_SUFFIX_EXAMPLE: &str = ".f000";
/// Upper bound on fragments per job (three-digit suffix).
pub(crate) const MAX_FRAGMENTS_LIMIT: usize = 256;

/// Default size of a byte chunk (`SILICIUM_TARGET_BYTES_PER_FRAGMENT`).
pub(crate) const DEFAULT_TARGET_BYTES_PER_FRAGMENT: usize = 4 * 1024 * 1024;

/// How jobs are split (`SILICIUM_MAX_FRAGMENTS`,
/// `SILICIUM_TARGET_PIXELS_PER_FRAGMENT`, `SILICIUM_TARGET_BYTES_PER_FRAGMENT`,
/// or a local requested count).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct JobSettings {
    pub(crate) max_fragments: usize,
    /// Pixels per image tile (raytracer).
    pub(crate) target_pixels: usize,
    /// Bytes per input chunk (workloads splitting a file).
    pub(crate) target_bytes: usize,
}

impl Default for JobSettings {
    fn default() -> Self {
        Self {
            max_fragments: tiles::DEFAULT_MAX_FRAGMENTS,
            target_pixels: tiles::DEFAULT_TARGET_PIXELS_PER_FRAGMENT,
            target_bytes: DEFAULT_TARGET_BYTES_PER_FRAGMENT,
        }
    }
}

impl JobSettings {
    pub(crate) fn from_env() -> Self {
        let read = |name: &str| {
            std::env::var(name)
                .ok()
                .and_then(|value| value.trim().parse::<usize>().ok())
                .filter(|value| *value > 0)
        };
        let defaults = Self::default();
        Self {
            max_fragments: read("SILICIUM_MAX_FRAGMENTS")
                .unwrap_or(defaults.max_fragments)
                .min(MAX_FRAGMENTS_LIMIT),
            target_pixels: read("SILICIUM_TARGET_PIXELS_PER_FRAGMENT")
                .unwrap_or(defaults.target_pixels),
            target_bytes: read("SILICIUM_TARGET_BYTES_PER_FRAGMENT")
                .unwrap_or(defaults.target_bytes),
        }
    }
}

/// One fragment of a job: the part of the input it covers.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct FragmentRef {
    pub(crate) task_id: String,
    /// Image tile (raytracer); empty for other workloads.
    #[serde(default = "empty_region")]
    pub(crate) region: Region,
    /// Input chunk (workloads splitting a file).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) byte_range: Option<ByteRange>,
    /// Items of the input in the chunk, for workloads whose input is a list
    /// (the passages of a document-search job).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) items: Option<ItemRange>,
}

/// Consecutive items `first..first + count` of a job's input.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct ItemRange {
    pub(crate) first: u64,
    pub(crate) count: u64,
}

fn empty_region() -> Region {
    Region {
        x_start: 0,
        x_end: 0,
        y_start: 0,
        y_end: 0,
    }
}

impl FragmentRef {
    /// Metadata for a runtime-delegated task, which is not in the initial job
    /// manifest but still needs workload-specific result verification.
    pub(crate) fn from_task(task: &NetworkTask) -> Option<Self> {
        (task.region.is_some() || task.byte_range.is_some()).then(|| Self {
            task_id: task.task_id.clone(),
            region: task.region.unwrap_or_else(empty_region),
            byte_range: task.byte_range,
            items: None,
        })
    }

    /// Fragment covering a byte chunk of the input.
    pub(crate) fn chunk(task_id: String, range: ByteRange) -> Self {
        Self {
            task_id,
            region: empty_region(),
            byte_range: Some(range),
            items: None,
        }
    }

    /// Fragment covering the items `items` of the input, stored in `range`.
    pub(crate) fn items(task_id: String, range: ByteRange, items: ItemRange) -> Self {
        Self {
            items: Some(items),
            ..Self::chunk(task_id, range)
        }
    }
}

/// What the publisher keeps about a job.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct JobManifest {
    pub(crate) job_id: String,
    /// BackEnd-facing job id. Older manifests default to the network id.
    #[serde(default)]
    pub(crate) root_job_id: String,
    /// Workload of the job; older manifests are raytracer renders.
    #[serde(default = "default_workload")]
    pub(crate) workload: String,
    /// Image size (raytracer); 0 for other workloads.
    #[serde(default)]
    pub(crate) width: u32,
    #[serde(default)]
    pub(crate) height: u32,
    /// Input size in bytes (workloads splitting a file).
    #[serde(default)]
    pub(crate) input_bytes: u64,
    #[serde(default)]
    pub(crate) scene_sha256: Option<String>,
    pub(crate) fragments: Vec<FragmentRef>,
}

fn default_workload() -> String {
    crate::workload::DEFAULT_WORKLOAD.to_string()
}

/// Path, relative to the work directory, of a result file kept by the
/// publisher: `results/<task or job id>.<extension>`.
pub(crate) fn result_file(id: &str, extension: &str) -> String {
    format!("results/{id}.{extension}")
}

/// Task id of fragment `index` of `job_id`.
pub(crate) fn fragment_task_id(job_id: &str, index: usize) -> String {
    format!("{job_id}.f{index:03}")
}

#[cfg(test)]
mod tests;
