//! Search over one or more indexes: by meaning, by keywords, or both.
//!
//! - **By meaning** ([`Mode::Dense`]): the cosine of the query vector with
//!   every passage vector.
//! - **By keywords** ([`Mode::Lexical`]): BM25 over the folded terms of the
//!   passages ([`crate::lexical`]), with statistics computed over all the
//!   indexes searched, so that their scores are comparable.
//! - **Hybrid** ([`Mode::Hybrid`]): both rankings fused by
//!   weighted reciprocal rank fusion (RRF): a passage scores
//!   `weight / (RRF_K + rank)` in each ranking where it appears, and the
//!   sums are sorted. RRF needs no score calibration between the two
//!   methods, which have nothing in common, and favors passages that both
//!   find. Keywords weigh [`LEXICAL_WEIGHT`] against 1 for the meaning: on
//!   the evaluation set, keywords alone are clearly worse than the model,
//!   and at equal weight they push good answers down.
//! - **Automatic** ([`Mode::Auto`], the default): hybrid when the query
//!   holds an exact token ([`has_exact_terms`]: a number, a code such as
//!   `E3`, an acronym such as `GPS`), by meaning otherwise. On the
//!   evaluation set with the real model (232 questions), MRR 0.808 against
//!   0.791 by meaning alone and 0.785 to 0.805 for hybrid search on every
//!   question: keywords earn their place on the tokens a small model reads
//!   poorly, and blur ordinary questions.
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
/// Weight of the keyword ranking in hybrid search (the meaning weighs 1),
/// chosen with `silicium-embed eval`.
pub const LEXICAL_WEIGHT: f32 = 0.5;
/// Candidates taken from each ranking before fusion, at least.
const MIN_CANDIDATES: usize = 50;
/// Results kept below the best one, in cosine (see [`Tuning::margin`]).
pub const RELEVANCE_MARGIN: f32 = 0.04;
/// First results of the keyword ranking kept whatever their cosine.
const KEYWORD_RESULTS_KEPT: usize = 3;
/// Words compared to tell that two neighbouring passages overlap.
const OVERLAP_PROBE_WORDS: usize = 8;

/// How passages are ranked.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Mode {
    /// By meaning only.
    Dense,
    /// By keywords only.
    Lexical,
    /// Both, fused.
    Hybrid,
    /// Hybrid when the query holds an exact token, by meaning otherwise
    /// (default).
    #[default]
    Auto,
}

impl std::str::FromStr for Mode {
    type Err = Error;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "dense" => Ok(Mode::Dense),
            "lexical" => Ok(Mode::Lexical),
            "hybrid" => Ok(Mode::Hybrid),
            "auto" => Ok(Mode::Auto),
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

/// How a search is tuned; the defaults are the values chosen with
/// `silicium-embed eval`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Tuning {
    /// Weight of the keyword ranking in hybrid search (the meaning weighs 1).
    pub lexical_weight: f32,
    /// Results whose cosine with the query is more than this below the best
    /// result are dropped (except the first keyword matches): a question
    /// that one passage answers does not bring a list of unrelated ones.
    /// `None` keeps `k` results.
    pub margin: Option<f32>,
}

impl Default for Tuning {
    fn default() -> Self {
        Self {
            lexical_weight: LEXICAL_WEIGHT,
            margin: Some(RELEVANCE_MARGIN),
        }
    }
}

/// The best passages of `indexes` for a query, `k` at most. `vector` is
/// the query embedded by the model of the indexes; it may be `None` in
/// [`Mode::Lexical`] only.
pub fn search(
    indexes: &[&Index],
    vector: Option<&[f32]>,
    query: &str,
    k: usize,
    mode: Mode,
) -> Result<Vec<Found>> {
    search_tuned(indexes, vector, query, k, mode, &Tuning::default())
}

/// [`search`] with another [`Tuning`] (to measure it).
pub fn search_tuned(
    indexes: &[&Index],
    vector: Option<&[f32]>,
    query: &str,
    k: usize,
    mode: Mode,
    tuning: &Tuning,
) -> Result<Vec<Found>> {
    if k == 0 || indexes.is_empty() {
        return Ok(Vec::new());
    }
    let mode = match mode {
        Mode::Auto if has_exact_terms(query) => Mode::Hybrid,
        Mode::Auto => Mode::Dense,
        other => other,
    };
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
    let keyword_matches: Vec<(usize, u64)> = lexical
        .iter()
        .take(KEYWORD_RESULTS_KEPT)
        .map(|found| (found.index, found.id))
        .collect();
    let ranked = match mode {
        Mode::Dense => dense,
        Mode::Lexical => lexical,
        Mode::Hybrid | Mode::Auto => fuse(&[(&dense, 1.0), (&lexical, tuning.lexical_weight)]),
    };
    let mut found = collapse_neighbours(indexes, ranked, k)?;
    if let (Some(vector), Some(margin)) = (vector, tuning.margin) {
        keep_relevant(indexes, vector, &mut found, &keyword_matches, margin);
    }
    Ok(found)
}

/// Drops the results whose cosine with `vector` is more than `margin`
/// below the best one, except `keyword_matches`.
fn keep_relevant(
    indexes: &[&Index],
    vector: &[f32],
    found: &mut Vec<Found>,
    keyword_matches: &[(usize, u64)],
    margin: f32,
) {
    let cosine = |found: &Found| {
        indexes[found.index]
            .similarity(found.id, vector)
            .unwrap_or(f32::MIN)
    };
    let best = found.iter().map(cosine).fold(f32::MIN, f32::max);
    found.retain(|result| {
        cosine(result) >= best - margin || keyword_matches.contains(&(result.index, result.id))
    });
}

/// True when `query` holds a word with a digit (`780`, `E3`, `2.1`) or an
/// acronym of two letters or more in capitals (`GPS`, `TCP`).
pub fn has_exact_terms(query: &str) -> bool {
    query.split(|c: char| !c.is_alphanumeric()).any(|word| {
        word.chars().any(|c| c.is_ascii_digit())
            || (word.chars().count() >= 2 && word.chars().all(char::is_uppercase))
    })
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

/// Weighted reciprocal rank fusion of several `(ranking, weight)` (each
/// ranking best first).
pub fn fuse(rankings: &[(&[Found], f32)]) -> Vec<Found> {
    let mut scores: HashMap<(usize, u64), f32> = HashMap::new();
    for (ranking, weight) in rankings {
        for (rank, found) in ranking.iter().enumerate() {
            *scores.entry((found.index, found.id)).or_default() +=
                weight / (RRF_K + rank as f32 + 1.0);
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
mod tests;
