//! Publishing a task queued by the API: share its input by hash, split it
//! into fragments as its workload defines ([`crate::workload`]), then for each task
//! sign the proposal in the task book, store the DHT record and gossip it.
//! When configured, this node also works on its own tasks.

use crate::{
    content::ContentStore,
    control::ControlRegistry,
    jobs::{JobSettings, JobStore},
    processing::NodeContext,
    swarm::{P2pBehaviour, publish_task_record, publish_taskbook_event},
    task::{GossipMessage, NetworkTask},
    worker::process_task,
};
use libp2p::{Swarm, gossipsub};
use silicium_node_core::{
    p2p::{DhtRecordEnvelope, TaskEnvelope},
    taskbook::{PayloadRef, TaskEvent, TaskEventBody, TaskTerms},
};

/// How this node publishes tasks.
pub(crate) struct PublishSettings {
    pub(crate) terms: TaskTerms,
    pub(crate) jobs: JobSettings,
    pub(crate) work_own_tasks: bool,
    pub(crate) control: ControlRegistry,
}

/// Publishes `task` (one task, or the fragments of its job) and returns the
/// tasks published, for retries.
pub(crate) async fn publish_request(
    swarm: &mut Swarm<P2pBehaviour>,
    topic: &gossipsub::IdentTopic,
    context: &NodeContext,
    jobs: &JobStore,
    settings: &PublishSettings,
    mut task: NetworkTask,
) -> Vec<NetworkTask> {
    if !share_scene(context, &mut task).await {
        return Vec::new();
    }
    let tasks = split_job(context, jobs, settings, task);
    for task in &tasks {
        publish_one(swarm, topic, context, settings, task);
    }
    tasks
}

/// Shares the task's input by hash (prepared by its workload when it
/// prepares inputs), unless the control API already did. False when the
/// workload refused the input: the task is not published.
async fn share_scene(context: &NodeContext, task: &mut NetworkTask) -> bool {
    if let Some(sha256) = &task.scene_sha256
        && task.scene_path == ContentStore::relative_path(sha256)
        && context.content.has(sha256)
    {
        return true;
    }
    let Some(workload) = crate::workload::of(task) else {
        return true;
    };
    let source = context.content.absolute(&task.scene_path);
    match import_input(&context.content, workload, &source).await {
        Ok(sha256) => {
            task.scene_path = ContentStore::relative_path(&sha256);
            task.scene_sha256 = Some(sha256);
            true
        }
        Err(ImportError::Rejected(reason)) => {
            println!(" Input of {} refused: {reason}", task.task_id);
            false
        }
        Err(ImportError::Storage(err)) => {
            println!(" Scene of {} not shared: {err}", task.task_id);
            true
        }
    }
}

/// Why a submitted input was not imported.
#[derive(Debug)]
pub(crate) enum ImportError {
    /// The workload refused it; the message is for the submitter.
    Rejected(String),
    /// It could not be stored.
    Storage(String),
}

/// Imports the file submitted at `source` into the content store, as the
/// workload prepares it ([`crate::workload::Workload::prepare_input`]) or as
/// is, and returns its hash.
pub(crate) async fn import_input(
    content: &ContentStore,
    workload: &'static dyn crate::workload::Workload,
    source: &std::path::Path,
) -> Result<String, ImportError> {
    let path = source.to_path_buf();
    let prepared = tokio::task::spawn_blocking(move || workload.prepare_input(&path))
        .await
        .map_err(|err| ImportError::Storage(err.to_string()))?
        .map_err(ImportError::Rejected)?;
    match prepared {
        Some(bytes) => content.add_bytes(&bytes).await,
        None => content.add_external_file(source).await,
    }
    .map_err(ImportError::Storage)
}

/// The fragments of `task`'s job, or `task` alone when it is not split.
fn split_job(
    context: &NodeContext,
    jobs: &JobStore,
    settings: &PublishSettings,
    mut task: NetworkTask,
) -> Vec<NetworkTask> {
    let input = context.content.absolute(&task.scene_path);
    let workload = crate::workload::of(&task);
    let Some((manifest, fragments)) =
        workload.and_then(|workload| workload.split(&task, &input, &settings.jobs))
    else {
        if workload.is_some_and(|workload| workload.requires_split()) {
            println!(" Job {} could not be split; not published", task.task_id);
            settings
                .control
                .mark_failed(&task.task_id, "input_not_split");
            return Vec::new();
        }
        if let Some(payment) = task.solana_payment.as_mut() {
            if payment.fragment_index.is_some() {
                return vec![task];
            }
            if payment.expected_fragments != 1 {
                println!(
                    " Paid job {} expected {} fragments but this workload is not split",
                    task.task_id, payment.expected_fragments
                );
                settings
                    .control
                    .mark_failed(&task.task_id, "solana_fragment_count_mismatch");
                return Vec::new();
            }
            payment.fragment_index = Some(0);
        }
        if task.parent_task_id.is_none() && task.delegation_depth == 0 {
            task.root_job_id.get_or_insert_with(|| task.task_id.clone());
        }
        return vec![task];
    };
    let root_job_id = manifest.root_job_id.clone();
    let mut fragments = fragments;
    for fragment in &mut fragments {
        fragment.root_job_id = Some(root_job_id.clone());
        fragment.parent_task_id = None;
        fragment.delegation_depth = 0;
    }
    let count = fragments.len();
    let fragments = if let Some(payment) = task.solana_payment.as_ref() {
        if payment.expected_fragments as usize != count {
            println!(
                " Paid job {} expected {} fragments but the workload split into {count}",
                task.task_id, payment.expected_fragments
            );
            settings
                .control
                .mark_failed(&task.task_id, "solana_fragment_count_mismatch");
            return Vec::new();
        }
        fragments
            .into_iter()
            .enumerate()
            .map(|(index, mut fragment)| {
                fragment.solana_payment = Some(silicium_node_core::p2p::SolanaPaymentRef {
                    job: payment.job.clone(),
                    expected_fragments: payment.expected_fragments,
                    fragment_index: Some(index as u32),
                });
                fragment
            })
            .collect()
    } else {
        fragments
    };
    match jobs.add(manifest) {
        Ok(()) => {
            // The control-plane request represents the logical job. Once it
            // is split, expose only its durable fragment tasks so callers do
            // not wait forever on a parent that can never enter the taskbook.
            settings.control.remove_task(&task.task_id);
            println!(" Job {} split into {count} fragment(s)", task.task_id);
            fragments
        }
        Err(err) => {
            println!(
                " Job {} not split (manifest not saved: {err})",
                task.task_id
            );
            vec![task]
        }
    }
}

/// Proposes one task in the task book, stores its DHT record, gossips it.
fn publish_one(
    swarm: &mut Swarm<P2pBehaviour>,
    topic: &gossipsub::IdentTopic,
    context: &NodeContext,
    settings: &PublishSettings,
    task: &NetworkTask,
) {
    let envelope: TaskEnvelope = task.clone().into();
    let task_bytes = serde_json::to_vec(&envelope).expect("task envelope serializes");
    let proposal = TaskEventBody::TaskProposed {
        spec: PayloadRef {
            uri: DhtRecordEnvelope::task_record_key(&task.task_id),
            sha256: TaskEvent::payload_hash(&task_bytes),
        },
        terms: crate::workload::of(task)
            .map_or(settings.terms, |workload| workload.terms(settings.terms)),
    };
    match context.taskbook.append_signed(&task.task_id, proposal) {
        Ok(event) => publish_taskbook_event(swarm, topic, &event),
        Err(err) => {
            println!(" Task book refused task {}: {err}", task.task_id);
            return;
        }
    }
    settings
        .control
        .register_published(task, &settings.terms_roles());
    publish_task_record(swarm, task);
    let data = serde_json::to_vec(&GossipMessage::Task(envelope)).expect("task serializes");
    match swarm.behaviour_mut().gossipsub.publish(topic.clone(), data) {
        Ok(_) => println!(" Published task {} to gossipsub", task.task_id),
        Err(err) => println!(" Task {} not gossiped yet: {err:?}", task.task_id),
    }
    context.remember_task(task);
    if settings.work_own_tasks {
        let context = context.clone();
        let task = task.clone();
        tokio::spawn(async move { process_task(context, task).await });
    }
}

impl PublishSettings {
    fn terms_roles(&self) -> Vec<String> {
        vec!["compute".to_string(), "verify".to_string()]
    }
}
