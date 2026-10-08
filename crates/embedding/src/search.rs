//! Search over one or more indexes: by meaning, by keywords, or both.
//!
//! - **By meaning** ([`Mode::Dense`]): the cosine of the query vector with
//!   every passage vector.
//! - **By keywords** ([`Mode::Lexical`]): BM25 over the folded terms of the
//!   passages ([`crate::lexical`]), with statistics computed over all the
//!   indexes searched, so that their scores are comparable.
//! - **Hybrid** ([`Mode::Hybrid`], the default): both rankings fused by
//!   reciprocal rank fusion (RRF): a passage scores `1 / (RRF_K + rank)` in
//!   each ranking where it appears, and the sums are sorted. RRF needs no
//!   score calibration between the two methods, which have nothing in
//!   common, and favors passages that both find.
//!
//! Neighbouring passages cut from the same text with an overlap often come
//! out together; the lower-ranked one is dropped ([`collapse_neighbours`]),
//! so that the results show different places of the documents.

use crate::{
    Error, Result,
    index::{Index, top_k},
    lexical::{Bm25Stats, query_terms},
};
use std::collections::HashMap;

/// Rank offset of reciprocal rank fusion (the usual value).
pub const RRF_K: f32 = 60.0;
/// Candidates taken from each ranking before fusion, at least.
const MIN_CANDIDATES: usize = 50;
/// Words compared to tell that two neighbouring passages overlap.
const OVERLAP_PROBE_WORDS: usize = 8;

/// How passages are ranked.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Mode {
    /// By meaning only.
    Dense,
    /// By keywords only.
    Lexical,
    /// Both, fused (default).
    #[default]
    Hybrid,
}

impl std::str::FromStr for Mode {
    type Err = Error;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "dense" => Ok(Mode::Dense),
            "lexical" => Ok(Mode::Lexical),
            "hybrid" => Ok(Mode::Hybrid),
            other => Err(Error::Input(format!("unknown search mode {other}"))),
        }
    }
}

/// A result: passage `id` of the `index`-th index searched.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Found {
    pub index: usize,
    pub id: u64,
    /// Cosine for [`Mode::Dense`], BM25 for [`Mode::Lexical`], fused score
    /// for [`Mode::Hybrid`]: only the order is meaningful across modes.
    pub score: f32,
}

/// The `k` best passages of `indexes` for a query. `vector` is the query
/// embedded by the model of the indexes; it may be `None` in
/// [`Mode::Lexical`] only.
pub fn search(
    indexes: &[&Index],
    vector: Option<&[f32]>,
    query: &str,
    k: usize,
    mode: Mode,
) -> Result<Vec<Found>> {
    if k == 0 || indexes.is_empty() {
        return Ok(Vec::new());
    }
    let depth = (k * 4).max(MIN_CANDIDATES);
    let dense = match (mode, vector) {
        (Mode::Lexical, _) => Vec::new(),
        (_, Some(vector)) => dense_ranking(indexes, vector, depth)?,
        (_, None) => return Err(Error::Input("a query vector is needed".into())),
    };
    let lexical = match mode {
        Mode::Dense => Vec::new(),
        _ => lexical_ranking(indexes, query, depth),
    };
    let ranked = match mode {
        Mode::Dense => dense,
        Mode::Lexical => lexical,
        Mode::Hybrid => fuse(&[&dense, &lexical]),
    };
    collapse_neighbours(indexes, ranked, k)
}

/// The `depth` passages closest to `vector` over all indexes.
fn dense_ranking(indexes: &[&Index], vector: &[f32], depth: usize) -> Result<Vec<Found>> {
    let mut candidates = Vec::new();
    for (position, index) in indexes.iter().enumerate() {
        for hit in index.search(vector, depth)? {
            candidates.push(((position, hit.id), hit.score));
        }
    }
    Ok(as_found(top_k(candidates.into_iter(), depth)))
}

/// The `depth` passages of best BM25 score over all indexes.
fn lexical_ranking(indexes: &[&Index], query: &str, depth: usize) -> Vec<Found> {
    let terms = query_terms(query);
    if terms.is_empty() {
        return Vec::new();
    }
    let lexical: Vec<_> = indexes.iter().map(|index| index.lexical()).collect();
    let stats = Bm25Stats::over(&lexical, &terms);
    let candidates = lexical
        .iter()
        .enumerate()
        .flat_map(|(position, index)| {
            index
                .search(&terms, &stats, depth)
                .into_iter()
                .map(move |(id, score)| ((position, id), score))
        })
        .collect::<Vec<_>>();
    as_found(top_k(candidates.into_iter(), depth))
}

fn as_found(ranked: Vec<((usize, u64), f32)>) -> Vec<Found> {
    ranked
        .into_iter()
        .map(|((index, id), score)| Found { index, id, score })
        .collect()
}

/// Reciprocal rank fusion of several rankings (best first).
pub fn fuse(rankings: &[&[Found]]) -> Vec<Found> {
    let mut scores: HashMap<(usize, u64), f32> = HashMap::new();
    for ranking in rankings {
        for (rank, found) in ranking.iter().enumerate() {
            *scores.entry((found.index, found.id)).or_default() +=
                1.0 / (RRF_K + rank as f32 + 1.0);
        }
    }
    let count = scores.len();
    as_found(top_k(scores.into_iter(), count))
}

/// The first `k` of `ranked`, without a passage that overlaps a
/// better-ranked neighbour (same index, next or previous id, the start of
/// the later one contained in the earlier one).
fn collapse_neighbours(indexes: &[&Index], ranked: Vec<Found>, k: usize) -> Result<Vec<Found>> {
    let mut kept: Vec<(Found, String)> = Vec::with_capacity(k);
    for found in ranked {
        if kept.len() == k {
            break;
        }
        let text = indexes[found.index].passage(found.id)?.text;
        let overlaps = kept.iter().any(|(other, other_text)| {
            other.index == found.index
                && other.id.abs_diff(found.id) == 1
                && if other.id < found.id {
                    continues(other_text, &text)
                } else {
                    continues(&text, other_text)
                }
        });
        if !overlaps {
            kept.push((found, text));
        }
    }
    Ok(kept.into_iter().map(|(found, _)| found).collect())
}

/// True when `later` starts with words that appear in `earlier` (the
/// overlap of two windows cut from one text).
fn continues(earlier: &str, later: &str) -> bool {
    let probe: Vec<&str> = later.split_whitespace().take(OVERLAP_PROBE_WORDS).collect();
    probe.len() == OVERLAP_PROBE_WORDS && earlier.contains(&probe.join(" "))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        corpus,
        documents::{Document, Extraction, Page},
        index,
        passages::Chunker,
        testing,
        vectors::VectorBlock,
    };

    /// An index of `texts` (one document per text) with the tiny model.
    fn index_of(texts: &[&str]) -> Index {
        let extraction = Extraction {
            documents: texts
                .iter()
                .enumerate()
                .map(|(n, text)| Document {
                    name: format!("doc{n}.txt"),
                    pages: vec![Page {
                        number: None,
                        text: text.to_string(),
                    }],
                })
                .collect(),
            skipped: Vec::new(),
        };
        let bytes = corpus::build(&extraction, &Chunker::default()).unwrap();
        let (_, body) = corpus::read_header(&bytes).unwrap();
        let records = corpus::read_range(&bytes, body as u64, bytes.len() as u64).unwrap();
        let encoder = testing::tiny_encoder().unwrap();
        let inputs: Vec<_> = records.iter().map(|r| r.embedding_input()).collect();
        let texts: Vec<&str> = inputs.iter().map(AsRef::as_ref).collect();
        let vectors = encoder.embed_passages(&texts).unwrap();
        let block = VectorBlock::new(testing::TINY.dimension, 0, &vectors).unwrap();
        Index::from_files(index::assemble(&bytes, &[block], &testing::TINY).unwrap()).unwrap()
    }

    #[test]
    fn keywords_find_an_exact_number_the_tiny_model_cannot() {
        let a = index_of(&["le chat de la maison", "le loyer est de 780 euros"]);
        let b = index_of(&["la voiture du client", "le chien et le chat"]);
        let encoder = testing::tiny_encoder().unwrap();
        let vector = encoder.embed_query("780").unwrap();
        let lexical = search(&[&a, &b], None, "780", 5, Mode::Lexical).unwrap();
        assert_eq!((lexical[0].index, lexical[0].id), (0, 1));
        assert_eq!(lexical.len(), 1, "only passages with the term");
        let hybrid = search(&[&a, &b], Some(&vector), "780", 3, Mode::Hybrid).unwrap();
        assert_eq!(
            (hybrid[0].index, hybrid[0].id),
            (0, 1),
            "keyword match first"
        );
        assert_eq!(hybrid.len(), 3);
        assert!(search(&[&a], None, "780", 3, Mode::Hybrid).is_err());
        let dense = search(&[&a, &b], Some(&vector), "780", 4, Mode::Dense).unwrap();
        assert_eq!(dense.len(), 4);
    }

    #[test]
    fn overlapping_neighbours_are_shown_once() {
        let words: Vec<String> = (0..400).map(|n| format!("mot{n}")).collect();
        let index = index_of(&[&words.join(" ")]);
        let all = search(&[&index], None, "mot125 mot140", 10, Mode::Lexical).unwrap();
        let ids: Vec<u64> = all.iter().map(|f| f.id).collect();
        assert_eq!(
            ids.len(),
            1,
            "mot125 and mot140 are in two overlapping windows: {ids:?}"
        );
    }

    fn found(index: usize, id: u64) -> Found {
        Found {
            index,
            id,
            score: 0.0,
        }
    }

    #[test]
    fn fusion_favours_passages_found_by_both_rankings() {
        let dense = [found(0, 1), found(0, 2), found(0, 3)];
        let lexical = [found(0, 3), found(0, 4)];
        let fused: Vec<u64> = fuse(&[&dense, &lexical]).iter().map(|f| f.id).collect();
        assert_eq!(fused[0], 3, "found by both");
        assert_eq!(fused[1], 1, "first of a ranking");
        assert_eq!(fused[2..], [2, 4], "equal scores keep the smaller id first");
    }

    #[test]
    fn overlap_is_detected_from_the_start_of_the_later_window() {
        let earlier = "a b c d e f g h i j k l";
        assert!(continues(earlier, "e f g h i j k l m n"));
        assert!(!continues(earlier, "x f g h i j k l m n"));
        assert!(!continues(earlier, "e f g"), "too short to tell");
    }
}
