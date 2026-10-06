//! Results: once one of this node's tasks is finalized, download the result
//! the worker published (`content://<sha256>`), check it against the
//! commitment the verifiers approved
//! ([`crate::workload::Workload::accepts_result`]), and keep it as
//! `results/<task_id>.<extension>` in the work directory; the last fragment
//! of a job triggers the assembly of the job result ([`crate::jobs`]).

use crate::{
    jobs::{JobStore, result_file, store::write_atomic},
    processing::NodeContext,
    workload::{self, Workload},
};
use silicium_node_core::taskbook::DerivedTaskStatus;
use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex},
};

/// URI scheme of result payloads stored in the content store.
pub(crate) const CONTENT_SCHEME: &str = "content://";
/// Downloads tried per task before giving up.
const MAX_TRIES: u32 = 5;

/// Collection state of finished tasks, by task id.
#[derive(Clone)]
pub(crate) struct Collector {
    tasks: Arc<Mutex<BTreeMap<String, Collection>>>,
    jobs: JobStore,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Collection {
    Running(u32),
    Failed(u32),
    Done,
}

impl Collector {
    pub(crate) fn new(jobs: JobStore) -> Self {
        Self {
            tasks: Arc::default(),
            jobs,
        }
    }

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
                let collected = collect_one(&context, &collector.jobs, &task_id).await;
                collector.end(&task_id, try_number, collected);
                if collected == Some(true) {
                    collector.assemble_job_of(&task_id);
                }
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

    /// Reassembles the job of a fragment once its last image arrived.
    fn assemble_job_of(&self, task_id: &str) {
        let Some((job, _)) = self.jobs.fragment(task_id) else {
            return;
        };
        match self.jobs.assemble(&job.job_id) {
            Ok(Some(path)) => println!(" Job {} assembled into {}", job.job_id, path.display()),
            Ok(None) => {}
            Err(err) => println!(" Job {} not assembled: {err}", job.job_id),
        }
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

/// Collects one task: `Some(true)` collected, `Some(false)` to retry,
/// `None` nothing to collect (not finalized, or not a content result).
async fn collect_one(context: &NodeContext, jobs: &JobStore, task_id: &str) -> Option<bool> {
    let state = context.taskbook.state(task_id).ok().flatten()?;
    if state.status != DerivedTaskStatus::Finalized {
        return None;
    }
    let finalized = state.finalized_attempt?;
    let attempt = state.attempts.iter().find(|a| a.attempt == finalized)?;
    let result = attempt.result.as_ref()?;
    let sha256 = result.result.uri.strip_prefix(CONTENT_SCHEME)?;
    if !context.content.ensure(sha256).await {
        println!(" Result of {task_id} not downloaded yet");
        return Some(false);
    }
    let bytes = context.content.get(sha256)?;
    let job = jobs.fragment(task_id);
    let workload = job
        .as_ref()
        .and_then(|(job, _)| workload::find(&job.workload))
        .or_else(|| known_workload(context, task_id))?;
    let fragment = job.as_ref().map(|(_, fragment)| fragment);
    if !workload.accepts_result(fragment, &bytes, &result.milestones) {
        println!(" Result of {task_id} does not match its verified commitment");
        return None;
    }
    let relative = match &job {
        Some((job, _)) => JobStore::fragment_result_path(job, task_id),
        None => result_file(task_id, workload.fragment_extension()),
    };
    let path = context.content.absolute(&relative);
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

/// Workload of a task this node knows but that belongs to no job.
fn known_workload(context: &NodeContext, task_id: &str) -> Option<&'static dyn Workload> {
    let known = context.known_tasks.lock().ok()?;
    known.get(task_id).and_then(workload::of)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_failed_collection_is_retried_a_bounded_number_of_times() {
        let root = std::env::temp_dir().join(format!("silicium-collector-{}", std::process::id()));
        let collector = Collector::new(JobStore::open(root));
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
