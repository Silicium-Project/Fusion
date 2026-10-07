//! Job manifests on disk (`results/<job id>.job.json` in the work
//! directory), lookup of the job a fragment belongs to, and assembly of the
//! job result (`results/<job id>.<extension>`, by the job's workload) once
//! every fragment result (`results/<fragment id>.<extension>`) is there.

use super::{FragmentRef, JobManifest, result_file};
use crate::{
    content::ContentStore,
    workload::{self, Workload},
};
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

    /// Finds a job by the identifier used by the BackEnd control plane.
    pub(crate) fn manifest_for_root(&self, root_job_id: &str) -> Option<JobManifest> {
        self.jobs
            .lock()
            .ok()?
            .values()
            .find(|job| job.root_job_id == root_job_id || job.job_id == root_job_id)
            .cloned()
    }

    /// Root directory used by the compatibility artifact writer.
    pub(crate) fn root(&self) -> &Path {
        &self.root
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

    /// Path, relative to the work directory, of the collected result of
    /// fragment `task_id` of `job`.
    pub(crate) fn fragment_result_path(job: &JobManifest, task_id: &str) -> String {
        let extension = workload_of(job).map_or("bin", |w| w.fragment_extension());
        result_file(task_id, extension)
    }

    /// Fragments of `job` whose result is collected.
    pub(crate) fn collected(&self, job: &JobManifest) -> Vec<String> {
        job.fragments
            .iter()
            .filter(|fragment| {
                self.root
                    .join(Self::fragment_result_path(job, &fragment.task_id))
                    .is_file()
            })
            .map(|fragment| fragment.task_id.clone())
            .collect()
    }

    /// True once every file of the job result is written (the last one is
    /// written last).
    pub(crate) fn is_assembled(&self, job_id: &str) -> bool {
        let Some(job) = self.manifest(job_id) else {
            return false;
        };
        workload_of(&job)
            .and_then(|w| w.published_outputs().last())
            .is_some_and(|output| {
                self.root
                    .join(result_file(job_id, output.extension))
                    .is_file()
            })
    }

    /// Assembles the result of `job_id` when every fragment result is
    /// collected; `Ok(None)` while some are missing. Returns the path of the
    /// first result file.
    pub(crate) fn assemble(&self, job_id: &str) -> Result<Option<PathBuf>, String> {
        let job = self.manifest(job_id).ok_or("unknown job")?;
        let workload = workload_of(&job).ok_or("unknown workload")?;
        let mut fragments = Vec::with_capacity(job.fragments.len());
        for fragment in &job.fragments {
            let path = self
                .root
                .join(Self::fragment_result_path(&job, &fragment.task_id));
            match fs::read(path) {
                Ok(bytes) => fragments.push(bytes),
                Err(_) => return Ok(None),
            }
        }
        let input = job
            .scene_sha256
            .as_deref()
            .map(|sha256| self.root.join(ContentStore::relative_path(sha256)))
            .unwrap_or_default();
        let outputs = workload.assemble(&job, &input, &fragments)?;
        let mut first = None;
        for output in outputs {
            let path = self.root.join(result_file(job_id, output.extension));
            write_atomic(&path, &output.bytes)?;
            first.get_or_insert(path);
        }
        Ok(first)
    }
}

/// The workload of a job.
fn workload_of(job: &JobManifest) -> Option<&'static dyn Workload> {
    workload::find(&job.workload)
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
    #[cfg(windows)]
    if path.exists() {
        fs::remove_file(path).map_err(|err| err.to_string())?;
    }
    fs::rename(&partial, path).map_err(|err| err.to_string())
}
