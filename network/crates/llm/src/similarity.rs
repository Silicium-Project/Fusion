//! How close two answers are, and the verdict of a verifier.
//!
//! A verifier recomputes a few items of a fragment ([`sample_size`]) and
//! compares its answers with the worker's. Greedy decoding makes two honest
//! machines agree most of the time, but not always: processors and GPUs
//! round differently, and once one token differs the rest of a long answer
//! follows another path. Answers are therefore compared by similarity, not
//! byte for byte:
//!
//! - **label**: equal or not;
//! - **text**: 1 when equal after normalization, else the ROUGE-L F1 of
//!   their words (longest common subsequence: a paraphrase that keeps the
//!   order of the facts scores high, an unrelated text, a copy of the
//!   input or an empty answer scores low);
//! - **fields**: the mean of the text similarity of each field.
//!
//! The thresholds ([`Thresholds::for_output`]) are first values, to be
//! calibrated on real machines with `silicium-llm compare` (see the crate
//! README): too high and honest workers are refused, too low and a worker
//! running a smaller model passes.

use crate::request::OutputSpec;
use serde_json::Value;

/// Words compared at most per answer (bounds the cost of ROUGE-L).
const MAX_TOKENS_COMPARED: usize = 1500;

/// What a verifier accepts.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Thresholds {
    /// Smallest mean similarity over the items recomputed.
    pub min_mean: f64,
    /// Smallest similarity of any one item.
    pub min_item: f64,
}

impl Thresholds {
    pub fn for_output(output: &OutputSpec) -> Thresholds {
        match output {
            // One label in three may differ (an item on the border between
            // two categories), not more.
            OutputSpec::Label { .. } => Thresholds {
                min_mean: 0.66,
                min_item: 0.0,
            },
            OutputSpec::Text | OutputSpec::Fields { .. } => Thresholds {
                min_mean: 0.6,
                min_item: 0.2,
            },
        }
    }

    /// True when `scores` (one per item recomputed) pass.
    pub fn accept(&self, scores: &[f64]) -> bool {
        if scores.is_empty() {
            return false;
        }
        let mean = scores.iter().sum::<f64>() / scores.len() as f64;
        mean >= self.min_mean && scores.iter().all(|score| *score >= self.min_item)
    }
}

/// Items a verifier recomputes in a fragment of `count` items: labels are
/// short to compute, so more of them.
pub fn sample_size(output: &OutputSpec, count: usize) -> usize {
    let size = match output {
        OutputSpec::Label { .. } => count.div_ceil(4).clamp(3, 6),
        _ => count.div_ceil(6).clamp(2, 4),
    };
    size.min(count)
}

/// Similarity in `[0, 1]` of a worker's answer and a verifier's.
pub fn answer_similarity(output: &OutputSpec, worker: &Value, verifier: &Value) -> f64 {
    match (worker, verifier) {
        (Value::Null, Value::Null) => 1.0,
        (Value::Null, _) | (_, Value::Null) => 0.0,
        _ => match output {
            OutputSpec::Text => text_similarity(as_text(worker), as_text(verifier)),
            OutputSpec::Label { .. } => f64::from(u8::from(worker == verifier)),
            OutputSpec::Fields { fields } => {
                if fields.is_empty() {
                    return 0.0;
                }
                let field = |value: &Value, name: &str| {
                    value
                        .get(name)
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string()
                };
                fields
                    .iter()
                    .map(|name| text_similarity(&field(worker, name), &field(verifier, name)))
                    .sum::<f64>()
                    / fields.len() as f64
            }
        },
    }
}

fn as_text(value: &Value) -> &str {
    value.as_str().unwrap_or("")
}

/// Similarity in `[0, 1]` of two texts: 1 when their words are the same,
/// else the ROUGE-L F1 of their words.
pub fn text_similarity(a: &str, b: &str) -> f64 {
    let (a, b) = (words(a), words(b));
    if a == b {
        return 1.0;
    }
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let common = lcs_length(&a, &b) as f64;
    if common == 0.0 {
        return 0.0;
    }
    let precision = common / a.len() as f64;
    let recall = common / b.len() as f64;
    2.0 * precision * recall / (precision + recall)
}

/// Lowercase words: runs of letters and digits, every ideogram, kana or
/// hangul syllable on its own (those scripts write no spaces).
pub fn words(text: &str) -> Vec<String> {
    let mut words = Vec::new();
    let mut current = String::new();
    for c in text.chars() {
        if is_cjk(c) {
            if !current.is_empty() {
                words.push(std::mem::take(&mut current));
            }
            words.push(c.to_string());
        } else if c.is_alphanumeric() {
            current.extend(c.to_lowercase());
        } else if !current.is_empty() {
            words.push(std::mem::take(&mut current));
        }
        if words.len() >= MAX_TOKENS_COMPARED {
            return words;
        }
    }
    if !current.is_empty() {
        words.push(current);
    }
    words
}

fn is_cjk(c: char) -> bool {
    matches!(c as u32,
        0x3040..=0x30FF   // hiragana, katakana
        | 0x3400..=0x4DBF // CJK extension A
        | 0x4E00..=0x9FFF // CJK unified ideographs
        | 0xAC00..=0xD7AF // hangul syllables
        | 0xF900..=0xFAFF) // CJK compatibility ideographs
}

/// Length of the longest common subsequence of `a` and `b`.
fn lcs_length(a: &[String], b: &[String]) -> usize {
    let mut previous = vec![0usize; b.len() + 1];
    let mut current = vec![0usize; b.len() + 1];
    for word in a {
        for (j, other) in b.iter().enumerate() {
            current[j + 1] = if word == other {
                previous[j] + 1
            } else {
                current[j].max(previous[j + 1])
            };
        }
        std::mem::swap(&mut previous, &mut current);
    }
    previous[b.len()]
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn identical_texts_score_one_whatever_their_spacing_and_case() {
        assert_eq!(
            text_similarity("Bonjour, le monde !", "bonjour le  MONDE"),
            1.0
        );
        assert_eq!(text_similarity("", ""), 1.0);
        assert_eq!(text_similarity("a", ""), 0.0);
    }

    #[test]
    fn a_diverging_ending_keeps_a_high_score() {
        let honest = "La livraison a été rapide et le produit correspond à la description, \
                      le client est satisfait.";
        let other_cpu = "La livraison a été rapide et le produit correspond à la description ; \
                         le client recommande le vendeur.";
        assert!(text_similarity(honest, other_cpu) > 0.7);
    }

    #[test]
    fn unrelated_copied_or_empty_answers_score_low() {
        let answer = "Le contrat peut être résilié avec un préavis de trois mois.";
        let unrelated = "Il fait beau aujourd'hui sur toute la Bretagne.";
        assert!(text_similarity(answer, unrelated) < 0.2);
        let input = format!(
            "{} {}",
            "Article 6 . Les parties conviennent de ce qui suit".repeat(10),
            answer
        );
        assert!(text_similarity(&input, answer) < 0.3, "a copy of the input");
    }

    #[test]
    fn ideograms_are_words() {
        assert_eq!(words("日本語abc 12"), ["日", "本", "語", "abc", "12"]);
        assert!(text_similarity("我喜欢猫", "我喜欢狗") > 0.7);
    }

    #[test]
    fn answers_are_compared_by_kind() {
        let labels = OutputSpec::Label {
            labels: vec!["a".into(), "b".into()],
        };
        assert_eq!(answer_similarity(&labels, &json!("a"), &json!("a")), 1.0);
        assert_eq!(answer_similarity(&labels, &json!("a"), &json!("b")), 0.0);
        assert_eq!(answer_similarity(&labels, &Value::Null, &Value::Null), 1.0);
        assert_eq!(answer_similarity(&labels, &json!("a"), &Value::Null), 0.0);
        let fields = OutputSpec::Fields {
            fields: vec!["nom".into(), "date".into()],
        };
        let score = answer_similarity(
            &fields,
            &json!({"nom": "Alice Martin", "date": "3 mars"}),
            &json!({"nom": "Alice Martin", "date": ""}),
        );
        assert_eq!(score, 0.5);
    }

    #[test]
    fn verdicts_follow_the_thresholds() {
        let text = Thresholds::for_output(&OutputSpec::Text);
        assert!(text.accept(&[1.0, 0.7, 0.5]));
        assert!(!text.accept(&[1.0, 0.1]), "one item far off");
        assert!(!text.accept(&[0.5, 0.5]));
        assert!(!text.accept(&[]));
        let labels = Thresholds::for_output(&OutputSpec::Label { labels: vec![] });
        assert!(labels.accept(&[1.0, 1.0, 0.0]));
        assert!(!labels.accept(&[1.0, 0.0, 0.0]));
    }

    #[test]
    fn samples_are_small_but_never_empty() {
        assert_eq!(sample_size(&OutputSpec::Text, 1), 1);
        assert_eq!(sample_size(&OutputSpec::Text, 8), 2);
        assert_eq!(sample_size(&OutputSpec::Text, 100), 4);
        let labels = OutputSpec::Label { labels: vec![] };
        assert_eq!(sample_size(&labels, 2), 2);
        assert_eq!(sample_size(&labels, 16), 4);
    }
}
