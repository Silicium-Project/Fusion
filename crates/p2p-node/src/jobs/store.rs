//! Job manifests on disk (`results/<job id>.job.json` in the work
//! directory), lookup of the job a fragment belongs to, and reassembly of
//! the final image (`results/<job id>.ppm` and `.png`) once every fragment
//! image (`results/<fragment id>.ppm`) is there.

use super::{FragmentRef, JobManifest};
use crate::results::result_path;
use silicium_raytracer::pipeline::{png, ppm, reassemble};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};

const MANIFEST_SUFFIX: &str = ".job.json";

/// Jobs published by this node, by job id.
#[derive(Clone)]
pub(crate) struct JobStore {
    root: PathBuf,
    jobs: Arc<Mutex<BTreeMap<String, JobManifest>>>,
}

impl JobStore {
    /// Opens the store of the work directory `root`, loading saved manifests.
    pub(crate) fn open(root: PathBuf) -> Self {
        let mut jobs = BTreeMap::new();
        if let Ok(entries) = fs::read_dir(root.join("results")) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if !name.ends_with(MANIFEST_SUFFIX) {
                    continue;
                }
                let manifest = fs::read(entry.path())
                    .ok()
                    .and_then(|bytes| serde_json::from_slice::<JobManifest>(&bytes).ok());
                if let Some(manifest) = manifest {
                    jobs.insert(manifest.job_id.clone(), manifest);
                }
            }
        }
        Self {
            root,
            jobs: Arc::new(Mutex::new(jobs)),
        }
    }

    /// Path of a job's manifest, relative to the work directory.
    pub(crate) fn manifest_path(job_id: &str) -> String {
        format!("results/{job_id}{MANIFEST_SUFFIX}")
    }

    /// Path of a job's final PNG, relative to the work directory.
    pub(crate) fn png_path(job_id: &str) -> String {
        format!("results/{job_id}.png")
    }

    /// Saves and remembers a new job.
    pub(crate) fn add(&self, manifest: JobManifest) -> Result<(), String> {
        let bytes = serde_json::to_vec_pretty(&manifest).map_err(|err| err.to_string())?;
        write_atomic(
            &self.root.join(Self::manifest_path(&manifest.job_id)),
            &bytes,
        )?;
        self.jobs
            .lock()
            .map_err(|_| "job store poisoned".to_string())?
            .insert(manifest.job_id.clone(), manifest);
        Ok(())
    }

    pub(crate) fn manifest(&self, job_id: &str) -> Option<JobManifest> {
        self.jobs.lock().ok()?.get(job_id).cloned()
    }

    /// The job a fragment task belongs to, and the fragment.
    pub(crate) fn fragment(&self, task_id: &str) -> Option<(JobManifest, FragmentRef)> {
        let jobs = self.jobs.lock().ok()?;
        jobs.values().find_map(|job| {
            job.fragments
                .iter()
                .find(|fragment| fragment.task_id == task_id)
                .map(|fragment| (job.clone(), fragment.clone()))
        })
    }

    /// Fragments of `job_id` whose image is collected.
    pub(crate) fn collected(&self, job: &JobManifest) -> Vec<String> {
        job.fragments
            .iter()
            .filter(|fragment| self.root.join(result_path(&fragment.task_id)).is_file())
            .map(|fragment| fragment.task_id.clone())
            .collect()
    }

    /// True once the final image and its PNG are written (PNG last).
    pub(crate) fn is_assembled(&self, job_id: &str) -> bool {
        self.root.join(Self::png_path(job_id)).is_file()
    }

    /// Reassembles the final image of `job_id` when every fragment image is
    /// collected; `Ok(None)` while some are missing.
    pub(crate) fn assemble(&self, job_id: &str) -> Result<Option<PathBuf>, String> {
        let job = self.manifest(job_id).ok_or("unknown job")?;
        let mut images = Vec::with_capacity(job.fragments.len());
        for fragment in &job.fragments {
            match fs::read(self.root.join(result_path(&fragment.task_id))) {
                Ok(bytes) => images.push((fragment.region, bytes)),
                Err(_) => return Ok(None),
            }
        }
        let placed: Vec<reassemble::PlacedTile<'_>> = images
            .iter()
            .map(|(region, bytes)| reassemble::PlacedTile {
                x_start: region.x_start as usize,
                y_start: region.y_start as usize,
                ppm: bytes,
            })
            .collect();
        let image = reassemble::reassemble(&placed)?;
        let decoded = ppm::parse(&image, job_id)?;
        if (decoded.width, decoded.height) != (job.width as usize, job.height as usize) {
            return Err(format!(
                "reassembled image is {}x{}, expected {}x{}",
                decoded.width, decoded.height, job.width, job.height
            ));
        }
        let path = self.root.join(result_path(job_id));
        write_atomic(&path, &image)?;
        let preview = png::encode_rgb(decoded.width, decoded.height, &decoded.pixels)?;
        write_atomic(&self.root.join(Self::png_path(job_id)), &preview)?;
        Ok(Some(path))
    }
}

/// Writes a file through a temporary name, so readers never see half of it.
pub(crate) fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    let mut partial = path.as_os_str().to_owned();
    partial.push(".partial");
    let partial = PathBuf::from(partial);
    fs::write(&partial, bytes).map_err(|err| err.to_string())?;
    fs::rename(&partial, path).map_err(|err| err.to_string())
}
