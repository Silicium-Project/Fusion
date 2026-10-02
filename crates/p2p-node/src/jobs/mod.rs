//! Jobs split into fragments: a task published through the API with a scene
//! and no region becomes a job of rectangular tiles
//! (`silicium_raytracer::pipeline::tiles`), each published as its own task
//! `<job id>.f<NNN>` with its region. The job manifest (size, fragments) is
//! kept in the work directory ([`store`]); once every fragment's image is
//! collected, the publisher reassembles the final image.

pub(crate) mod store;

use crate::task::NetworkTask;
use serde::{Deserialize, Serialize};
use silicium_node_core::p2p::{Region, TaskEnvelope};
use silicium_raytracer::pipeline::tiles;

pub(crate) use store::JobStore;

/// Suffix of a fragment task id; its width is reserved in job ids.
pub(crate) const FRAGMENT_SUFFIX_EXAMPLE: &str = ".f000";
/// Upper bound on fragments per job (three-digit suffix).
const MAX_FRAGMENTS_LIMIT: usize = 256;

/// How jobs are split (`SILICIUM_MAX_FRAGMENTS`,
/// `SILICIUM_TARGET_PIXELS_PER_FRAGMENT`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct JobSettings {
    pub(crate) max_fragments: usize,
    pub(crate) target_pixels: usize,
}

impl Default for JobSettings {
    fn default() -> Self {
        Self {
            max_fragments: tiles::DEFAULT_MAX_FRAGMENTS,
            target_pixels: tiles::DEFAULT_TARGET_PIXELS_PER_FRAGMENT,
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
        }
    }
}

/// One fragment of a job.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct FragmentRef {
    pub(crate) task_id: String,
    pub(crate) region: Region,
}

/// What the publisher keeps about a job.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct JobManifest {
    pub(crate) job_id: String,
    pub(crate) width: u32,
    pub(crate) height: u32,
    #[serde(default)]
    pub(crate) scene_sha256: Option<String>,
    pub(crate) fragments: Vec<FragmentRef>,
}

/// Task id of fragment `index` of `job_id`.
pub(crate) fn fragment_task_id(job_id: &str, index: usize) -> String {
    format!("{job_id}.f{index:03}")
}

/// Splits `task` into fragment tasks, centre first. `None` when the task is
/// not a whole-image render (it already has a region, or runs a WASM module):
/// it is then published as is.
pub(crate) fn split(
    task: &NetworkTask,
    scene_text: &str,
    settings: &JobSettings,
) -> Option<(JobManifest, Vec<NetworkTask>)> {
    if task.region.is_some() || task.runtime_module_path.is_some() {
        return None;
    }
    let (width, height) = tiles::scene_resolution(scene_text);
    let side = Region::MAX_SIDE as usize;
    if width > side || height > side {
        return None;
    }
    let count = tiles::estimate_fragment_count(
        width,
        height,
        settings.target_pixels,
        settings.max_fragments.min(MAX_FRAGMENTS_LIMIT),
    );
    let tiles = tiles::split_tiles(width, height, count).ok()?;
    let mut fragments = Vec::with_capacity(tiles.len());
    let mut tasks = Vec::with_capacity(tiles.len());
    for (index, tile) in tiles.iter().enumerate() {
        let task_id = fragment_task_id(&task.task_id, index);
        let region = Region {
            x_start: tile.x_start as u32,
            x_end: tile.x_end as u32,
            y_start: tile.y_start as u32,
            y_end: tile.y_end as u32,
        };
        let mut fragment = task.clone();
        fragment.output_path = TaskEnvelope::local_output_path(&task_id)?;
        fragment.task_id = task_id.clone();
        fragment.region = Some(region);
        fragments.push(FragmentRef { task_id, region });
        tasks.push(fragment);
    }
    let manifest = JobManifest {
        job_id: task.task_id.clone(),
        width: width as u32,
        height: height as u32,
        scene_sha256: task.scene_sha256.clone(),
        fragments,
    };
    Some((manifest, tasks))
}

#[cfg(test)]
mod tests;
