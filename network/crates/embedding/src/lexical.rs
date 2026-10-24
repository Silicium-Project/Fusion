//! Keyword search (BM25) over the passages of an index.
//!
//! The embedding model finds passages by meaning, but small models are weak
//! on exact tokens: names, numbers ("article 6", "780 €"), references and
//! codes. A keyword index catches those; [`crate::search`] fuses both
//! rankings.
//!
//! Terms are folded so that a question matches the documents whatever its
//! spelling: lower case, accents removed (`préavis` = `preavis`), `ß`/`œ`/`æ`
//! spelled out, stop words of French, English and German dropped, and words
//! of more than [`STEM_CHARS`] letters cut to their first [`STEM_CHARS`]
//! letters. Cutting is a crude stemmer that works across languages:
//! `résilier`, `résiliation` and `résilié` all give `resili`. Numbers are
//! kept whole.
//!
//! The index is built in memory when an index is loaded (from the passage
//! text and its section), so the published index files do not change.

use std::collections::{HashMap, HashSet};
use unicode_normalization::UnicodeNormalization;

/// Letters kept of a long word (see the module documentation).
pub const STEM_CHARS: usize = 6;
/// BM25 term-frequency saturation.
const K1: f32 = 1.2;
/// BM25 length normalization.
const B: f32 = 0.75;

/// Stop words of French, English and German, already folded (no accents).
const STOP_WORDS: &[&str] = &[
    // French
    "a", "au", "aux", "avec", "ce", "ces", "cet", "cette", "dans", "de", "des", "du", "elle", "en",
    "est", "et", "etre", "il", "ils", "je", "la", "le", "les", "leur", "lui", "ma", "mais", "me",
    "mes", "mon", "ne", "nos", "notre", "nous", "on", "ou", "par", "pas", "pour", "qu", "que",
    "qui", "sa", "se", "ses", "son", "sont", "sur", "ta", "te", "tes", "ton", "tu", "un", "une",
    "vos", "votre", "vous", "y", "quel", "quelle", "quels", "quelles", "comment", "combien",
    "quand", "est-ce", "ai", "as", "avez", "avons", "ont", "suis", "etes", "sommes", "faut",
    "peut", "peux", "puis", "dois", "doit", "si", "ca", "cela", "ceci", "dont", "ainsi", "plus",
    "moins", "tres", "aussi", // English
    "the", "an", "and", "or", "of", "to", "in", "on", "at", "for", "with", "by", "from", "is",
    "are", "was", "were", "be", "been", "it", "its", "this", "that", "these", "those", "as", "if",
    "do", "does", "did", "can", "could", "should", "would", "will", "shall", "may", "must", "my",
    "your", "our", "their", "his", "her", "we", "you", "they", "he", "she", "i", "me", "us",
    "them", "what", "which", "who", "whom", "how", "when", "where", "why", "there", "here", "have",
    "has", "had", "not", "no", "so", "than", "then", "into", "about", "any", "all",
    // German
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines",
    "und", "oder", "ist", "sind", "war", "wird", "werden", "im", "zu", "zum", "zur", "mit", "von",
    "vom", "fur", "auf", "aus", "bei", "nach", "uber", "unter", "wie", "was", "wer", "wann", "wo",
    "warum", "welche", "welcher", "welches", "ich", "du", "er", "sie", "es", "wir", "ihr", "mein",
    "dein", "sein", "kann", "muss", "darf", "soll", "nicht", "kein", "keine", "auch", "noch",
    "nur", "man", "sich", "wenn", "dass", "als", "am", "um", "bis", "gibt", "habe", "hat", "haben",
];

/// The search terms of a text, in order, repeated as they occur.
pub fn terms(text: &str) -> Vec<String> {
    let stop_words: &HashSet<&str> = stop_words();
    let folded = fold(text);
    folded
        .split(|c: char| !c.is_alphanumeric())
        .filter(|word| !word.is_empty())
        .filter(|word| !stop_words.contains(word))
        .filter_map(stem)
        .collect()
}

/// Lower case, accents removed, ligatures spelled out, runs of white space
/// as one space: two texts equal for a reader are equal folded.
pub fn fold_text(text: &str) -> String {
    fold(text).split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Lower case, accents removed, ligatures spelled out.
fn fold(text: &str) -> String {
    text.nfd()
        .filter(|c| !unicode_normalization::char::is_combining_mark(*c))
        .flat_map(char::to_lowercase)
        .flat_map(|c| match c {
            'ß' => "ss".chars().collect::<Vec<_>>(),
            'œ' => "oe".chars().collect(),
            'æ' => "ae".chars().collect(),
            other => vec![other],
        })
        .collect()
}

/// A word as a term: numbers whole, words of one letter dropped, long
/// words cut, a plural `s` removed from short ones.
fn stem(word: &str) -> Option<String> {
    if word.chars().all(|c| c.is_ascii_digit()) {
        return Some(word.to_string());
    }
    let length = word.chars().count();
    if length < 2 {
        return None;
    }
    if length > STEM_CHARS {
        return Some(word.chars().take(STEM_CHARS).collect());
    }
    if length > 3 && word.ends_with('s') {
        return Some(word[..word.len() - 1].to_string());
    }
    Some(word.to_string())
}

fn stop_words() -> &'static HashSet<&'static str> {
    static WORDS: std::sync::OnceLock<HashSet<&'static str>> = std::sync::OnceLock::new();
    WORDS.get_or_init(|| STOP_WORDS.iter().copied().collect())
}

/// The distinct terms of a query, in order of first appearance.
pub fn query_terms(query: &str) -> Vec<String> {
    let mut seen = HashSet::new();
    terms(query)
        .into_iter()
        .filter(|term| seen.insert(term.clone()))
        .collect()
}

/// Inverted index of the passages of one index.
#[derive(Debug, Clone, Default)]
pub struct LexicalIndex {
    /// Term to (passage id, occurrences), by passage id.
    postings: HashMap<String, Vec<(u32, u16)>>,
    /// Number of terms of each passage.
    lengths: Vec<u32>,
    total_length: u64,
}

impl LexicalIndex {
    /// Indexes `texts`, passage `i` being the `i`-th text.
    pub fn build<'a>(texts: impl IntoIterator<Item = &'a str>) -> Self {
        let mut index = LexicalIndex::default();
        for (id, text) in texts.into_iter().enumerate() {
            let terms = terms(text);
            let mut counts: HashMap<String, u16> = HashMap::new();
            for term in &terms {
                let count = counts.entry(term.clone()).or_default();
                *count = count.saturating_add(1);
            }
            for (term, count) in counts {
                index
                    .postings
                    .entry(term)
                    .or_default()
                    .push((id as u32, count));
            }
            index.lengths.push(terms.len() as u32);
            index.total_length += terms.len() as u64;
        }
        index
    }

    /// Number of passages indexed.
    pub fn passage_count(&self) -> usize {
        self.lengths.len()
    }

    /// Passages that contain `term`.
    pub fn document_frequency(&self, term: &str) -> usize {
        self.postings.get(term).map_or(0, Vec::len)
    }

    /// The `k` passages of best BM25 score for `terms`, best first, with
    /// the collection statistics `stats` (so that the scores of several
    /// indexes can be compared).
    pub fn search(&self, terms: &[String], stats: &Bm25Stats, k: usize) -> Vec<(u64, f32)> {
        let mut scores: HashMap<u32, f32> = HashMap::new();
        for term in terms {
            let (Some(postings), Some(idf)) = (self.postings.get(term), stats.idf.get(term)) else {
                continue;
            };
            for &(id, count) in postings {
                let tf = f32::from(count);
                let length = self.lengths[id as usize] as f32;
                let norm = K1 * (1.0 - B + B * length / stats.average_length.max(1.0));
                *scores.entry(id).or_default() += idf * tf * (K1 + 1.0) / (tf + norm);
            }
        }
        crate::index::top_k(
            scores.into_iter().map(|(id, score)| (u64::from(id), score)),
            k,
        )
    }

    /// Approximate memory held, in bytes.
    pub fn memory_bytes(&self) -> usize {
        self.lengths.len() * 4
            + self
                .postings
                .iter()
                .map(|(term, postings)| term.len() + 48 + postings.len() * 8)
                .sum::<usize>()
    }
}

/// Collection statistics of a keyword search over one or more indexes.
#[derive(Debug, Clone, PartialEq)]
pub struct Bm25Stats {
    pub average_length: f32,
    /// Inverse document frequency of each query term found somewhere.
    pub idf: HashMap<String, f32>,
}

impl Bm25Stats {
    /// Statistics of `terms` over all of `indexes`.
    pub fn over(indexes: &[&LexicalIndex], terms: &[String]) -> Self {
        let passages: usize = indexes.iter().map(|index| index.passage_count()).sum();
        let total: u64 = indexes.iter().map(|index| index.total_length).sum();
        let average_length = if passages == 0 {
            0.0
        } else {
            total as f32 / passages as f32
        };
        let idf = terms
            .iter()
            .filter_map(|term| {
                let df: usize = indexes
                    .iter()
                    .map(|index| index.document_frequency(term))
                    .sum();
                (df > 0).then(|| {
                    let (n, df) = (passages as f32, df as f32);
                    (term.clone(), ((n - df + 0.5) / (df + 0.5) + 1.0).ln())
                })
            })
            .collect();
        Self {
            average_length,
            idf,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn terms_ignore_case_accents_stop_words_and_endings() {
        assert_eq!(
            terms("Comment RÉSILIER le contrat ? Résiliation, l'article 6"),
            vec!["resili", "contra", "resili", "articl", "6"]
        );
        assert_eq!(
            terms("Straße Œuvre bikes"),
            vec!["strass", "oeuvre", "bike"]
        );
        assert_eq!(terms("Kündigungsfrist"), terms("kundigungsfrist"));
    }

    #[test]
    fn query_terms_are_distinct() {
        assert_eq!(query_terms("préavis préavis du préavis"), vec!["preavi"]);
    }

    #[test]
    fn rare_and_repeated_terms_score_higher() {
        let index = LexicalIndex::build([
            "le loyer est de 780 euros",
            "le préavis est d'un mois",
            "préavis préavis : un mois de préavis",
            "les animaux sont autorisés",
        ]);
        let terms = query_terms("quel préavis ?");
        let stats = Bm25Stats::over(&[&index], &terms);
        let hits = index.search(&terms, &stats, 10);
        assert_eq!(hits.iter().map(|h| h.0).collect::<Vec<_>>(), vec![2, 1]);
        let number = query_terms("780");
        let stats = Bm25Stats::over(&[&index], &number);
        assert_eq!(index.search(&number, &stats, 10)[0].0, 0);
    }

    #[test]
    fn statistics_cover_every_index() {
        let a = LexicalIndex::build(["chat", "chat chien"]);
        let b = LexicalIndex::build(["chien", "poisson", "poisson rouge"]);
        let terms = query_terms("chat poisson");
        let stats = Bm25Stats::over(&[&a, &b], &terms);
        assert!((stats.average_length - 7.0 / 5.0).abs() < 1e-6);
        assert_eq!(stats.idf.len(), 2);
        assert!(stats.idf["chat"] > 0.0 && stats.idf["poisso"] > 0.0);
        assert!(
            Bm25Stats::over(&[&a], &query_terms("absent"))
                .idf
                .is_empty()
        );
    }
}
