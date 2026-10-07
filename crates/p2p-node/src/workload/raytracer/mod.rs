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
use silicium_node_core::taskbook::{MilestoneSample, ResultState};
use silicium_raytracer::pipeline::{png, ppm, reassemble};
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
