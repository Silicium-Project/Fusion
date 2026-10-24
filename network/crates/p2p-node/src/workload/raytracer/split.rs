//! Splitting a whole-image render into rectangular tiles
//! (`silicium_raytracer::pipeline::tiles`, centre first), each published as
//! a fragment task with its region.

use crate::{
    jobs::{FragmentRef, JobManifest, JobSettings, MAX_FRAGMENTS_LIMIT, fragment_task_id},
    task::NetworkTask,
};
use silicium_node_core::p2p::{Region, TaskEnvelope};
use silicium_raytracer::pipeline::tiles;

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
    let count = task.requested_fragment_count.unwrap_or_else(|| {
        tiles::estimate_fragment_count(
            width,
            height,
            settings.target_pixels,
            settings.max_fragments.min(MAX_FRAGMENTS_LIMIT),
        )
    });
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
        fragments.push(FragmentRef {
            task_id,
            region,
            byte_range: None,
            items: None,
        });
        tasks.push(fragment);
    }
    let manifest = JobManifest {
        job_id: task.task_id.clone(),
        root_job_id: task
            .root_job_id
            .clone()
            .unwrap_or_else(|| task.task_id.clone()),
        workload: super::ID.to_string(),
        width: width as u32,
        height: height as u32,
        input_bytes: scene_text.len() as u64,
        scene_sha256: task.scene_sha256.clone(),
        fragments,
    };
    Some((manifest, tasks))
}
