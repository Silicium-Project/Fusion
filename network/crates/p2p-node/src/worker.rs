//! Worker side of the task book: claim the open attempt of a task, wait for
//! the publisher to accept this node, keep the lease alive while computing,
//! then publish the result or release the attempt.

use crate::{
    activity::Role, content::ContentStore, processing::NodeContext, results::CONTENT_SCHEME,
    storage::now_ms, task::NetworkTask,
};
use sha2::{Digest, Sha256};
use silicium_node_core::{
    p2p::TaskEnvelope,
    taskbook::{
        DerivedTaskState, DerivedTaskStatus, MAX_ATTEMPTS, PayloadRef, TASK_ID_SEPARATOR,
        TaskEventBody, TaskTerms,
    },
};
use std::{
    collections::BTreeSet,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};

/// How long to wait for the task's proposal to reach this node.
const PROPOSAL_WAIT: Duration = Duration::from_secs(10);
/// How long to wait for the publisher's decision on this node's claim.
const ACCEPT_WAIT: Duration = Duration::from_secs(30);
const POLL_INTERVAL: Duration = Duration::from_millis(250);
const MAX_DELEGATION_DEPTH: u8 = 4;

/// Signs, stores and queues for gossip one event of this node.
pub(crate) async fn record_task_event(context: &NodeContext, task_id: &str, body: TaskEventBody) {
    match context.taskbook.append_signed(task_id, body) {
        Ok(event) => {
            if context.tx_events.send(event).await.is_err() {
                println!(" Task book event channel closed for {task_id}");
            }
        }
        Err(err) => println!(" Failed to persist task book event for {task_id}: {err}"),
    }
}

/// Handles a task received from the network (see the module documentation).
pub(crate) async fn process_task(context: NodeContext, mut task: NetworkTask) {
    if !crate::workload::is_allowed(&task) {
        return;
    }
    let task_id = task.task_id.clone();
    // The publisher announces an unclaimed task again until someone claims
    // it: handle each task once at a time.
    let Some(_active) = ActiveTask::enter(&context, &task_id) else {
        return;
    };
    if !ensure_scene(&context, &mut task).await {
        println!(" Scene of task {task_id} unavailable; not claiming it");
        return;
    }
    context.remember_task(&task);
    if !context.roles.compute {
        // Verify-only node: it keeps the task to check results, not to claim it.
        return;
    }
    if let Some(payment) = task.solana_payment.as_ref()
        && !crate::solana_settlement::ready(payment).await
    {
        println!(" Paid task {task_id} is waiting for a linked Devnet wallet and valid escrow");
        return;
    }
    // A workload needing local resources (a model to download) gets them
    // first; the publisher announces the task again until someone claims it.
    if let Some(workload) = crate::workload::of(&task)
        && !workload.ensure_ready(&context, &task).await
    {
        println!(" Not ready for task {task_id} yet; claiming it when announced again");
        return;
    }
    // Claim only with a free compute slot: the other fragments stay open for
    // other nodes meanwhile.
    let Ok(_slot) = context.compute_slots.clone().acquire_owned().await else {
        return;
    };
    let Some((attempt, terms)) = open_attempt(&context, &task_id).await else {
        println!(" No open attempt for task {task_id}; not claiming it");
        return;
    };
    context.activity.received(&task_id);
    record_task_event(&context, &task_id, TaskEventBody::ClaimProposed { attempt }).await;
    if !wait_until_accepted(&context, &task_id, attempt).await {
        println!(" Claim on task {task_id} (attempt {attempt}) not accepted for this node");
        return;
    }
    context.activity.started(&task_id, Role::Compute);
    let renewer = LeaseRenewer::start(context.clone(), task_id.clone(), attempt, terms);
    let outcome = match crate::workload::of(&task) {
        Some(workload) => execute_task(&context, &task, workload, attempt, _slot).await,
        None => None,
    };
    renewer.stop();
    let body = match outcome {
        Some(outcome) => match share_result(&context, &task).await {
            Some(result) => {
                let settled = match task.solana_payment.as_ref() {
                    Some(payment) => {
                        crate::solana_settlement::submit(payment, &result.sha256).await
                    }
                    None => true,
                };
                if settled {
                    TaskEventBody::ResultPublished {
                        attempt,
                        result,
                        milestones: outcome.milestones,
                    }
                } else {
                    TaskEventBody::ClaimReleased { attempt }
                }
            }
            None => TaskEventBody::ClaimReleased { attempt },
        },
        None => TaskEventBody::ClaimReleased { attempt },
    };
    let produced = matches!(body, TaskEventBody::ResultPublished { .. });
    context.activity.finished(&task_id, Role::Compute, produced);
    record_task_event(&context, &task_id, body).await;
}

async fn execute_task(
    context: &NodeContext,
    task: &NetworkTask,
    workload: &'static dyn crate::workload::Workload,
    attempt: u32,
    compute_slot: tokio::sync::OwnedSemaphorePermit,
) -> Option<crate::workload::ComputeOutcome> {
    let available_peers = context
        .available_compute_authors
        .lock()
        .map(|peers| peers.len())
        .unwrap_or_default();
    if available_peers == 0 {
        println!(
            " Keeping {} local: no live compute peers in the gossip mesh",
            task.task_id
        );
        return workload.execute(context, task).await;
    }
    if task.delegation_depth >= MAX_DELEGATION_DEPTH {
        println!(
            " Keeping {} local: delegation depth {} reached the limit",
            task.task_id, task.delegation_depth
        );
        return workload.execute(context, task).await;
    }
    let Some((remote_score, local_score)) = bayesian_delegation_score(context) else {
        println!(
            " Keeping {} local: Bayesian history is unavailable",
            task.task_id
        );
        return workload.execute(context, task).await;
    };
    println!(
        " Delegation assessment for {}: {} live compute peer(s), remote {:.3}, local {:.3}",
        task.task_id, available_peers, remote_score, local_score
    );
    if remote_score <= local_score {
        println!(
            " Keeping {} local: Bayesian delegation score {:.3} does not beat local {:.3}",
            task.task_id, remote_score, local_score
        );
        return workload.execute(context, task).await;
    }
    let input = context.content.absolute(&task.scene_path);
    let Some((mut manifest, mut children)) =
        workload.split_subtask(task, &input, &context.job_settings)
    else {
        println!(
            " Keeping {} local: workload says this fragment is not splittable",
            task.task_id
        );
        return workload.execute(context, task).await;
    };
    if children.len() != 2 {
        println!(
            " Delegation refused for {}: only binary splits are supported",
            task.task_id
        );
        return None;
    }

    let payment_children = match task.solana_payment.as_ref() {
        Some(payment) => {
            let Some(parent_index) = payment.fragment_index else {
                println!(" Paid task {} has no parent fragment index", task.task_id);
                return None;
            };
            let Some(indexes) = child_fragment_indexes(payment.expected_fragments, parent_index)
            else {
                // No reserved child slots remain: compute this fragment as a
                // leaf and leave its escrow unit untouched.
                return workload.execute(context, task).await;
            };
            Some(indexes)
        }
        None => None,
    };

    let parent_hash = sha256_hex(task.task_id.as_bytes());
    let recovered_child_ids = recover_prior_child_ids(context, &parent_hash, &children);
    if recovered_child_ids.is_some() {
        println!(" Resuming prior delegation for {}", task.task_id);
    }
    for (index, child) in children.iter_mut().enumerate() {
        let child_id = recovered_child_ids
            .as_ref()
            .map(|ids| ids[index].clone())
            .unwrap_or_else(|| {
                let name = format!("d-{}-a{attempt}-{index}", &parent_hash[..16]);
                context.taskbook.owned_task_id(&name)
            });
        child.task_id = child_id.clone();
        child.output_path = TaskEnvelope::local_output_path_for(&child_id, Some(workload.id()))?;
        child.root_job_id = Some(
            task.root_job_id
                .clone()
                .unwrap_or_else(|| task.task_id.clone()),
        );
        child.parent_task_id = Some(task.task_id.clone());
        child.delegation_depth = task.delegation_depth.saturating_add(1);
        manifest.fragments[index].task_id = child_id;
        if let (Some(payment), Some(indexes)) = (task.solana_payment.as_ref(), payment_children) {
            let mut child_payment = payment.clone();
            child_payment.fragment_index = Some(indexes[index]);
            child.solana_payment = Some(child_payment);
        }
    }

    let mut child_hashes = Vec::with_capacity(2);
    for fragment in &manifest.fragments {
        let bytes = serde_json::to_vec(fragment).ok()?;
        child_hashes.push(sha256_hex(&bytes));
    }
    let manifest_bytes = serde_json::to_vec(&manifest).ok()?;
    let manifest_hash = sha256_hex(&manifest_bytes);

    // One on-chain transaction claims the paid parent, records its split,
    // and creates both child PDAs. If it fails, no child task is advertised.
    if let Some(payment) = task.solana_payment.as_ref()
        && !crate::solana_settlement::split(
            payment,
            &manifest_hash,
            &[
                (payment_children?[0], child_hashes[0].clone()),
                (payment_children?[1], child_hashes[1].clone()),
            ],
        )
        .await
    {
        println!(
            " Paid task {} split transaction was not confirmed",
            task.task_id
        );
        return None;
    }

    for child in &children {
        if context
            .taskbook
            .state(&child.task_id)
            .ok()
            .flatten()
            .is_none()
        {
            context.tx_publish.send(child.clone()).await.ok()?;
        }
    }
    println!(
        " Delegated {} into {} child tasks",
        task.task_id,
        children.len()
    );
    // Do not occupy a compute slot while waiting for the children. Otherwise
    // a mesh in which every worker subdivides simultaneously would deadlock.
    drop(compute_slot);

    let deadline = tokio::time::Instant::now()
        + Duration::from_secs(context.compute_timeout_s.saturating_mul(100).max(1_200));
    let mut results = vec![None; manifest.fragments.len()];
    loop {
        let mut all_ready = true;
        for (index, fragment) in manifest.fragments.iter().enumerate() {
            if results[index].is_some() {
                continue;
            }
            let Some(state) = context.taskbook.state(&fragment.task_id).ok().flatten() else {
                all_ready = false;
                continue;
            };
            if state.status == DerivedTaskStatus::Failed
                || state.status == DerivedTaskStatus::Cancelled
            {
                return None;
            }
            if state.status != DerivedTaskStatus::Finalized {
                all_ready = false;
                continue;
            }
            let Some(result) = state
                .attempts
                .last()
                .and_then(|attempt| attempt.result.as_ref())
            else {
                all_ready = false;
                continue;
            };
            if !context.content.ensure(&result.result.sha256).await {
                all_ready = false;
                continue;
            }
            let Some(bytes) = context.content.get(&result.result.sha256) else {
                all_ready = false;
                continue;
            };
            results[index] = Some(bytes);
        }
        if all_ready && results.iter().all(Option::is_some) {
            let child_payloads: Vec<Vec<u8>> = results.into_iter().flatten().collect();
            let combined = workload.combine_subtask_results(task, &child_payloads)?;
            let milestones = workload.subtask_result_milestones(task, &combined);
            let output = context.content.absolute(&task.output_path);
            if let Some(parent) = output.parent() {
                std::fs::create_dir_all(parent).ok()?;
            }
            std::fs::write(output, combined).ok()?;
            return Some(crate::workload::ComputeOutcome { milestones });
        }
        if tokio::time::Instant::now() >= deadline {
            println!(
                " Delegated task {} reached its network wait limit",
                task.task_id
            );
            return None;
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}

/// Probability that at least one connected peer produces a valid result,
/// using the Beta(1,1) posterior derived from the replicated task book. The
/// publisher uses the same posterior mean to rank claimants.
fn bayesian_delegation_score(context: &NodeContext) -> Option<(f64, f64)> {
    let peers = context.available_compute_authors.lock().ok()?.clone();
    if peers.is_empty() {
        return None;
    }
    let records = context
        .taskbook
        .with_book(|book| book.author_records(now_ms()))
        .ok()?;
    let local_author = context.taskbook.author();
    let local_score = records
        .get(&local_author)
        .copied()
        .unwrap_or_default()
        .score();

    let mut seen = BTreeSet::new();
    let mut probability_all_fail = 1.0;
    for author in peers {
        if let Some(author) = author.as_ref()
            && !seen.insert(author.clone())
        {
            continue;
        }
        let score = author
            .as_ref()
            .and_then(|author| records.get(author))
            .copied()
            .unwrap_or_default()
            .score();
        probability_all_fail *= 1.0 - score;
    }
    Some((1.0 - probability_all_fail, local_score))
}

/// A parent retry may be handled by a different peer after its first splitter
/// committed the child tasks. Reuse those task-book identities so the child
/// manifest still matches the immutable on-chain split commitment.
fn recover_prior_child_ids(
    context: &NodeContext,
    parent_hash: &str,
    candidates: &[NetworkTask],
) -> Option<[String; 2]> {
    if candidates.len() != 2 {
        return None;
    }
    let known = context.known_tasks.lock().ok()?;
    for prior_attempt in (1..=MAX_ATTEMPTS).rev() {
        let mut child_ids = Vec::with_capacity(2);
        let mut complete_pair = true;
        for (index, candidate) in candidates.iter().enumerate() {
            let name = format!("d-{}-a{prior_attempt}-{index}", &parent_hash[..16]);
            let Some(existing) = known.values().find(|existing| {
                existing
                    .task_id
                    .split_once(TASK_ID_SEPARATOR)
                    .is_some_and(|(_, existing_name)| existing_name == name)
                    && existing.region == candidate.region
                    && existing.byte_range == candidate.byte_range
                    && existing.workload == candidate.workload
                    && existing.scene_sha256 == candidate.scene_sha256
                    && existing.delegation_depth == candidate.delegation_depth.saturating_add(1)
            }) else {
                complete_pair = false;
                break;
            };
            child_ids.push(existing.task_id.clone());
        }
        if complete_pair {
            return child_ids.try_into().ok();
        }
    }
    None
}

pub(crate) fn child_fragment_indexes(
    initial_fragments: u32,
    parent_index: u32,
) -> Option<[u32; 2]> {
    const MAX_FRAGMENT_NODES: u32 = 1_000;
    if initial_fragments == 0 || parent_index >= MAX_FRAGMENT_NODES {
        return None;
    }
    let per_root = MAX_FRAGMENT_NODES.saturating_sub(initial_fragments) / initial_fragments;
    if per_root < 2 {
        return None;
    }
    let (root, local) = if parent_index < initial_fragments {
        (parent_index, 0)
    } else {
        let offset = parent_index - initial_fragments;
        let root = offset / per_root;
        if root >= initial_fragments {
            return None;
        }
        (root, offset % per_root + 1)
    };
    let first_local = local.saturating_mul(2).saturating_add(1);
    let second_local = first_local.saturating_add(1);
    (second_local <= per_root).then_some([
        initial_fragments + root * per_root + first_local - 1,
        initial_fragments + root * per_root + second_local - 1,
    ])
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// Stores the rendered image in the content store (announced to peers) and
/// returns the payload reference published with the result.
async fn share_result(context: &NodeContext, task: &NetworkTask) -> Option<PayloadRef> {
    match context.content.add_file(&task.output_path).await {
        Ok(sha256) => Some(PayloadRef {
            uri: format!("{CONTENT_SCHEME}{sha256}"),
            sha256,
        }),
        Err(err) => {
            println!(" Result image of {} not shared: {err}", task.task_id);
            None
        }
    }
}

/// Makes sure the task's scene is in the work directory, fetching it from
/// peers by hash when needed, and points the task at the local copy. Tasks
/// without a scene hash (older publishers) keep their path as is.
async fn ensure_scene(context: &NodeContext, task: &mut NetworkTask) -> bool {
    let Some(sha256) = task.scene_sha256.clone() else {
        return true;
    };
    if !context.content.ensure(&sha256).await {
        return false;
    }
    task.scene_path = ContentStore::relative_path(&sha256);
    true
}

/// Current derived state of `task_id`, `None` when unknown or unreadable.
fn current_state(context: &NodeContext, task_id: &str) -> Option<DerivedTaskState> {
    context.taskbook.state(task_id).ok().flatten()
}

/// Attempt open for claims and the task terms, waiting for the proposal
/// (it may arrive after the task itself).
async fn open_attempt(context: &NodeContext, task_id: &str) -> Option<(u32, TaskTerms)> {
    let deadline = Instant::now() + PROPOSAL_WAIT;
    loop {
        if let Some(state) = current_state(context, task_id) {
            return state.next_attempt.map(|attempt| (attempt, state.terms));
        }
        if Instant::now() >= deadline {
            return None;
        }
        tokio::time::sleep(POLL_INTERVAL).await;
    }
}

/// True once the publisher accepted this node for `attempt`; false when it
/// accepted someone else, the task ended, or no decision came in time.
async fn wait_until_accepted(context: &NodeContext, task_id: &str, attempt: u32) -> bool {
    let me = context.taskbook.author();
    let deadline = Instant::now() + ACCEPT_WAIT;
    while Instant::now() < deadline {
        if let Some(state) = current_state(context, task_id) {
            if let Some(accepted) = state.attempts.get(attempt as usize - 1) {
                return accepted.claimant == me;
            }
            if state.status.is_terminal() {
                return false;
            }
        }
        tokio::time::sleep(POLL_INTERVAL).await;
    }
    false
}

/// Marks a task as handled by this node until dropped.
struct ActiveTask {
    context: NodeContext,
    task_id: String,
}

impl ActiveTask {
    /// `None` when the task is already being handled.
    fn enter(context: &NodeContext, task_id: &str) -> Option<Self> {
        let mut active = context.active_tasks.lock().ok()?;
        active.insert(task_id.to_string()).then(|| Self {
            context: context.clone(),
            task_id: task_id.to_string(),
        })
    }
}

impl Drop for ActiveTask {
    fn drop(&mut self) {
        if let Ok(mut active) = self.context.active_tasks.lock() {
            active.remove(&self.task_id);
        }
    }
}

/// Renews the lease of a running attempt every third of the lease, within
/// the renewals the terms allow.
struct LeaseRenewer {
    stop: Arc<AtomicBool>,
    handle: tokio::task::JoinHandle<()>,
}

impl LeaseRenewer {
    fn start(context: NodeContext, task_id: String, attempt: u32, terms: TaskTerms) -> Self {
        let stop = Arc::new(AtomicBool::new(false));
        let flag = stop.clone();
        let period = Duration::from_millis((terms.lease_ms / 3).max(1_000));
        let handle = tokio::spawn(async move {
            for _ in 0..terms.max_renewals {
                tokio::time::sleep(period).await;
                if flag.load(Ordering::Relaxed) {
                    break;
                }
                record_task_event(&context, &task_id, TaskEventBody::LeaseRenewed { attempt })
                    .await;
            }
        });
        Self { stop, handle }
    }

    fn stop(self) {
        self.stop.store(true, Ordering::Relaxed);
        self.handle.abort();
    }
}
