//! Quality of the search, measured on a set of questions.
//!
//! An evaluation set is a directory with the documents searched
//! (`documents/`, any format [`crate::documents`] reads) and the questions
//! (`questions.jsonl`), one [`Question`] per line:
//!
//! ```text
//! {"id":"fr-bail-03","lang":"fr","question":"Combien de temps pour partir ?",
//!  "expected":[{"document":"contrat-de-location.md","contains":"préavis est d'un mois"}]}
//! ```
//!
//! A result answers the question when it comes from an expected document
//! and contains the expected words (compared folded: case, accents and
//! spaces ignored), so the set stays valid when the chunking changes.
//!
//! [`evaluate`] reports, for one search mode, the share of questions
//! answered in the first 1, 3, 5 and 10 results (recall@k) and the mean
//! reciprocal rank of the first answer (MRR@10), overall and per language.
//! `silicium-embed eval` runs it (see the crate README); the set of this
//! repository is in `crates/embedding/eval/`.

use crate::{
    Error, Result,
    index::{Index, IndexPassage},
    lexical::fold_text,
    search::{self, Mode},
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// The ranks reported.
pub const CUTOFFS: [usize; 4] = [1, 3, 5, 10];
/// Results looked at per question.
pub const DEPTH: usize = 10;

/// A question of the set.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Question {
    pub id: String,
    pub lang: String,
    pub question: String,
    pub expected: Vec<Expected>,
}

/// A passage that answers a question.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Expected {
    /// File name of the document (a path inside an archive matches by its
    /// last part).
    pub document: String,
    /// Words the passage contains.
    pub contains: String,
}

/// Reads `questions.jsonl`.
pub fn read_questions(text: &str) -> Result<Vec<Question>> {
    text.lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
        .map(|(number, line)| {
            serde_json::from_str(line)
                .map_err(|err| Error::Format(format!("question line {}: {err}", number + 1)))
        })
        .collect()
}

/// True when `passage` answers one of `expected`.
pub fn answers(passage: &IndexPassage, expected: &[Expected]) -> bool {
    let name = passage
        .document
        .rsplit('/')
        .next()
        .unwrap_or(&passage.document);
    let text = fold_text(&format!("{} {}", passage.section, passage.text));
    expected
        .iter()
        .any(|e| e.document == name && text.contains(&fold_text(&e.contains)))
}

/// Measures of one mode.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Report {
    pub mode: String,
    pub overall: Scores,
    pub by_lang: BTreeMap<String, Scores>,
    /// Questions not answered in the first [`DEPTH`] results.
    pub missed: Vec<String>,
}

/// Recall at each cutoff and mean reciprocal rank.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Scores {
    pub questions: usize,
    /// Share of questions answered in the first `k` results, by `k`.
    pub recall: BTreeMap<usize, f32>,
    pub mrr: f32,
}

impl Scores {
    fn from_ranks(ranks: &[Option<usize>]) -> Self {
        let count = ranks.len().max(1) as f32;
        let recall = CUTOFFS
            .iter()
            .map(|&k| {
                let hits = ranks
                    .iter()
                    .filter(|rank| rank.is_some_and(|r| r <= k))
                    .count();
                (k, hits as f32 / count)
            })
            .collect();
        let mrr = ranks
            .iter()
            .map(|rank| rank.map_or(0.0, |r| 1.0 / r as f32))
            .sum::<f32>()
            / count;
        Self {
            questions: ranks.len(),
            recall,
            mrr,
        }
    }
}

/// Runs `questions` on `index` in `mode`. `embed` turns a question into a
/// query vector (needed except in [`Mode::Lexical`]).
pub fn evaluate(
    index: &Index,
    questions: &[Question],
    mode: Mode,
    embed: &dyn Fn(&str) -> Result<Vec<f32>>,
) -> Result<Report> {
    let mut ranks: Vec<(String, Option<usize>)> = Vec::new();
    let mut missed = Vec::new();
    for question in questions {
        let vector = match mode {
            Mode::Lexical => None,
            _ => Some(embed(&question.question)?),
        };
        let found = search::search(&[index], vector.as_deref(), &question.question, DEPTH, mode)?;
        let mut rank = None;
        for (position, hit) in found.iter().enumerate() {
            if answers(&index.passage(hit.id)?, &question.expected) {
                rank = Some(position + 1);
                break;
            }
        }
        if rank.is_none() {
            missed.push(question.id.clone());
        }
        ranks.push((question.lang.clone(), rank));
    }
    let mut by_lang: BTreeMap<String, Vec<Option<usize>>> = BTreeMap::new();
    for (lang, rank) in &ranks {
        by_lang.entry(lang.clone()).or_default().push(*rank);
    }
    Ok(Report {
        mode: format!("{mode:?}").to_lowercase(),
        overall: Scores::from_ranks(&ranks.iter().map(|(_, rank)| *rank).collect::<Vec<_>>()),
        by_lang: by_lang
            .into_iter()
            .map(|(lang, ranks)| (lang, Scores::from_ranks(&ranks)))
            .collect(),
        missed,
    })
}

/// A report as a few lines of text.
pub fn format_report(report: &Report) -> String {
    let line = |label: &str, scores: &Scores| {
        let recall: Vec<String> = scores
            .recall
            .iter()
            .map(|(k, value)| format!("R@{k} {:>5.1}%", value * 100.0))
            .collect();
        format!(
            "  {label:<8} {:>3} q  {}  MRR {:.3}",
            scores.questions,
            recall.join("  "),
            scores.mrr
        )
    };
    let mut lines = vec![format!("{}:", report.mode), line("all", &report.overall)];
    for (lang, scores) in &report.by_lang {
        lines.push(line(lang, scores));
    }
    if !report.missed.is_empty() {
        lines.push(format!("  missed: {}", report.missed.join(", ")));
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn passage(document: &str, section: &str, text: &str) -> IndexPassage {
        IndexPassage {
            id: 0,
            document: document.into(),
            page: None,
            section: section.into(),
            text: text.into(),
        }
    }

    #[test]
    fn an_answer_is_matched_folded_in_the_expected_document() {
        let expected = vec![Expected {
            document: "bail.md".into(),
            contains: "Préavis  d'un MOIS".into(),
        }];
        assert!(answers(
            &passage("docs/bail.md", "", "Le preavis d'un mois court…"),
            &expected
        ));
        assert!(answers(
            &passage("bail.md", "Préavis d'un mois", "…"),
            &expected
        ));
        assert!(!answers(
            &passage("autre.md", "", "préavis d'un mois"),
            &expected
        ));
        assert!(!answers(
            &passage("bail.md", "", "préavis de trois mois"),
            &expected
        ));
    }

    #[test]
    fn scores_count_ranks_up_to_each_cutoff() {
        let scores = Scores::from_ranks(&[Some(1), Some(3), None, Some(10)]);
        assert_eq!(scores.recall[&1], 0.25);
        assert_eq!(scores.recall[&3], 0.5);
        assert_eq!(scores.recall[&10], 0.75);
        assert!((scores.mrr - (1.0 + 1.0 / 3.0 + 0.1) / 4.0).abs() < 1e-6);
    }

    #[test]
    fn questions_are_read_from_json_lines() {
        let questions =
            read_questions("{\"id\":\"a\",\"lang\":\"fr\",\"question\":\"?\",\"expected\":[]}\n\n")
                .unwrap();
        assert_eq!(questions.len(), 1);
        assert!(read_questions("{oops}").is_err());
    }
}
