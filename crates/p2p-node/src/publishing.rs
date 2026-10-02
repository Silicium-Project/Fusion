//! Publishing a task queued by the API: share its scene by hash, split a
//! whole-image render into fragments ([`crate::jobs`]), then for each task
//! sign the proposal in the task book, store the DHT record and gossip it.
//! When configured, this node also works on its own tasks.

use crate::{
    content::ContentStore,
    jobs::{self, JobSettings, JobStore},
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
    share_scene(context, &mut task).await;
    let tasks = split_job(context, jobs, settings, task);
    for task in &tasks {
        publish_one(swarm, topic, context, settings, task);
    }
    tasks
}

/// Copies the scene into the content store, so peers can fetch it by hash.
async fn share_scene(context: &NodeContext, task: &mut NetworkTask) {
    match context.content.add_file(&task.scene_path).await {
        Ok(sha256) => {
            task.scene_path = ContentStore::relative_path(&sha256);
            task.scene_sha256 = Some(sha256);
        }
        Err(err) => println!(" Scene of {} not shared: {err}", task.task_id),
    }
}

/// The fragments of `task`'s job, or `task` alone when it is not split.
fn split_job(
    context: &NodeContext,
    jobs: &JobStore,
    settings: &PublishSettings,
    task: NetworkTask,
) -> Vec<NetworkTask> {
    let scene = std::fs::read_to_string(context.content.absolute(&task.scene_path));
    let Some((manifest, fragments)) = scene
        .ok()
        .and_then(|text| jobs::split(&task, &text, &settings.jobs))
    else {
        return vec![task];
    };
    let count = fragments.len();
    match jobs.add(manifest) {
        Ok(()) => {
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
        terms: settings.terms,
    };
    match context.taskbook.append_signed(&task.task_id, proposal) {
        Ok(event) => publish_taskbook_event(swarm, topic, &event),
        Err(err) => {
            println!(" Task book refused task {}: {err}", task.task_id);
            return;
        }
    }
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
