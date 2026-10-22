//! Incoming gossip messages: task-book events, backfill requests, and tasks
//! (admitted, then handed to the worker).

use crate::{
    admission::SecurityConfig,
    backfill,
    peers::{
        current_unix_seconds, online_compute_authors, PROFILE_MAX_FUTURE_SKEW_SECONDS,
        PROFILE_STALE_AFTER_SECONDS,
    },
    processing::NodeContext,
    task::{GossipMessage, PeerProfile},
    worker::process_task,
};
use libp2p::{PeerId, gossipsub};
use silicium_node_core::{p2p::TaskEnvelope, taskbook::TaskEvent};
use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex},
    time::Duration,
};

pub(crate) type PeerProfiles = Arc<Mutex<BTreeMap<String, PeerProfile>>>;
const MAX_PENDING_ADMISSIONS: usize = 512;
const DELEGATION_ADMISSION_RETRIES: usize = 80;

/// Handles one gossip message; returns the messages to send back (stored
/// events answering a backfill request).
pub(crate) fn handle(
    context: &NodeContext,
    security: &SecurityConfig,
    local_peer_id: PeerId,
    peer_id: PeerId,
    message: gossipsub::Message,
    peer_profiles: &PeerProfiles,
) -> Vec<GossipMessage> {
    match serde_json::from_slice::<GossipMessage>(&message.data) {
        Ok(GossipMessage::TaskEvent(event)) => {
            receive_event(context, peer_id, event);
            Vec::new()
        }
        Ok(GossipMessage::PeerHeartbeat(profile)) => {
            // `peer_id` is the immediate propagation source, which may be a
            // relay forwarding another peer's signed heartbeat. Bind the
            // profile to the gossipsub message author instead.
            let expected_peer_id = message.source.map(|source| source.to_string());
            if expected_peer_id.as_deref() != Some(profile.peer_id.as_str())
                || profile.node_id.trim().is_empty()
            {
                println!(" Ignored invalid heartbeat from {peer_id}");
                return Vec::new();
            }
            // Keep the origin's signed timestamp. Re-stamping a relayed
            // heartbeat here lets cached messages make offline peers appear
            // online again and can overwrite a newer runtime profile.
            let age = current_unix_seconds().saturating_sub(profile.last_seen_unix);
            if profile.last_seen_unix <= 0
                || age > PROFILE_STALE_AFTER_SECONDS
                || age < -PROFILE_MAX_FUTURE_SKEW_SECONDS
            {
                println!(" Ignored stale heartbeat from {peer_id}");
                return Vec::new();
            }
            if let Ok(mut profiles) = peer_profiles.lock() {
                let should_replace = profiles
                    .get(&profile.node_id)
                    .is_none_or(|known| {
                        known.peer_id != profile.peer_id
                            || known.last_seen_unix <= profile.last_seen_unix
                    });
                if should_replace {
                    profiles.insert(profile.node_id.clone(), profile);
                }
                let authors = online_compute_authors(
                    &local_peer_id.to_string(),
                    &profiles,
                    current_unix_seconds(),
                );
                if let Ok(mut available) = context.available_compute_authors.lock() {
                    *available = authors;
                }
            }
            Vec::new()
        }
        Ok(GossipMessage::TaskEventsRequest {
            author,
            after_sequence,
        }) => backfill::answer(&context.taskbook, &author, after_sequence)
            .into_iter()
            .map(GossipMessage::TaskEvent)
            .collect(),
        Ok(GossipMessage::Task(envelope)) => {
            admit(
                context,
                security,
                local_peer_id,
                peer_id,
                message.source,
                envelope,
            );
            Vec::new()
        }
        Err(_) => {
            // Older peers gossip a bare task envelope.
            match serde_json::from_slice::<TaskEnvelope>(&message.data) {
                Ok(envelope) => admit(
                    context,
                    security,
                    local_peer_id,
                    peer_id,
                    message.source,
                    envelope,
                ),
                Err(_) => println!(" Could not parse task book or NetworkTask message"),
            }
            Vec::new()
        }
    }
}

fn receive_event(context: &NodeContext, peer_id: PeerId, event: TaskEvent) {
    match context.taskbook.append_remote(event) {
        Ok(received) if received.pending => {
            println!(" Task book event from {peer_id} waits for its predecessors")
        }
        Ok(received) if received.accepted.is_empty() => {}
        Ok(received) => println!(
            " Accepted {} task book event(s) from {peer_id}",
            received.accepted.len()
        ),
        Err(err) => println!(" Rejected task book event from {peer_id}: {err}"),
    }
}

fn admit(
    context: &NodeContext,
    security: &SecurityConfig,
    local_peer_id: PeerId,
    peer_id: PeerId,
    source: Option<PeerId>,
    envelope: TaskEnvelope,
) {
    let task_id = envelope.task_id.clone();
    let Some(pending) = PendingAdmission::enter(context, &task_id) else {
        return;
    };
    let context = context.clone();
    let security = security.clone();
    tokio::spawn(async move {
        for retry in 0..=DELEGATION_ADMISSION_RETRIES {
            match security.admit_received(&context, source, local_peer_id, envelope.clone()) {
                Ok(task) => {
                    drop(pending);
                    process_task(context, task).await;
                    return;
                }
                Err(reason)
                    if retryable_delegation_admission(&reason)
                        && retry < DELEGATION_ADMISSION_RETRIES =>
                {
                    tokio::time::sleep(Duration::from_millis(250)).await;
                }
                Err(reason) => {
                    println!(" Ignored task from {peer_id}: {reason}");
                    return;
                }
            }
        }
        println!(" Ignored task from {peer_id}: delegation_state_not_ready");
    });
}

fn retryable_delegation_admission(reason: &str) -> bool {
    matches!(
        reason,
        "delegation_parent_pending"
            | "delegation_proposal_pending"
            | "delegation_parent_proposal_pending"
            | "delegation_author_not_accepted_parent_claimant"
    )
}

struct PendingAdmission {
    context: NodeContext,
    task_id: String,
}

impl PendingAdmission {
    fn enter(context: &NodeContext, task_id: &str) -> Option<Self> {
        let mut pending = context.pending_admissions.lock().ok()?;
        if pending.len() >= MAX_PENDING_ADMISSIONS || !pending.insert(task_id.to_string()) {
            return None;
        }
        Some(Self {
            context: context.clone(),
            task_id: task_id.to_string(),
        })
    }
}

impl Drop for PendingAdmission {
    fn drop(&mut self) {
        if let Ok(mut pending) = self.context.pending_admissions.lock() {
            pending.remove(&self.task_id);
        }
    }
}
