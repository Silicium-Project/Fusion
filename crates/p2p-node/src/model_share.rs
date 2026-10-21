//! Model files shared between nodes: a node that has the pinned files of a
//! model (in its model store, see
//! `silicium_embedding::model::store::pinned`) announces each one in the DHT
//! under `silicium/models/v1/<store name>` and serves it by pieces over the
//! `/silicium/model/1` request-response protocol; a node preparing a model
//! gets a file from them when the Hub cannot give it (Hub down, file
//! changed under the pinned commit) or first, as `SILICIUM_AI_MODEL_SOURCES`
//! says.
//!
//! Nothing a peer sends is trusted: the pieces are written to a side file,
//! and the file enters the store only if its size and hash are the pinned
//! ones (otherwise the next peer is asked). A peer only serves files whose
//! name is a store name (`<sha256>` or `git-<sha1>`), never a path.
//!
//! The event loop owns the swarm: the node's tasks send it
//! [`ModelCommand`]s (find holders, ask a peer for a piece, announce a file)
//! through the sender given to [`connect`].

use crate::{fetch::serde_bytes_compat, swarm::P2pBehaviour};
use futures::{StreamExt, stream};
use libp2p::{
    PeerId, StreamProtocol, Swarm, kad,
    request_response::{self, OutboundRequestId, ProtocolSupport},
};
use serde::{Deserialize, Serialize};
use silicium_embedding::model::store::{ModelStore, PinnedFile, is_pinned_name};
use std::{
    collections::HashMap,
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::OnceLock,
    time::Duration,
};
use tokio::sync::{mpsc, oneshot};

/// Request-response protocol name.
pub(crate) const PROTOCOL: &str = "/silicium/model/1";
/// Largest piece asked for or sent.
pub(crate) const PIECE_BYTES: u32 = 4 << 20;
/// Pieces asked for at the same time from one peer.
const PIECES_IN_FLIGHT: usize = 4;
/// Peers asked for one file before giving up.
const MAX_PEERS: usize = 8;
/// Wait for the holders of a file.
const PROVIDERS_TIMEOUT: Duration = Duration::from_secs(30);
/// Wait for one piece.
const PIECE_TIMEOUT: Duration = Duration::from_secs(90);

/// DHT key under which the holders of the store file `name` are announced.
pub(crate) fn dht_key(name: &str) -> kad::RecordKey {
    kad::RecordKey::new(&format!("silicium/models/v1/{name}"))
}

/// Asks a peer for `length` bytes of the store file `name` from `offset`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct PieceRequest {
    pub(crate) name: String,
    pub(crate) offset: u64,
    pub(crate) length: u32,
}

/// A piece, with the size of the whole file; `data` is `None` when the peer
/// does not have the file (or the request is out of bounds).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct PieceResponse {
    pub(crate) name: String,
    pub(crate) offset: u64,
    pub(crate) total: u64,
    #[serde(with = "serde_bytes_compat")]
    pub(crate) data: Option<Vec<u8>>,
}

/// The behaviour added to the swarm.
pub(crate) type ModelBehaviour = request_response::cbor::Behaviour<PieceRequest, PieceResponse>;

/// Builds the request-response behaviour, with responses fit for a piece.
pub(crate) fn behaviour() -> ModelBehaviour {
    let codec = request_response::cbor::codec::Codec::default()
        .set_response_size_maximum(u64::from(PIECE_BYTES) + 4096);
    request_response::Behaviour::with_codec(
        codec,
        [(StreamProtocol::new(PROTOCOL), ProtocolSupport::Full)],
        request_response::Config::default().with_request_timeout(PIECE_TIMEOUT),
    )
}

/// Requests from the node's tasks to the event loop.
pub(crate) enum ModelCommand {
    /// Holders of the store file `name` (DHT providers, then the connected
    /// peers).
    Holders {
        name: String,
        reply: oneshot::Sender<Vec<PeerId>>,
    },
    /// Ask `peer` for one piece.
    Piece {
        peer: PeerId,
        request: PieceRequest,
        reply: oneshot::Sender<Option<PieceResponse>>,
    },
    /// Announce that this node holds the store file `name`.
    Provide { name: String },
}

static COMMANDS: OnceLock<mpsc::Sender<ModelCommand>> = OnceLock::new();

/// Lets the node's tasks reach the event loop (called once at start).
pub(crate) fn connect(commands: mpsc::Sender<ModelCommand>) {
    let _ = COMMANDS.set(commands);
}

async fn send(command: ModelCommand) -> bool {
    match COMMANDS.get() {
        Some(commands) => commands.send(command).await.is_ok(),
        None => false,
    }
}

/// Announces that this node holds the store file `name`.
pub(crate) async fn announce(name: String) {
    send(ModelCommand::Provide { name }).await;
}

/// The store at `root`, only to list, check and move files (never asks
/// the Hub, and may be dropped anywhere).
fn local_store(root: &Path) -> ModelStore {
    ModelStore::new(root.to_path_buf(), "", Box::new(NoHub))
}

/// Announces every pinned file of the store at `root` (at start).
pub(crate) async fn provide_store(root: &Path) {
    for (name, _) in local_store(root).pinned_files() {
        send(ModelCommand::Provide { name }).await;
    }
}

/// Gets `file` from peers into the store at `root`: true once it is there,
/// checked.
pub(crate) async fn download(root: &Path, file: &PinnedFile<'_>) -> bool {
    let store = local_store(root);
    let name = file.store_name();
    let (reply, answer) = oneshot::channel();
    if !send(ModelCommand::Holders {
        name: name.clone(),
        reply,
    })
    .await
    {
        return false;
    }
    let holders = match tokio::time::timeout(PROVIDERS_TIMEOUT, answer).await {
        Ok(Ok(holders)) => holders,
        _ => return false,
    };
    let Ok(partial) = store.peer_partial_path(file) else {
        return false;
    };
    for peer in holders.into_iter().take(MAX_PEERS) {
        match download_from(peer, &name, file.size, &partial).await {
            Ok(()) => {
                let installed = {
                    let partial = partial.clone();
                    let (owned, root) = (OwnedPinned::from(file), store.root().to_path_buf());
                    tokio::task::spawn_blocking(move || owned.install(&root, &partial)).await
                };
                match installed {
                    Ok(Ok(())) => {
                        println!(" Model file {} received from {peer}", file.path);
                        send(ModelCommand::Provide { name }).await;
                        return true;
                    }
                    Ok(Err(err)) => {
                        println!(" Model file {} from {peer} refused: {err}", file.path)
                    }
                    Err(err) => println!(" Model file {} not checked: {err}", file.path),
                }
            }
            Err(err) => {
                let _ = std::fs::remove_file(&partial);
                println!(" Model file {} not received from {peer}: {err}", file.path);
            }
        }
    }
    false
}

/// A pinned file owned (to cross into a blocking task).
struct OwnedPinned {
    path: String,
    size: u64,
    sha256: Option<String>,
    git: Option<String>,
}

impl From<&PinnedFile<'_>> for OwnedPinned {
    fn from(file: &PinnedFile<'_>) -> Self {
        use silicium_embedding::model::store::PinnedHash;
        let (sha256, git) = match file.hash {
            PinnedHash::Sha256(hash) => (Some(hash.to_string()), None),
            PinnedHash::GitBlob(hash) => (None, Some(hash.to_string())),
        };
        Self {
            path: file.path.to_string(),
            size: file.size,
            sha256,
            git,
        }
    }
}

impl OwnedPinned {
    fn install(&self, root: &Path, received: &Path) -> Result<(), String> {
        use silicium_embedding::model::store::PinnedHash;
        let hash = match (&self.sha256, &self.git) {
            (Some(hash), _) => PinnedHash::Sha256(hash),
            (_, Some(hash)) => PinnedHash::GitBlob(hash),
            _ => return Err("no hash".into()),
        };
        let file = PinnedFile {
            path: &self.path,
            size: self.size,
            hash,
        };
        local_store(root)
            .install_pinned(&file, received)
            .map(|_| ())
            .map_err(|err| err.to_string())
    }
}

/// A Hub client that is never used.
struct NoHub;

impl silicium_embedding::model::store::Fetcher for NoHub {
    fn fetch(&self, url: &str, _sink: &mut dyn Write) -> silicium_embedding::Result<()> {
        Err(silicium_embedding::Error::Model(format!(
            "{url}: not asked"
        )))
    }
}

/// Offsets and lengths of the pieces of a file of `size` bytes.
pub(crate) fn pieces(size: u64) -> Vec<(u64, u32)> {
    let step = u64::from(PIECE_BYTES);
    (0..size.div_ceil(step))
        .map(|index| {
            let offset = index * step;
            (offset, (size - offset).min(step) as u32)
        })
        .collect()
}

/// Downloads the whole file from `peer` into `partial` (in order, a few
/// pieces at a time).
async fn download_from(peer: PeerId, name: &str, size: u64, partial: &Path) -> Result<(), String> {
    let mut out = std::fs::File::create(partial).map_err(|err| err.to_string())?;
    let mut answers = stream::iter(pieces(size))
        .map(|(offset, length)| {
            let request = PieceRequest {
                name: name.to_string(),
                offset,
                length,
            };
            async move { (request.clone(), ask(peer, request).await) }
        })
        .buffered(PIECES_IN_FLIGHT);
    while let Some((request, answer)) = answers.next().await {
        let piece = answer.ok_or("no answer")?;
        let data = check_piece(&request, size, piece)?;
        out.write_all(&data).map_err(|err| err.to_string())?;
    }
    out.flush().map_err(|err| err.to_string())
}

/// The bytes of `piece` when it answers `request` for a file of `size` bytes.
pub(crate) fn check_piece(
    request: &PieceRequest,
    size: u64,
    piece: PieceResponse,
) -> Result<Vec<u8>, String> {
    if piece.name != request.name || piece.offset != request.offset {
        return Err("answer to another request".into());
    }
    if piece.total != size {
        return Err(format!("file of {} bytes, pinned {size}", piece.total));
    }
    let data = piece.data.ok_or("file not there")?;
    if data.len() != request.length as usize {
        return Err("short piece".into());
    }
    Ok(data)
}

async fn ask(peer: PeerId, request: PieceRequest) -> Option<PieceResponse> {
    let (reply, answer) = oneshot::channel();
    if !send(ModelCommand::Piece {
        peer,
        request,
        reply,
    })
    .await
    {
        return None;
    }
    tokio::time::timeout(PIECE_TIMEOUT, answer)
        .await
        .ok()?
        .ok()?
}

/// Answer to a peer's request, from the store at `root` (none: this node
/// shares no model file).
pub(crate) fn serve(root: Option<&Path>, request: PieceRequest) -> PieceResponse {
    let read = || -> Option<(u64, Vec<u8>)> {
        let root = root?;
        if !is_pinned_name(&request.name) || request.length > PIECE_BYTES {
            return None;
        }
        let path: PathBuf = root.join(&request.name);
        let mut file = std::fs::File::open(path).ok()?;
        let total = file.metadata().ok()?.len();
        let end = request.offset.checked_add(u64::from(request.length))?;
        if end > total {
            return None;
        }
        file.seek(SeekFrom::Start(request.offset)).ok()?;
        let mut data = vec![0; request.length as usize];
        file.read_exact(&mut data).ok()?;
        Some((total, data))
    };
    let (total, data) = match read() {
        Some((total, data)) => (total, Some(data)),
        None => (0, None),
    };
    PieceResponse {
        name: request.name,
        offset: request.offset,
        total,
        data,
    }
}

/// Model sharing state of the event loop: lookups and requests in progress.
#[derive(Default)]
pub(crate) struct ModelShare {
    lookups: HashMap<kad::QueryId, (Vec<PeerId>, oneshot::Sender<Vec<PeerId>>)>,
    requests: HashMap<OutboundRequestId, oneshot::Sender<Option<PieceResponse>>>,
}

impl ModelShare {
    /// Handles a command from the node's tasks.
    pub(crate) fn handle_command(
        &mut self,
        swarm: &mut Swarm<P2pBehaviour>,
        command: ModelCommand,
    ) {
        match command {
            ModelCommand::Holders { name, reply } => {
                let query = swarm.behaviour_mut().kademlia.get_providers(dht_key(&name));
                self.lookups.insert(query, (Vec::new(), reply));
            }
            ModelCommand::Piece {
                peer,
                request,
                reply,
            } => {
                let id = swarm.behaviour_mut().models.send_request(&peer, request);
                self.requests.insert(id, reply);
            }
            ModelCommand::Provide { name } => {
                if let Err(err) = swarm
                    .behaviour_mut()
                    .kademlia
                    .start_providing(dht_key(&name))
                {
                    println!(" Could not announce model file {name}: {err:?}");
                }
            }
        }
    }

    /// Takes the provider lookups of model files; gives back other events.
    pub(crate) fn on_kademlia(
        &mut self,
        swarm: &Swarm<P2pBehaviour>,
        event: kad::Event,
    ) -> Option<kad::Event> {
        let kad::Event::OutboundQueryProgressed {
            id,
            result: kad::QueryResult::GetProviders(result),
            step,
            ..
        } = &event
        else {
            return Some(event);
        };
        let Some((found, _)) = self.lookups.get_mut(id) else {
            return Some(event);
        };
        if let Ok(kad::GetProvidersOk::FoundProviders { providers, .. }) = result {
            for peer in providers {
                if !found.contains(peer) && peer != swarm.local_peer_id() {
                    found.push(*peer);
                }
            }
        }
        let finished = step.last
            || matches!(
                result,
                Ok(kad::GetProvidersOk::FinishedWithNoAdditionalRecord { .. }) | Err(_)
            );
        if finished && let Some((mut found, reply)) = self.lookups.remove(id) {
            // Then the connected peers: a holder may not be in the DHT yet.
            for peer in swarm.connected_peers() {
                if !found.contains(peer) {
                    found.push(*peer);
                }
            }
            let _ = reply.send(found);
        }
        None
    }

    /// Serves requests and hands answers to the waiting downloads.
    pub(crate) fn on_event(
        &mut self,
        swarm: &mut Swarm<P2pBehaviour>,
        store_root: Option<&Path>,
        event: request_response::Event<PieceRequest, PieceResponse>,
    ) {
        match event {
            request_response::Event::Message {
                message:
                    request_response::Message::Request {
                        request, channel, ..
                    },
                ..
            } => {
                let _ = swarm
                    .behaviour_mut()
                    .models
                    .send_response(channel, serve(store_root, request));
            }
            request_response::Event::Message {
                message:
                    request_response::Message::Response {
                        request_id,
                        response,
                    },
                ..
            } => {
                if let Some(reply) = self.requests.remove(&request_id) {
                    let _ = reply.send(Some(response));
                }
            }
            request_response::Event::OutboundFailure { request_id, .. } => {
                if let Some(reply) = self.requests.remove(&request_id) {
                    let _ = reply.send(None);
                }
            }
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests;
