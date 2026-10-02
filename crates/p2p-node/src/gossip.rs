//! Incoming gossip messages: task-book events, backfill and content
//! requests and answers, and tasks (admitted, then handed to the worker).

use crate::{
    admission::SecurityConfig,
    backfill,
    content::{MAX_CONTENT_BYTES, hex_decode, hex_encode},
    processing::NodeContext,
    task::GossipMessage,
    worker::process_task,
};
use libp2p::{PeerId, gossipsub};
use silicium_node_core::{p2p::TaskEnvelope, taskbook::TaskEvent};

/// Handles one gossip message; returns the messages to send back (stored
/// events answering a backfill request, content answering a content request).
pub(crate) fn handle(
    context: &NodeContext,
    security: &SecurityConfig,
    local_peer_id: PeerId,
    peer_id: PeerId,
    message: gossipsub::Message,
) -> Vec<GossipMessage> {
    println!(" Received message from {peer_id}");
    match serde_json::from_slice::<GossipMessage>(&message.data) {
        Ok(GossipMessage::TaskEvent(event)) => {
            receive_event(context, peer_id, event);
            Vec::new()
        }
        Ok(GossipMessage::TaskEventsRequest {
            author,
            after_sequence,
        }) => backfill::answer(&context.taskbook, &author, after_sequence)
            .into_iter()
            .map(GossipMessage::TaskEvent)
            .collect(),
        Ok(GossipMessage::ContentRequest { sha256 }) => context
            .content
            .get(&sha256)
            .map(|bytes| GossipMessage::ContentResponse {
                sha256,
                data_hex: hex_encode(&bytes),
            })
            .into_iter()
            .collect(),
        Ok(GossipMessage::ContentResponse { sha256, data_hex }) => {
            let stored = data_hex.len() <= 2 * MAX_CONTENT_BYTES
                && hex_decode(&data_hex)
                    .is_some_and(|bytes| context.content.receive(&sha256, &bytes));
            if stored {
                println!(" Received content {sha256} from {peer_id}");
            }
            Vec::new()
        }
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
    match security.admit_remote(source, local_peer_id, envelope) {
        Ok(task) => {
            let context = context.clone();
            tokio::spawn(async move { process_task(context, task).await });
        }
        Err(reason) => println!(" Ignored task from {peer_id}: {reason}"),
    }
}
