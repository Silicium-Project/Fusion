//! Result images: once one of this node's tasks is finalized, download the
//! image the worker published (`content://<sha256>`), check it against the
//! milestone commitment the verifiers approved, and keep it as
//! `results/<task_id>.ppm` in the work directory.
//!
//! The check matters: verifiers re-render milestones, not the uploaded file,
//! so without it a worker could commit honest milestones and upload another
//! image.

use crate::processing::NodeContext;
use silicium_node_core::taskbook::{DerivedTaskStatus, MilestoneSample};
use silicium_raytracer::pipeline::{ppm, sha256_hex};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::{Arc, Mutex},
};

/// URI scheme of result payloads stored in the content store.
pub(crate) const CONTENT_SCHEME: &str = "content://";
/// Downloads tried per task before giving up.
const MAX_TRIES: u32 = 5;

/// Collection state of finished tasks, by task id.
#[derive(Clone, Default)]
pub(crate) struct Collector {
    tasks: Arc<Mutex<BTreeMap<String, Collection>>>,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Collection {
    Running(u32),
    Failed(u32),
    Done,
}

impl Collector {
    /// Starts collecting the result of each finished task not yet collected
    /// (or whose previous try failed, up to [`MAX_TRIES`]).
    pub(crate) fn collect(&self, context: &NodeContext, finished: &[String]) {
        for task_id in finished {
            let Some(try_number) = self.begin(task_id) else {
                continue;
            };
            let context = context.clone();
            let collector = self.clone();
            let task_id = task_id.clone();
            tokio::spawn(async move {
                let collected = collect_one(&context, &task_id).await;
                collector.end(&task_id, try_number, collected);
            });
        }
    }

    fn begin(&self, task_id: &str) -> Option<u32> {
        let mut tasks = self.tasks.lock().ok()?;
        let try_number = match tasks.get(task_id) {
            None => 1,
            Some(Collection::Failed(tries)) if *tries < MAX_TRIES => tries + 1,
            Some(_) => return None,
        };
        tasks.insert(task_id.to_string(), Collection::Running(try_number));
        Some(try_number)
    }

    fn end(&self, task_id: &str, try_number: u32, collected: Option<bool>) {
        if let Ok(mut tasks) = self.tasks.lock() {
            let state = match collected {
                Some(true) | None => Collection::Done,
                Some(false) => Collection::Failed(try_number),
            };
            tasks.insert(task_id.to_string(), state);
        }
    }
}

/// Path of a task's collected image, relative to the work directory.
pub(crate) fn result_path(task_id: &str) -> String {
    format!("results/{task_id}.ppm")
}

/// Collects one task: `Some(true)` collected, `Some(false)` to retry,
/// `None` nothing to collect (not finalized, or not a content result).
async fn collect_one(context: &NodeContext, task_id: &str) -> Option<bool> {
    let state = context.taskbook.state(task_id).ok().flatten()?;
    if state.status != DerivedTaskStatus::Finalized {
        return None;
    }
    let finalized = state.finalized_attempt?;
    let attempt = state.attempts.iter().find(|a| a.attempt == finalized)?;
    let result = attempt.result.as_ref()?;
    let sha256 = result.result.uri.strip_prefix(CONTENT_SCHEME)?;
    if !context.content.ensure(sha256).await {
        println!(" Result image of {task_id} not downloaded yet");
        return Some(false);
    }
    let bytes = context.content.get(sha256)?;
    if !image_matches_milestones(&bytes, &result.milestones, (0, 0)) {
        println!(" Result image of {task_id} does not match its verified milestones");
        return None;
    }
    let path = context.content.absolute(&result_path(task_id));
    match write_atomic(&path, &bytes) {
        Ok(()) => {
            println!(" Result of {task_id} saved to {}", path.display());
            Some(true)
        }
        Err(err) => {
            println!(" Could not save the result of {task_id}: {err}");
            Some(false)
        }
    }
}

/// True when every milestone's block of `image` (a P6 PPM whose top-left
/// pixel sits at `origin` in the full image) hashes to its commitment.
pub(crate) fn image_matches_milestones(
    image: &[u8],
    milestones: &[MilestoneSample],
    origin: (u32, u32),
) -> bool {
    let Ok(image) = ppm::parse(image, "result") else {
        return false;
    };
    !milestones.is_empty()
        && milestones.iter().all(|milestone| {
            block_hash(&image, milestone, origin).as_deref() == Some(&milestone.pixel_sha256)
        })
}

/// SHA-256 of a milestone's block of rows, or `None` when it falls outside
/// the image.
fn block_hash(image: &ppm::Ppm, milestone: &MilestoneSample, origin: (u32, u32)) -> Option<String> {
    let to_local = |value: u32, start: u32| value.checked_sub(start).map(|v| v as usize);
    let x_start = to_local(milestone.x_start, origin.0)?;
    let x_end = to_local(milestone.x_end, origin.0)?;
    let y_start = to_local(milestone.y_start, origin.1)?;
    let y_end = to_local(milestone.y_end, origin.1)?;
    if x_start >= x_end || y_start >= y_end || x_end > image.width || y_end > image.height {
        return None;
    }
    let stride = image.width * 3;
    let mut block = Vec::with_capacity((x_end - x_start) * 3 * (y_end - y_start));
    for row in y_start..y_end {
        let offset = row * stride;
        block.extend_from_slice(&image.pixels[offset + x_start * 3..offset + x_end * 3]);
    }
    Some(sha256_hex(&block))
}

fn write_atomic(path: &PathBuf, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    let partial = path.with_extension("partial");
    fs::write(&partial, bytes).map_err(|err| err.to_string())?;
    fs::rename(&partial, path).map_err(|err| err.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use silicium_raytracer::pipeline::milestones;

    fn pattern(width: usize, height: usize) -> Vec<u8> {
        let pixels: Vec<u8> = (0..width * height * 3)
            .map(|i| (i * 31 % 256) as u8)
            .collect();
        ppm::encode(width, height, &pixels)
    }

    fn samples(image: &[u8], y: usize, x: usize) -> Vec<MilestoneSample> {
        milestones::build(image, y, 4, x)
            .unwrap()
            .milestones
            .into_iter()
            .map(|m| MilestoneSample {
                index: m.index as u32,
                x_start: m.x_start as u32,
                x_end: m.x_end as u32,
                y_start: m.y_start as u32,
                y_end: m.y_end as u32,
                pixel_sha256: m.pixel_sha256,
            })
            .collect()
    }

    #[test]
    fn the_committed_image_matches_and_another_does_not() {
        let image = pattern(6, 10);
        let committed = samples(&image, 0, 0);
        assert!(image_matches_milestones(&image, &committed, (0, 0)));
        let mut other = image.clone();
        let last = other.len() - 1;
        other[last] ^= 0xff;
        assert!(!image_matches_milestones(&other, &committed, (0, 0)));
        assert!(!image_matches_milestones(&image, &[], (0, 0)));
        assert!(!image_matches_milestones(b"not a ppm", &committed, (0, 0)));
    }

    #[test]
    fn a_tile_is_checked_at_its_place_in_the_image() {
        let tile = pattern(3, 5);
        let committed = samples(&tile, 20, 7);
        assert!(image_matches_milestones(&tile, &committed, (7, 20)));
        assert!(!image_matches_milestones(&tile, &committed, (0, 0)));
    }

    #[test]
    fn a_failed_collection_is_retried_a_bounded_number_of_times() {
        let collector = Collector::default();
        for try_number in 1..=MAX_TRIES {
            assert_eq!(collector.begin("t"), Some(try_number));
            assert_eq!(collector.begin("t"), None, "already running");
            collector.end("t", try_number, Some(false));
        }
        assert_eq!(collector.begin("t"), None);
        assert_eq!(collector.begin("u"), Some(1));
        collector.end("u", 1, Some(true));
        assert_eq!(collector.begin("u"), None);
    }
}
