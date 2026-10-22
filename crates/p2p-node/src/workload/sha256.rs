//! The `calcul/integrity/sha256` workload (alias `calcul/hash/sha256`): the
//! SHA-256 of an input file, computed in parallel by chunks.
//!
//! - The publisher splits the input into byte chunks
//!   (`SILICIUM_TARGET_BYTES_PER_FRAGMENT`, or the requested fragment count).
//! - A worker hashes its chunk and publishes a small JSON [`ChunkHash`].
//! - A verifier recomputes the chunk (cheap and deterministic) and compares
//!   the SHA-256 of the JSON it gets with the one the worker published.
//! - The publisher assembles a [`JobHash`]: every chunk hash, the SHA-256 of
//!   the list of chunk hashes, and, for a single chunk, the hash of the whole
//!   input (`input_hash`, as the Python handler returns it).

use super::{ComputeOutcome, OutputFile, PublishedOutput, Workload};
use crate::{
    jobs::{FragmentRef, JobManifest, JobSettings, MAX_FRAGMENTS_LIMIT, fragment_task_id},
    processing::NodeContext,
    task::NetworkTask,
};
use futures::future::BoxFuture;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256 as Hasher};
use silicium_node_core::{
    p2p::{ByteRange, TaskEnvelope},
    taskbook::{MilestoneSample, ResultState},
};
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
};

/// Identifier of the workload.
pub(crate) const ID: &str = "calcul/integrity/sha256";
/// Former identifier, still accepted.
pub(crate) const ALIAS: &str = "calcul/hash/sha256";
const DELEGATION_LEAF_BYTES: u64 = 4 * 1024 * 1024;

/// The sha256 workload (see the module documentation).
pub(crate) struct Sha256;

const OUTPUTS: &[PublishedOutput] = &[PublishedOutput {
    extension: "json",
    target: "result/sha256.json",
    summary_keys: &["result_path"],
}];

/// Result of one chunk, published by the worker.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct ChunkHash {
    pub(crate) algorithm: String,
    pub(crate) index: u32,
    pub(crate) offset: u64,
    pub(crate) length: u64,
    pub(crate) sha256: String,
    /// Ordered child range commitments for a recursively delegated fragment.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(crate) children: Vec<ChunkHash>,
}

/// Result of a job, assembled by the publisher.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct JobHash {
    pub(crate) workload: String,
    pub(crate) algorithm: String,
    pub(crate) size_bytes: u64,
    pub(crate) chunk_count: usize,
    /// SHA-256 of the chunk hashes, one lowercase hex hash per line.
    pub(crate) chunk_list_sha256: String,
    /// SHA-256 of the whole input, known when it is a single chunk.
    pub(crate) input_hash: Option<String>,
    pub(crate) chunks: Vec<ChunkHash>,
}

impl Workload for Sha256 {
    fn id(&self) -> &'static str {
        ID
    }

    fn storage_dir(&self) -> &'static str {
        "sha256"
    }

    fn fragment_extension(&self) -> &'static str {
        "json"
    }

    fn published_outputs(&self) -> &'static [PublishedOutput] {
        OUTPUTS
    }

    fn split(
        &self,
        task: &NetworkTask,
        input: &Path,
        settings: &JobSettings,
    ) -> Option<(JobManifest, Vec<NetworkTask>)> {
        if task.byte_range.is_some() {
            return None;
        }
        let size = std::fs::metadata(input).ok()?.len();
        if size > ByteRange::MAX_END {
            return None;
        }
        let ranges = chunk_ranges(size, task.requested_fragment_count, settings);
        let mut fragments = Vec::with_capacity(ranges.len());
        let mut tasks = Vec::with_capacity(ranges.len());
        for (index, range) in ranges.into_iter().enumerate() {
            let task_id = fragment_task_id(&task.task_id, index);
            let mut fragment = task.clone();
            fragment.output_path = TaskEnvelope::local_output_path_for(&task_id, Some(ID))?;
            fragment.task_id = task_id.clone();
            fragment.workload = Some(ID.to_string());
            fragment.byte_range = Some(range);
            fragments.push(FragmentRef::chunk(task_id, range));
            tasks.push(fragment);
        }
        let manifest = JobManifest {
            job_id: task.task_id.clone(),
            root_job_id: task
                .root_job_id
                .clone()
                .unwrap_or_else(|| task.task_id.clone()),
            workload: ID.to_string(),
            width: 0,
            height: 0,
            input_bytes: size,
            scene_sha256: task.scene_sha256.clone(),
            fragments,
        };
        Some((manifest, tasks))
    }

    fn split_subtask(
        &self,
        task: &NetworkTask,
        input: &Path,
        _settings: &JobSettings,
    ) -> Option<(JobManifest, Vec<NetworkTask>)> {
        let parent = task.byte_range?;
        let size = std::fs::metadata(input).ok()?.len();
        if !parent.is_valid()
            || parent.is_empty()
            || parent.end > size
            || parent.len() <= DELEGATION_LEAF_BYTES
        {
            return None;
        }
        let midpoint = parent.start + parent.len() / 2;
        if midpoint <= parent.start || midpoint >= parent.end {
            return None;
        }
        let ranges = [
            ByteRange {
                start: parent.start,
                end: midpoint,
            },
            ByteRange {
                start: midpoint,
                end: parent.end,
            },
        ];
        let mut fragments = Vec::with_capacity(2);
        let mut tasks = Vec::with_capacity(2);
        for (index, range) in ranges.into_iter().enumerate() {
            let task_id = fragment_task_id(&task.task_id, index);
            let mut fragment = task.clone();
            fragment.task_id = task_id.clone();
            fragment.output_path = TaskEnvelope::local_output_path_for(&task_id, Some(ID))?;
            fragment.byte_range = Some(range);
            fragment.requested_fragment_count = None;
            fragments.push(FragmentRef::chunk(task_id, range));
            tasks.push(fragment);
        }
        Some((
            JobManifest {
                job_id: task.task_id.clone(),
                root_job_id: task.task_id.clone(),
                workload: ID.to_string(),
                width: 0,
                height: 0,
                input_bytes: parent.len(),
                scene_sha256: task.scene_sha256.clone(),
                fragments,
            },
            tasks,
        ))
    }

    fn combine_subtask_results(
        &self,
        task: &NetworkTask,
        child_results: &[Vec<u8>],
    ) -> Option<Vec<u8>> {
        let range = task.byte_range?;
        if child_results.len() != 2 || range.len() <= DELEGATION_LEAF_BYTES {
            return None;
        }
        let midpoint = range.start + range.len() / 2;
        let children: Vec<ChunkHash> = child_results
            .iter()
            .map(|bytes| serde_json::from_slice(bytes).ok())
            .collect::<Option<_>>()?;
        let expected = [
            ByteRange {
                start: range.start,
                end: midpoint,
            },
            ByteRange {
                start: midpoint,
                end: range.end,
            },
        ];
        if children
            .iter()
            .zip(expected)
            .any(|(child, range)| !valid_chunk_tree(child, range))
        {
            return None;
        }
        let parent = ChunkHash {
            algorithm: "sha256".to_string(),
            index: fragment_index(&task.task_id),
            offset: range.start,
            length: range.len(),
            sha256: tree_digest(&children),
            children,
        };
        serde_json::to_vec(&parent).ok()
    }

    fn execute<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
    ) -> BoxFuture<'a, Option<ComputeOutcome>> {
        Box::pin(async move {
            let bytes = chunk_result(context, task).await?;
            let output = context.content.absolute(&task.output_path);
            if let Err(err) = write_output(&output, &bytes) {
                println!(" Could not write the result of {}: {err}", task.task_id);
                return None;
            }
            Some(ComputeOutcome {
                milestones: Vec::new(),
            })
        })
    }

    fn verify<'a>(
        &'a self,
        context: &'a NodeContext,
        task: &'a NetworkTask,
        result: &'a ResultState,
        _seed: &'a str,
    ) -> BoxFuture<'a, Option<bool>> {
        Box::pin(async move {
            let expected = chunk_result(context, task).await?;
            Some(sha256_hex(&expected) == result.result.sha256)
        })
    }

    fn accepts_result(
        &self,
        fragment: Option<&FragmentRef>,
        bytes: &[u8],
        _milestones: &[MilestoneSample],
    ) -> bool {
        let Ok(chunk) = serde_json::from_slice::<ChunkHash>(bytes) else {
            return false;
        };
        let range = fragment.and_then(|fragment| fragment.byte_range);
        chunk.algorithm == "sha256" && range.is_none_or(|range| valid_chunk_tree(&chunk, range))
    }

    fn assemble(
        &self,
        job: &JobManifest,
        _input: &Path,
        fragments: &[Vec<u8>],
    ) -> Result<Vec<OutputFile>, String> {
        let roots = fragments
            .iter()
            .map(|bytes| serde_json::from_slice::<ChunkHash>(bytes).map_err(|err| err.to_string()))
            .collect::<Result<Vec<_>, _>>()?;
        let mut chunks = Vec::new();
        for root in &roots {
            flatten_chunks(root, &mut chunks);
        }
        for (index, chunk) in chunks.iter_mut().enumerate() {
            chunk.index = index as u32;
        }
        let covered: u64 = chunks.iter().map(|chunk| chunk.length).sum();
        if covered != job.input_bytes {
            return Err(format!(
                "chunks cover {covered} bytes, expected {}",
                job.input_bytes
            ));
        }
        let list: String = chunks
            .iter()
            .map(|chunk| format!("{}\n", chunk.sha256))
            .collect();
        let result = JobHash {
            workload: ID.to_string(),
            algorithm: "sha256".to_string(),
            size_bytes: job.input_bytes,
            chunk_count: chunks.len(),
            chunk_list_sha256: sha256_hex(list.as_bytes()),
            input_hash: (chunks.len() == 1).then(|| chunks[0].sha256.clone()),
            chunks,
        };
        let bytes = serde_json::to_vec_pretty(&result).map_err(|err| err.to_string())?;
        Ok(vec![OutputFile {
            extension: "json",
            bytes,
        }])
    }
}

/// Byte ranges covering `size` bytes: the requested count (at most 256),
/// else chunks of about `settings.target_bytes`, at most
/// `settings.max_fragments`; never more chunks than bytes. An empty input is
/// a single empty chunk.
pub(crate) fn chunk_ranges(
    size: u64,
    requested: Option<usize>,
    settings: &JobSettings,
) -> Vec<ByteRange> {
    let max = settings.max_fragments.clamp(1, MAX_FRAGMENTS_LIMIT) as u64;
    let target = settings.target_bytes.max(1) as u64;
    // A count requested by the BackEnd is honoured (like raytracer tiles) up
    // to the hard limit; otherwise the node's own maximum applies.
    let count = match requested {
        Some(count) => (count as u64).clamp(1, MAX_FRAGMENTS_LIMIT as u64),
        None => size.div_ceil(target).clamp(1, max),
    }
    .min(size.max(1));
    let chunk = size.div_ceil(count).max(1);
    let mut ranges = Vec::with_capacity(count as usize);
    let mut start = 0;
    while start < size {
        let end = (start + chunk).min(size);
        ranges.push(ByteRange { start, end });
        start = end;
    }
    if ranges.is_empty() {
        ranges.push(ByteRange { start: 0, end: 0 });
    }
    ranges
}

/// The JSON result of `task`'s chunk, computed from the local input.
async fn chunk_result(context: &NodeContext, task: &NetworkTask) -> Option<Vec<u8>> {
    let input = context.content.absolute(&task.scene_path);
    let range = task.byte_range;
    let index = fragment_index(&task.task_id);
    let computed = tokio::task::spawn_blocking(move || {
        hash_chunk_tree(&input, range, index, DELEGATION_LEAF_BYTES)
    })
    .await;
    match computed {
        Ok(Ok(chunk)) => serde_json::to_vec(&chunk).ok(),
        Ok(Err(err)) => {
            println!(" Could not hash the input of {}: {err}", task.task_id);
            None
        }
        Err(err) => {
            println!(" Hashing task of {} failed: {err}", task.task_id);
            None
        }
    }
}

/// Hashes `range` of the file `input` (the whole file when `None`).
pub(crate) fn hash_chunk(
    input: &Path,
    range: Option<ByteRange>,
    index: u32,
) -> std::io::Result<ChunkHash> {
    let mut file = File::open(input)?;
    let size = file.metadata()?.len();
    let range = range.unwrap_or(ByteRange {
        start: 0,
        end: size,
    });
    if range.end > size || !range.is_valid() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            format!(
                "chunk {}..{} outside a {size}-byte input",
                range.start, range.end
            ),
        ));
    }
    file.seek(SeekFrom::Start(range.start))?;
    let mut hasher = Hasher::new();
    let mut remaining = file.take(range.len());
    let mut buffer = vec![0u8; 64 * 1024];
    loop {
        let read = remaining.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(ChunkHash {
        algorithm: "sha256".to_string(),
        index,
        offset: range.start,
        length: range.len(),
        sha256: hex(&hasher.finalize()),
        children: Vec::new(),
    })
}

fn hash_chunk_tree(
    input: &Path,
    range: Option<ByteRange>,
    index: u32,
    leaf_bytes: u64,
) -> std::io::Result<ChunkHash> {
    let size = File::open(input)?.metadata()?.len();
    let range = range.unwrap_or(ByteRange {
        start: 0,
        end: size,
    });
    if range.len() <= leaf_bytes {
        return hash_chunk(input, Some(range), index);
    }
    let midpoint = range.start + range.len() / 2;
    let children = vec![
        hash_chunk_tree(
            input,
            Some(ByteRange {
                start: range.start,
                end: midpoint,
            }),
            0,
            leaf_bytes,
        )?,
        hash_chunk_tree(
            input,
            Some(ByteRange {
                start: midpoint,
                end: range.end,
            }),
            0,
            leaf_bytes,
        )?,
    ];
    Ok(ChunkHash {
        algorithm: "sha256".to_string(),
        index,
        offset: range.start,
        length: range.len(),
        sha256: tree_digest(&children),
        children,
    })
}

fn valid_chunk_tree(chunk: &ChunkHash, range: ByteRange) -> bool {
    if chunk.algorithm != "sha256"
        || !is_hex_hash(&chunk.sha256)
        || (chunk.offset, chunk.length) != (range.start, range.len())
    {
        return false;
    }
    if range.len() <= DELEGATION_LEAF_BYTES {
        return chunk.children.is_empty();
    }
    if chunk.children.len() != 2 {
        return false;
    }
    let midpoint = range.start + range.len() / 2;
    let expected = [
        ByteRange {
            start: range.start,
            end: midpoint,
        },
        ByteRange {
            start: midpoint,
            end: range.end,
        },
    ];
    chunk
        .children
        .iter()
        .zip(expected)
        .all(|(child, expected)| valid_chunk_tree(child, expected))
        && chunk.sha256 == tree_digest(&chunk.children)
}

fn tree_digest(children: &[ChunkHash]) -> String {
    let bytes = serde_json::to_vec(children).unwrap_or_default();
    sha256_hex(&bytes)
}

fn flatten_chunks(chunk: &ChunkHash, out: &mut Vec<ChunkHash>) {
    if chunk.children.is_empty() {
        out.push(chunk.clone());
    } else {
        for child in &chunk.children {
            flatten_chunks(child, out);
        }
    }
}

fn write_output(path: &PathBuf, bytes: &[u8]) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, bytes)
}

fn fragment_index(task_id: &str) -> u32 {
    task_id
        .rsplit_once(".f")
        .and_then(|(_, value)| value.parse().ok())
        .unwrap_or(0)
}

fn sha256_hex(bytes: &[u8]) -> String {
    hex(&Hasher::digest(bytes))
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn is_hex_hash(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

#[cfg(test)]
mod tests;
