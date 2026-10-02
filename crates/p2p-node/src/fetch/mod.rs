//! Downloading content from peers: find holders through DHT provider records
//! (falling back to every connected peer), ask them one at a time over the
//! `/silicium/content/1` request-response protocol, keep the first answer
//! that hashes to the requested value, and serve this node's own content to
//! others.

use crate::{
    content::{ContentCommand, ContentStore, MAX_CONTENT_BYTES},
    swarm::P2pBehaviour,
};
use libp2p::{
    PeerId, StreamProtocol, Swarm, kad,
    request_response::{self, OutboundRequestId, ProtocolSupport},
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, VecDeque};
use tokio::sync::oneshot;

/// Request-response protocol name.
pub(crate) const PROTOCOL: &str = "/silicium/content/1";

/// Asks a peer for one content.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct ContentRequest {
    pub(crate) sha256: String,
}

/// The content, or `None` when the peer does not have it.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct ContentResponse {
    pub(crate) sha256: String,
    #[serde(with = "serde_bytes_compat")]
    pub(crate) data: Option<Vec<u8>>,
}

/// The behaviour added to the swarm.
pub(crate) type ContentBehaviour =
    request_response::cbor::Behaviour<ContentRequest, ContentResponse>;

/// Builds the request-response behaviour with a response size fit for images.
pub(crate) fn behaviour() -> ContentBehaviour {
    let codec = request_response::cbor::codec::Codec::default()
        .set_response_size_maximum(MAX_CONTENT_BYTES as u64 + 1024);
    request_response::Behaviour::with_codec(
        codec,
        [(StreamProtocol::new(PROTOCOL), ProtocolSupport::Full)],
        request_response::Config::default()
            .with_request_timeout(std::time::Duration::from_secs(60)),
    )
}

/// One download in progress.
struct Download {
    candidates: VecDeque<PeerId>,
    waiters: Vec<oneshot::Sender<bool>>,
    asked: Vec<PeerId>,
    /// True while a request to a peer awaits its answer (one at a time).
    in_flight: bool,
}

/// Downloads in progress, by content hash, and the queries serving them.
#[derive(Default)]
pub(crate) struct Fetcher {
    downloads: BTreeMap<String, Download>,
    queries: HashMap<kad::QueryId, String>,
    requests: BTreeMap<OutboundRequestId, String>,
}

impl Fetcher {
    /// Starts (or joins) the download of `sha256`.
    pub(crate) fn start(
        &mut self,
        kademlia: &mut kad::Behaviour<kad::store::MemoryStore>,
        sha256: String,
        reply: oneshot::Sender<bool>,
    ) {
        if let Some(download) = self.downloads.get_mut(&sha256) {
            download.waiters.push(reply);
            return;
        }
        let query = kademlia.get_providers(kad::RecordKey::new(&sha256));
        self.queries.insert(query, sha256.clone());
        self.downloads.insert(
            sha256,
            Download {
                candidates: VecDeque::new(),
                waiters: vec![reply],
                asked: Vec::new(),
                in_flight: false,
            },
        );
    }

    /// Adds holders found in the DHT; returns the content to ask for next.
    pub(crate) fn on_providers(
        &mut self,
        query: kad::QueryId,
        providers: impl IntoIterator<Item = PeerId>,
        finished: bool,
        connected: &[PeerId],
    ) -> Option<(String, PeerId)> {
        let sha256 = self.queries.get(&query)?.clone();
        if finished {
            self.queries.remove(&query);
        }
        let download = self.downloads.get_mut(&sha256)?;
        for peer in providers {
            if !download.candidates.contains(&peer) && !download.asked.contains(&peer) {
                download.candidates.push_back(peer);
            }
        }
        if finished && download.candidates.is_empty() && download.asked.is_empty() {
            // Nobody announced it: try every connected peer.
            download.candidates.extend(connected.iter().copied());
        }
        if download.in_flight {
            return None;
        }
        self.next_candidate(&sha256)
    }

    /// Picks the next peer to ask, or fails the download when none is left.
    fn next_candidate(&mut self, sha256: &str) -> Option<(String, PeerId)> {
        let download = self.downloads.get_mut(sha256)?;
        match download.candidates.pop_front() {
            Some(peer) => {
                download.asked.push(peer);
                Some((sha256.to_string(), peer))
            }
            None => {
                let still_querying = self.queries.values().any(|value| value == sha256);
                if !still_querying && !download.in_flight {
                    self.finish(sha256, false);
                }
                None
            }
        }
    }

    /// Remembers which content a sent request is for.
    pub(crate) fn sent(&mut self, request: OutboundRequestId, sha256: String) {
        if let Some(download) = self.downloads.get_mut(&sha256) {
            download.in_flight = true;
        }
        self.requests.insert(request, sha256);
    }

    /// Forgets a finished request; returns its content hash.
    fn answered(&mut self, request: OutboundRequestId) -> Option<String> {
        let sha256 = self.requests.remove(&request)?;
        if let Some(download) = self.downloads.get_mut(&sha256) {
            download.in_flight = false;
        }
        Some(sha256)
    }

    /// Handles an answer; returns the next peer to ask when it did not help.
    pub(crate) fn on_response(
        &mut self,
        store: &ContentStore,
        request: OutboundRequestId,
        response: ContentResponse,
    ) -> Option<(String, PeerId)> {
        let sha256 = self.answered(request)?;
        let delivered = response.sha256 == sha256
            && response
                .data
                .is_some_and(|bytes| store.put_verified(&sha256, &bytes));
        if delivered {
            self.finish(&sha256, true);
            return None;
        }
        self.next_candidate(&sha256)
    }

    /// Handles a failed request; returns the next peer to ask.
    pub(crate) fn on_failure(&mut self, request: OutboundRequestId) -> Option<(String, PeerId)> {
        let sha256 = self.answered(request)?;
        self.next_candidate(&sha256)
    }

    fn finish(&mut self, sha256: &str, success: bool) {
        if let Some(download) = self.downloads.remove(sha256) {
            for waiter in download.waiters {
                let _ = waiter.send(success);
            }
        }
        self.queries.retain(|_, value| value != sha256);
    }
}

/// Answer to a peer's request: the content when this node has it.
pub(crate) fn serve(store: &ContentStore, request: ContentRequest) -> ContentResponse {
    ContentResponse {
        data: store.get(&request.sha256),
        sha256: request.sha256,
    }
}

/// CBOR byte strings for `Option<Vec<u8>>` (a plain `Vec<u8>` would be
/// encoded as an array of integers, several times larger).
mod serde_bytes_compat {
    use serde::{Deserialize, Deserializer, Serializer, de};

    pub(crate) fn serialize<S: Serializer>(
        data: &Option<Vec<u8>>,
        serializer: S,
    ) -> Result<S::Ok, S::Error> {
        match data {
            Some(bytes) => serializer.serialize_some(&Bytes(bytes)),
            None => serializer.serialize_none(),
        }
    }

    pub(crate) fn deserialize<'de, D: Deserializer<'de>>(
        deserializer: D,
    ) -> Result<Option<Vec<u8>>, D::Error> {
        Option::<ByteBuf>::deserialize(deserializer).map(|value| value.map(|buf| buf.0))
    }

    struct Bytes<'a>(&'a [u8]);

    impl serde::Serialize for Bytes<'_> {
        fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
            serializer.serialize_bytes(self.0)
        }
    }

    struct ByteBuf(Vec<u8>);

    impl<'de> Deserialize<'de> for ByteBuf {
        fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
            struct Visitor;
            impl<'de> de::Visitor<'de> for Visitor {
                type Value = ByteBuf;
                fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                    formatter.write_str("a byte string")
                }
                fn visit_bytes<E: de::Error>(self, value: &[u8]) -> Result<ByteBuf, E> {
                    Ok(ByteBuf(value.to_vec()))
                }
                fn visit_byte_buf<E: de::Error>(self, value: Vec<u8>) -> Result<ByteBuf, E> {
                    Ok(ByteBuf(value))
                }
                fn visit_seq<A: de::SeqAccess<'de>>(self, mut seq: A) -> Result<ByteBuf, A::Error> {
                    let mut bytes = Vec::new();
                    while let Some(byte) = seq.next_element()? {
                        bytes.push(byte);
                    }
                    Ok(ByteBuf(bytes))
                }
            }
            deserializer.deserialize_bytes(Visitor)
        }
    }
}

/// Sends the request chosen by the fetcher, if any.
fn ask(swarm: &mut Swarm<P2pBehaviour>, fetcher: &mut Fetcher, next: Option<(String, PeerId)>) {
    if let Some((sha256, peer)) = next {
        let request = swarm.behaviour_mut().content.send_request(
            &peer,
            ContentRequest {
                sha256: sha256.clone(),
            },
        );
        fetcher.sent(request, sha256);
    }
}

/// Handles a command from the node's tasks.
pub(crate) fn handle_command(
    swarm: &mut Swarm<P2pBehaviour>,
    fetcher: &mut Fetcher,
    command: ContentCommand,
) {
    match command {
        ContentCommand::Fetch { sha256, reply } => {
            fetcher.start(&mut swarm.behaviour_mut().kademlia, sha256, reply);
        }
        ContentCommand::Provide { sha256 } => {
            if let Err(err) = swarm
                .behaviour_mut()
                .kademlia
                .start_providing(kad::RecordKey::new(&sha256))
            {
                println!(" Could not announce content {sha256}: {err:?}");
            }
        }
    }
}

/// Handles the provider lookups of downloads; other Kademlia events are
/// only logged.
pub(crate) fn handle_kademlia(
    swarm: &mut Swarm<P2pBehaviour>,
    fetcher: &mut Fetcher,
    event: kad::Event,
) {
    let kad::Event::OutboundQueryProgressed {
        id,
        result: kad::QueryResult::GetProviders(result),
        step,
        ..
    } = event
    else {
        println!(" Kademlia event: {event:?}");
        return;
    };
    let connected: Vec<PeerId> = swarm.connected_peers().copied().collect();
    let next = match result {
        Ok(kad::GetProvidersOk::FoundProviders { providers, .. }) => {
            fetcher.on_providers(id, providers, step.last, &connected)
        }
        Ok(kad::GetProvidersOk::FinishedWithNoAdditionalRecord { .. }) | Err(_) => {
            fetcher.on_providers(id, Vec::new(), true, &connected)
        }
    };
    ask(swarm, fetcher, next);
}

/// Serves requests and follows the answers of the content protocol.
pub(crate) fn handle_content(
    swarm: &mut Swarm<P2pBehaviour>,
    fetcher: &mut Fetcher,
    store: &ContentStore,
    event: request_response::Event<ContentRequest, ContentResponse>,
) {
    let next = match event {
        request_response::Event::Message {
            message:
                request_response::Message::Request {
                    request, channel, ..
                },
            ..
        } => {
            let _ = swarm
                .behaviour_mut()
                .content
                .send_response(channel, serve(store, request));
            None
        }
        request_response::Event::Message {
            message:
                request_response::Message::Response {
                    request_id,
                    response,
                },
            ..
        } => fetcher.on_response(store, request_id, response),
        request_response::Event::OutboundFailure { request_id, .. } => {
            fetcher.on_failure(request_id)
        }
        _ => None,
    };
    ask(swarm, fetcher, next);
}

#[cfg(test)]
mod tests;
