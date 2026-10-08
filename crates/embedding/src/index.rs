//! The result of a document-search job, and the search over it.
//!
//! The publisher assembles three files (format `silicium-index/1`):
//! - `index.json`: the [`IndexManifest`] (model, dimension, documents,
//!   skipped files);
//! - `vectors.f32`: the vectors of every passage, in passage order, as raw
//!   little-endian f32 (`numpy.fromfile(path, "<f4").reshape(-1, d)`);
//! - `passages.jsonl`: one [`IndexPassage`] per line, in the same order.
//!
//! Search is exact: the dot product of the query vector with every passage
//! vector, keeping the best `k`. It costs `passages × dimension`
//! multiply-adds, a fraction of a second for a million passages of dimension 384 on
//! one core, which covers the collections of a person. Past that, an
//! approximate index (HNSW) would be built from the same files without
//! changing them.

use crate::{
    Error, Result,
    corpus::{self, DocumentEntry},
    documents::SkippedDocument,
    lexical::LexicalIndex,
    model::ModelSpec,
    vectors::{VectorBlock, dot},
};
use serde::{Deserialize, Serialize};
use std::{cmp::Ordering, collections::BinaryHeap, path::Path};

/// Identifier of this format.
pub const FORMAT: &str = "silicium-index/1";
pub const MANIFEST_FILE: &str = "index.json";
pub const VECTORS_FILE: &str = "vectors.f32";
pub const PASSAGES_FILE: &str = "passages.jsonl";

/// `index.json`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IndexManifest {
    pub format: String,
    pub model: String,
    pub model_revision: String,
    pub dimension: usize,
    pub passage_count: u64,
    pub documents: Vec<DocumentEntry>,
    #[serde(default)]
    pub skipped: Vec<SkippedDocument>,
    pub vectors: String,
    pub passages: String,
}

/// A line of `passages.jsonl`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IndexPassage {
    pub id: u64,
    pub document: String,
    pub page: Option<u32>,
    /// Headings above the passage (`Article 6 › Préavis`), empty when the
    /// document has none (and in indexes built before sections existed).
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub section: String,
    pub text: String,
}

/// The three files of an index, as bytes.
#[derive(Debug, Clone, PartialEq)]
pub struct IndexFiles {
    pub manifest: Vec<u8>,
    pub vectors: Vec<u8>,
    pub passages: Vec<u8>,
}

/// A search result: passage `id` and its similarity to the query.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Hit {
    pub id: u64,
    pub score: f32,
}

/// Builds the index of `corpus` from the vector blocks of its fragments,
/// in fragment order. Every passage must have exactly one vector.
pub fn assemble(
    corpus_bytes: &[u8],
    blocks: &[VectorBlock],
    model: &ModelSpec,
) -> Result<IndexFiles> {
    let (header, body) = corpus::read_header(corpus_bytes)?;
    let mut next_id = 0u64;
    let mut vectors = Vec::with_capacity(header.passage_count as usize * model.dimension * 4);
    for block in blocks {
        block.check_shape(model.dimension, next_id, block.count() as u64)?;
        block.check_unit()?;
        for value in &block.values {
            vectors.extend_from_slice(&value.to_le_bytes());
        }
        next_id += block.count() as u64;
    }
    if next_id != header.passage_count {
        return Err(Error::Format(format!(
            "{next_id} vectors for {} passages",
            header.passage_count
        )));
    }
    let records = corpus::read_range(corpus_bytes, body as u64, corpus_bytes.len() as u64)?;
    let mut passages = Vec::new();
    for record in records {
        let document = header
            .documents
            .get(record.doc as usize)
            .map(|document| document.name.clone())
            .ok_or_else(|| Error::Format("passage of an unknown document".into()))?;
        let line = IndexPassage {
            id: record.id,
            document,
            page: record.page,
            section: record.section,
            text: record.text,
        };
        passages.extend(serde_json::to_vec(&line).map_err(|err| Error::Format(err.to_string()))?);
        passages.push(b'\n');
    }
    let manifest = IndexManifest {
        format: FORMAT.to_string(),
        model: model.id.to_string(),
        model_revision: model.revision.to_string(),
        dimension: model.dimension,
        passage_count: header.passage_count,
        documents: header.documents,
        skipped: header.skipped,
        vectors: VECTORS_FILE.to_string(),
        passages: PASSAGES_FILE.to_string(),
    };
    let manifest =
        serde_json::to_vec_pretty(&manifest).map_err(|err| Error::Format(err.to_string()))?;
    Ok(IndexFiles {
        manifest,
        vectors,
        passages,
    })
}

/// An index loaded in memory, ready to search.
#[derive(Debug, Clone)]
pub struct Index {
    pub manifest: IndexManifest,
    vectors: Vec<f32>,
    passages: Vec<u8>,
    /// Start of each line of `passages`.
    offsets: Vec<usize>,
    /// Keyword index of the passages (built on load, not stored).
    lexical: LexicalIndex,
}

impl Index {
    /// Loads the index files of `dir`.
    pub fn open(dir: &Path) -> Result<Self> {
        let manifest = std::fs::read(dir.join(MANIFEST_FILE))?;
        let vectors = std::fs::read(dir.join(VECTORS_FILE))?;
        let passages = std::fs::read(dir.join(PASSAGES_FILE))?;
        Self::from_files(IndexFiles {
            manifest,
            vectors,
            passages,
        })
    }

    /// Loads an index from its files, checking that they agree.
    pub fn from_files(files: IndexFiles) -> Result<Self> {
        let manifest: IndexManifest = serde_json::from_slice(&files.manifest)
            .map_err(|err| Error::Format(format!("index manifest: {err}")))?;
        if manifest.format != FORMAT || manifest.dimension == 0 {
            return Err(Error::Format("unknown index format".into()));
        }
        let count = manifest.passage_count as usize;
        if files.vectors.len() != count * manifest.dimension * 4 {
            return Err(Error::Format(
                "vector file does not match the manifest".into(),
            ));
        }
        let vectors = files
            .vectors
            .as_chunks::<4>()
            .0
            .iter()
            .map(|value| f32::from_le_bytes(*value))
            .collect();
        let offsets = line_offsets(&files.passages);
        if offsets.len() != count {
            return Err(Error::Format(
                "passage file does not match the manifest".into(),
            ));
        }
        let mut index = Self {
            manifest,
            vectors,
            passages: files.passages,
            offsets,
            lexical: LexicalIndex::default(),
        };
        let mut searchable = Vec::with_capacity(count);
        for id in 0..count as u64 {
            let passage = index.passage(id)?;
            searchable.push(format!(
                "{} {} {}",
                passage.document, passage.section, passage.text
            ));
        }
        index.lexical = LexicalIndex::build(searchable.iter().map(String::as_str));
        Ok(index)
    }

    /// The keyword index of the passages (document name, section and text).
    pub fn lexical(&self) -> &LexicalIndex {
        &self.lexical
    }

    /// The `k` passages most similar to `query` (a unit vector), best first.
    pub fn search(&self, query: &[f32], k: usize) -> Result<Vec<Hit>> {
        let dimension = self.manifest.dimension;
        if query.len() != dimension {
            return Err(Error::Format("query vector of the wrong dimension".into()));
        }
        let scored = self
            .vectors
            .chunks_exact(dimension)
            .enumerate()
            .map(|(id, vector)| (id as u64, dot(query, vector)));
        Ok(top_k(scored, k)
            .into_iter()
            .map(|(id, score)| Hit { id, score })
            .collect())
    }

    /// Passage `id`.
    pub fn passage(&self, id: u64) -> Result<IndexPassage> {
        let index = usize::try_from(id).map_err(|_| Error::Format("passage id".into()))?;
        let start = *self
            .offsets
            .get(index)
            .ok_or_else(|| Error::Format(format!("no passage {id}")))?;
        let end = self
            .offsets
            .get(index + 1)
            .copied()
            .unwrap_or(self.passages.len());
        serde_json::from_slice(self.passages[start..end].trim_ascii_end())
            .map_err(|err| Error::Format(format!("passage {id}: {err}")))
    }

    /// Approximate memory held by this index, in bytes.
    pub fn memory_bytes(&self) -> usize {
        self.vectors.len() * 4
            + self.passages.len()
            + self.offsets.len() * 8
            + self.lexical.memory_bytes()
    }
}

/// The `k` items of highest score, best first; equal scores keep the
/// smaller key first, so results are stable.
pub fn top_k<K: Ord + Copy>(items: impl Iterator<Item = (K, f32)>, k: usize) -> Vec<(K, f32)> {
    if k == 0 {
        return Vec::new();
    }
    // Min-heap of the best k seen so far: its top is the worst kept.
    let mut heap: BinaryHeap<Ranked<K>> = BinaryHeap::with_capacity(k + 1);
    for (key, score) in items {
        if !score.is_finite() {
            continue;
        }
        heap.push(Ranked { key, score });
        if heap.len() > k {
            heap.pop();
        }
    }
    let mut best: Vec<(K, f32)> = heap.into_iter().map(|r| (r.key, r.score)).collect();
    best.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
    best
}

/// Heap entry ordered so that the *worst* entry is the greatest.
struct Ranked<K> {
    key: K,
    score: f32,
}

impl<K: Ord> Ord for Ranked<K> {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .score
            .total_cmp(&self.score)
            .then_with(|| self.key.cmp(&other.key))
    }
}

impl<K: Ord> PartialOrd for Ranked<K> {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl<K: Ord> PartialEq for Ranked<K> {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}

impl<K: Ord> Eq for Ranked<K> {}

fn line_offsets(bytes: &[u8]) -> Vec<usize> {
    let mut offsets = Vec::new();
    let mut start = 0;
    for (position, byte) in bytes.iter().enumerate() {
        if *byte == b'\n' {
            if position > start {
                offsets.push(start);
            }
            start = position + 1;
        }
    }
    if start < bytes.len() {
        offsets.push(start);
    }
    offsets
}

#[cfg(test)]
mod tests;
