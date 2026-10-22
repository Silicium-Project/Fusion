//! The `raytracer` workload: a scene is split into image tiles, each tile is
//! rendered by the worker's compute daemon with a milestone commitment
//! (hashes of blocks of rows), verifiers re-render milestones drawn from the
//! publisher's acceptance, and the publisher reassembles the image (PPM and
//! PNG preview).

mod compute;
mod image;
mod split;
mod verify;

#[cfg(test)]
pub(crate) use split::split as split_scene;

use super::{ComputeOutcome, OutputFile, PublishedOutput, Workload};
use crate::{
    jobs::{FragmentRef, JobManifest, JobSettings},
    processing::NodeContext,
    task::NetworkTask,
};
use futures::future::BoxFuture;
use silicium_node_core::{
    p2p::{Region, TaskEnvelope},
    taskbook::{MilestoneSample, ResultState},
};
use silicium_raytracer::pipeline::{milestones, png, ppm, reassemble};
use std::path::Path;

/// Identifier of the workload.
pub(crate) const ID: &str = "raytracer";

/// The raytracer workload (see the module documentation).
pub(crate) struct Raytracer;

/// Final image, then its PNG preview (written last: it marks the job done).
const OUTPUTS: &[PublishedOutput] = &[
    PublishedOutput {
        extension: "ppm",
        target: "reassembled/render.ppm",
        summary_keys: &["reassembled_ppm", "result_path"],
    },
    PublishedOutput {
        extension: "png",
        target: "reassembled/render.png",
        summary_keys: &["reassembled_png", "result_png_path"],
    },
];

const MIN_DELEGATION_PIXELS: u64 = 4_096;

impl Workload for Raytracer {
    fn id(&self) -> &'static str {
        ID
    }

    fn storage_dir(&self) -> &'static str {
        "raytracer"
    }

    fn fragment_extension(&self) -> &'static str {
        "ppm"
    }

    fn published_outputs(&self) -> &'static [PublishedOutput] {
        OUTPUTS
    }

    fn split(
        &self,
        task: &NetworkTask,
        input: &Path,
        settings: &JobSettings,
    ) -> Option<(JobManifest, Vec<NetworkTask>)> {
        let scene = std::fs::read_to_string(input).ok()?;
        split::split(task, &scene, settings)
    }

    fn split_subtask(
        &self,
        task: &NetworkTask,
        input: &Path,
        _settings: &JobSettings,
    ) -> Option<(JobManifest, Vec<NetworkTask>)> {
        let parent_region = task.region?;
        let scene = std::fs::read_to_string(input).ok()?;
        let (scene_width, scene_height) =
            silicium_raytracer::pipeline::tiles::scene_resolution(&scene);
        let (scene_width, scene_height) = (
            u32::try_from(scene_width).ok()?,
            u32::try_from(scene_height).ok()?,
        );
        if parent_region.x_end > scene_width || parent_region.y_end > scene_height {
            return None;
        }
        let regions = split_region(parent_region)?;
        let input_bytes = std::fs::metadata(input).ok()?.len();
        let mut fragments = Vec::with_capacity(2);
        let mut tasks = Vec::with_capacity(2);
        for (index, region) in regions.into_iter().enumerate() {
            let task_id = crate::jobs::fragment_task_id(&task.task_id, index);
            let mut child = task.clone();
            child.task_id = task_id.clone();
            child.output_path = TaskEnvelope::local_output_path_for(&task_id, Some(ID))?;
            child.region = Some(region);
            child.requested_fragment_count = None;
            fragments.push(FragmentRef {
                task_id,
                region,
                byte_range: None,
                items: None,
            });
            tasks.push(child);
        }
        Some((
            JobManifest {
                job_id: task.task_id.clone(),
                root_job_id: task.task_id.clone(),
                workload: ID.to_string(),
                width: parent_region.x_end - parent_region.x_start,
                height: parent_region.y_end - parent_region.y_start,
                input_bytes,
                scene_sha256: task.scene_sha256.clone(),
                fragments,
            },
            tasks,
        ))
    }

    fn combine_subtask_results(
        &self,
        task: &NetworkTask,
        child_results: &[Vec<u8>],
    ) -> Option<Vec<u8>> {
        let parent = task.region?;
        let children = split_region(parent)?;
        if child_results.len() != 2 {
            return None;
        }
        for (bytes, region) in child_results.iter().zip(children) {
            let image = ppm::parse(bytes, "delegated-raytracer-child").ok()?;
            if image.width != (region.x_end - region.x_start) as usize
                || image.height != (region.y_end - region.y_start) as usize
            {
                return None;
            }
        }
        let placed = [
            reassemble::PlacedTile {
                x_start: (children[0].x_start - parent.x_start) as usize,
                y_start: (children[0].y_start - parent.y_start) as usize,
                ppm: &child_results[0],
            },
            reassemble::PlacedTile {
                x_start: (children[1].x_start - parent.x_start) as usize,
                y_start: (children[1].y_start - parent.y_start) as usize,
                ppm: &child_results[1],
            },
        ];
        let assembled = reassemble::reassemble(&placed).ok()?;
        let image = ppm::parse(&assembled, "delegated-raytracer-parent").ok()?;
        (image.width == (parent.x_end - parent.x_start) as usize
            && image.height == (parent.y_end - parent.y_start) as usize)
            .then_some(assembled)
    }

    fn subtask_result_milestones(&self, task: &NetworkTask, result: &[u8]) -> Vec<MilestoneSample> {
        let Some(region) = task.region else {
            return Vec::new();
        };
        let Ok(manifest) = milestones::build(
            result,
            region.y_start as usize,
            milestones::DEFAULT_VERIFICATION_BATCH_ROWS,
            region.x_start as usize,
        ) else {
            return Vec::new();
        };
        if manifest.fragment_x_end != region.x_end as usize
            || manifest.fragment_y_end != region.y_end as usize
        {
            return Vec::new();
        }
        manifest
            .milestones
            .into_iter()
            .map(|item| MilestoneSample {
                index: item.index as u32,
                x_start: item.x_start as u32,
                x_end: item.x_end as u32,
                y_start: item.y_start as u32,
                y_end: item.y_end as u32,
                pixel_sha256: item.pixel_sha256,
            })
            .collect()
    }

    fn execute<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
    ) -> BoxFuture<'a, Option<ComputeOutcome>> {
        Box::pin(compute::execute_task(context, task))
    }

    fn verify<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
        result: &'a ResultState,
        seed: &'a str,
    ) -> BoxFuture<'a, Option<bool>> {
        Box::pin(verify::verify(context, task, result, seed))
    }

    fn accepts_result(
        &self,
        fragment: Option<&FragmentRef>,
        bytes: &[u8],
        milestones: &[MilestoneSample],
    ) -> bool {
        let origin = fragment.map_or((0, 0), |fragment| {
            (fragment.region.x_start, fragment.region.y_start)
        });
        image::image_matches_milestones(bytes, milestones, origin)
    }

    fn assemble(
        &self,
        job: &JobManifest,
        _input: &Path,
        fragments: &[Vec<u8>],
    ) -> Result<Vec<OutputFile>, String> {
        let placed: Vec<reassemble::PlacedTile<'_>> = job
            .fragments
            .iter()
            .zip(fragments)
            .map(|(fragment, bytes)| reassemble::PlacedTile {
                x_start: fragment.region.x_start as usize,
                y_start: fragment.region.y_start as usize,
                ppm: bytes,
            })
            .collect();
        let image = reassemble::reassemble(&placed)?;
        let decoded = ppm::parse(&image, &job.job_id)?;
        if (decoded.width, decoded.height) != (job.width as usize, job.height as usize) {
            return Err(format!(
                "reassembled image is {}x{}, expected {}x{}",
                decoded.width, decoded.height, job.width, job.height
            ));
        }
        let preview = png::encode_rgb(decoded.width, decoded.height, &decoded.pixels)?;
        Ok(vec![
            OutputFile {
                extension: "ppm",
                bytes: image,
            },
            OutputFile {
                extension: "png",
                bytes: preview,
            },
        ])
    }
}

/// Deterministic half split along the longer side, used by both the parent
/// manifest and the result combiner.
fn split_region(parent: Region) -> Option<[Region; 2]> {
    if !parent.is_valid() {
        return None;
    }
    let width = parent.x_end - parent.x_start;
    let height = parent.y_end - parent.y_start;
    if u64::from(width) * u64::from(height) <= MIN_DELEGATION_PIXELS {
        return None;
    }
    if width >= height && width >= 2 {
        let middle = parent.x_start + width / 2;
        Some([
            Region {
                x_end: middle,
                ..parent
            },
            Region {
                x_start: middle,
                ..parent
            },
        ])
    } else if height >= 2 {
        let middle = parent.y_start + height / 2;
        Some([
            Region {
                y_end: middle,
                ..parent
            },
            Region {
                y_start: middle,
                ..parent
            },
        ])
    } else {
        None
    }
}
