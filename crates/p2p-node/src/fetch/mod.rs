//! Downloading content from peers: find holders through DHT provider records
//! and connected peers, ask them one at a time over the
//! `/silicium/content/1` request-response protocol, keep the first answer
//! that hashes to the requested value, and serve this node's own content to
//! others. Connected peers are probed in bounded parallel groups while the
//! provider lookup runs, so slow peers cannot hold up a result another worker
//! can already serve.

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

fn trace_content(message: impl std::fmt::Display) {
    if std::env::var("SILICIUM_P2P_CONTENT_TRACE")
        .is_ok_and(|value| matches!(value.trim(), "1" | "true" | "yes" | "on"))
    {
        eprintln!(" P2P content: {message}");
    }
}

/// Request-response protocol name.
pub(crate) const PROTOCOL: &str = "/silicium/content/1";
/// Parallel probes keep one slow or unreachable peer from blocking every
/// other content holder in the node's connection set.
const MAX_IN_FLIGHT: usize = 4;

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
    /// Number of requests awaiting answers for this content.
    in_flight: usize,
    /// Connected peers when the lookup ended, asked once the holders failed.
    fallback: Vec<PeerId>,
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
        connected: Vec<PeerId>,
    ) -> Vec<(String, PeerId)> {
        let abandoned = if let Some(download) = self.downloads.get_mut(&sha256) {
            // ContentStore::ensure gives each caller a bounded wait. A request
            // or provider lookup can outlive that caller, so discard an old
            // fetch once every waiter has gone away; otherwise later retries
            // would keep joining a download that can no longer make progress.
            download.waiters.retain(|waiter| !waiter.is_closed());
            if download.waiters.is_empty() {
                true
            } else {
                download.waiters.push(reply);
                return Vec::new();
            }
        } else {
            false
        };
        if abandoned {
            trace_content(format!(
                "restarting {sha256}; previous download has no live waiters"
            ));
            self.finish(&sha256, false);
        }
        let query = kademlia.get_providers(kad::RecordKey::new(&sha256));
        self.queries.insert(query, sha256.clone());
        self.downloads.insert(
            sha256.clone(),
            Download {
                // Ask currently connected peers immediately. The DHT query
                // continues in parallel and adds announced providers as it
                // discovers them.
                candidates: connected.into(),
                waiters: vec![reply],
                asked: Vec::new(),
                in_flight: 0,
                fallback: Vec::new(),
            },
        );
        self.next_candidates(&sha256)
    }

    /// Adds holders found in the DHT; returns the content to ask for next.
    pub(crate) fn on_providers(
        &mut self,
        query: kad::QueryId,
        providers: impl IntoIterator<Item = PeerId>,
        finished: bool,
        connected: &[PeerId],
    ) -> Vec<(String, PeerId)> {
        let Some(sha256) = self.queries.get(&query).cloned() else {
            return Vec::new();
        };
        if finished {
            self.queries.remove(&query);
        }
        let Some(download) = self.downloads.get_mut(&sha256) else {
            return Vec::new();
        };
        let mut preferred = Vec::new();
        for peer in providers {
            if !download.asked.contains(&peer) && !preferred.contains(&peer) {
                download.candidates.retain(|candidate| candidate != &peer);
                preferred.push(peer);
            }
        }
        // A provider record is evidence that this peer has the content, so
        // try it before the speculative direct-peer search already queued.
        for peer in preferred.into_iter().rev() {
            download.candidates.push_front(peer);
        }
        if finished {
            download.fallback = connected.to_vec();
        }
        self.next_candidates(&sha256)
    }

    /// Fills the bounded request window, or fails once no peer can help.
    fn next_candidates(&mut self, sha256: &str) -> Vec<(String, PeerId)> {
        let mut next = Vec::new();
        loop {
            let candidate = {
                let Some(download) = self.downloads.get_mut(sha256) else {
                    break;
                };
                if download.in_flight >= MAX_IN_FLIGHT {
                    break;
                }
                if download.candidates.is_empty() {
                    // No holder left to ask: try the other connected peers.
                    let untried: Vec<PeerId> = std::mem::take(&mut download.fallback)
                        .into_iter()
                        .filter(|peer| !download.asked.contains(peer))
                        .collect();
                    download.candidates.extend(untried);
                }
                match download.candidates.pop_front() {
                    Some(peer) => {
                        download.asked.push(peer);
                        // Reserve this slot before producing the next candidate.
                        download.in_flight += 1;
                        Some(peer)
                    }
                    None => None,
                }
            };
            if let Some(peer) = candidate {
                next.push((sha256.to_string(), peer));
            } else {
                let still_querying = self.queries.values().any(|value| value == sha256);
                let no_requests = self
                    .downloads
                    .get(sha256)
                    .is_none_or(|download| download.in_flight == 0);
                if !still_querying && no_requests {
                    self.finish(sha256, false);
                }
                break;
            }
        }
        next
    }

    /// Remembers which content a sent request is for.
    pub(crate) fn sent(&mut self, request: OutboundRequestId, sha256: String) {
        self.requests.insert(request, sha256);
    }

    /// Forgets a finished request; returns its content hash.
    fn answered(&mut self, request: OutboundRequestId) -> Option<String> {
        let sha256 = self.requests.remove(&request)?;
        if let Some(download) = self.downloads.get_mut(&sha256) {
            download.in_flight = download.in_flight.saturating_sub(1);
        }
        Some(sha256)
    }

    /// Handles an answer; returns the next peer to ask when it did not help.
    pub(crate) fn on_response(
        &mut self,
        store: &ContentStore,
        request: OutboundRequestId,
        response: ContentResponse,
    ) -> Vec<(String, PeerId)> {
        let Some(sha256) = self.answered(request) else {
            return Vec::new();
        };
        let delivered = response.sha256 == sha256
            && response
                .data
                .is_some_and(|bytes| store.put_verified(&sha256, &bytes));
        if delivered {
            self.finish(&sha256, true);
            return Vec::new();
        }
        self.next_candidates(&sha256)
    }

    /// Handles a failed request; returns the next peer to ask.
    pub(crate) fn on_failure(&mut self, request: OutboundRequestId) -> Vec<(String, PeerId)> {
        let Some(sha256) = self.answered(request) else {
            return Vec::new();
        };
        self.next_candidates(&sha256)
    }

    fn finish(&mut self, sha256: &str, success: bool) {
        if let Some(download) = self.downloads.remove(sha256) {
            for waiter in download.waiters {
                let _ = waiter.send(success);
            }
        }
        self.requests.retain(|_, value| value != sha256);
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
pub(crate) mod serde_bytes_compat {
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
fn ask(swarm: &mut Swarm<P2pBehaviour>, fetcher: &mut Fetcher, next: Vec<(String, PeerId)>) {
    for (sha256, peer) in next {
        trace_content(format!("request {sha256} -> {peer}"));
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
            let connected: Vec<PeerId> = swarm.connected_peers().copied().collect();
            trace_content(format!(
                "start {sha256}; {} connected peer candidate(s)",
                connected.len()
            ));
            let next = fetcher.start(
                &mut swarm.behaviour_mut().kademlia,
                sha256,
                reply,
                connected,
            );
            ask(swarm, fetcher, next);
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

/// Handles provider lookups of downloads. Routine routing and inbound DHT
/// events are intentionally ignored: workers generate them continuously, and
/// logging every event can exhaust the VPS log volume.
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
        return;
    };
    if let Some(sha256) = fetcher.queries.get(&id) {
        match &result {
            Ok(kad::GetProvidersOk::FoundProviders { providers, .. }) => trace_content(format!(
                "DHT providers for {sha256}: {}",
                providers.len()
            )),
            Ok(kad::GetProvidersOk::FinishedWithNoAdditionalRecord { .. }) => {
                trace_content(format!("DHT lookup finished without more providers for {sha256}"));
            }
            Err(error) => trace_content(format!("DHT lookup failed for {sha256}: {error:?}")),
        }
    }
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
            peer,
            message:
                request_response::Message::Request {
                    request, channel, ..
                },
            ..
        } => {
            let response = serve(store, request);
            trace_content(format!(
                "serve {} to {peer}: {} byte(s)",
                response.sha256,
                response.data.as_ref().map_or(0, Vec::len)
            ));
            let _ = swarm
                .behaviour_mut()
                .content
                .send_response(channel, response);
            Vec::new()
        }
        request_response::Event::Message {
            peer,
            message:
                request_response::Message::Response {
                    request_id,
                    response,
                },
            ..
        } => {
            let requested = fetcher.requests.get(&request_id).cloned().unwrap_or_default();
            trace_content(format!(
                "response {requested} <- {peer}: {} byte(s), response hash {}",
                response.data.as_ref().map_or(0, Vec::len),
                response.sha256
            ));
            fetcher.on_response(store, request_id, response)
        }
        request_response::Event::OutboundFailure {
            peer,
            request_id,
            error,
            ..
        } => {
            let requested = fetcher.requests.get(&request_id).cloned().unwrap_or_default();
            trace_content(format!("request {requested} -> {peer} failed: {error:?}"));
            fetcher.on_failure(request_id)
        }
        _ => Vec::new(),
    };
    ask(swarm, fetcher, next);
}

#[cfg(test)]
mod tests;
