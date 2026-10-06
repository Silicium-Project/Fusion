//! Raytracer verification: the result's milestones must tile the task's
//! region (or the whole image), and the milestones drawn from the
//! publisher's acceptance hash are re-rendered locally and compared.

use super::compute::render_region;
use crate::{processing::NodeContext, task::NetworkTask};
use silicium_node_core::taskbook::{
    ResultState, milestones_cover_region, sample_milestones, verification_sample_count,
};

/// Verdict on `result`, or `None` when a sampled block could not be
/// rendered locally (no verdict is then published, so that an honest result
/// is not rejected because of a local failure).
pub(crate) async fn verify(
    context: &NodeContext,
    task: &NetworkTask,
    result: &ResultState,
    seed: &str,
) -> Option<bool> {
    if !covers_scene(context, task, result) {
        println!(
            " Result of {} does not cover its region; rejecting it",
            task.task_id
        );
        return Some(false);
    }
    let milestones = &result.milestones;
    let sample = sample_milestones(
        milestones,
        seed,
        verification_sample_count(milestones.len()),
    );
    // A result without commitment cannot be checked: it is rejected.
    if sample.is_empty() {
        return Some(false);
    }
    let tag: String = result.event_hash.chars().take(16).collect();
    for milestone in sample {
        let output = format!(
            "verify/{}/{tag}-block-{}.ppm",
            task.task_id, milestone.index
        );
        let Some(hash) = render_region(context, task, &output, milestone).await else {
            println!(
                " Could not render a block of {}; no verdict published",
                task.task_id
            );
            return None;
        };
        if hash != milestone.pixel_sha256 {
            return Some(false);
        }
    }
    Some(true)
}

/// True when the result's milestones tile the task's region (a fragment),
/// or the whole image of the scene when the task has no region.
fn covers_scene(context: &NodeContext, task: &NetworkTask, result: &ResultState) -> bool {
    if let Some(region) = task.region {
        return milestones_cover_region(
            &result.milestones,
            (region.x_start, region.x_end),
            (region.y_start, region.y_end),
        );
    }
    let Ok(text) = std::fs::read_to_string(context.content.absolute(&task.scene_path)) else {
        return false;
    };
    let (width, height) = silicium_raytracer::pipeline::tiles::scene_resolution(&text);
    let (Ok(width), Ok(height)) = (u32::try_from(width), u32::try_from(height)) else {
        return false;
    };
    milestones_cover_region(&result.milestones, (0, width), (0, height))
}
