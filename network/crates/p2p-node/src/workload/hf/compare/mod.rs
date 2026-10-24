//! How a verifier compares a worker's output with its own, by task.
//!
//! Two honest machines can round differently (CPU and GPU, two GPU models),
//! so most outputs are compared by a similarity in `[0, 1]` rather than
//! equality, with a threshold on the mean and on each item of the sample.
//! The outputs follow the Hub's task schemas (`@huggingface/tasks`), as
//! the Silicium AI runtime writes them for one item.

use serde_json::Value;
use silicium_llm::similarity::{text_similarity, words};

/// The comparison of a task.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Metric {
    /// Same top-1 label (classification, fill-mask).
    Label,
    /// ROUGE-L of the words (generated text).
    Text,
    /// 1 − word error rate (speech recognition).
    Wer,
    /// Cosine of the vectors (embeddings).
    Vector,
    /// Close scores (sentence similarity).
    Scores,
    /// Same order of the ranked texts (pairwise agreement).
    Ranking,
    /// F1 of the (entity, word) pairs (token classification).
    Entities,
    /// Word F1 of the answers (question answering).
    AnswerF1,
    /// Same answer, normalized (table question answering).
    ExactAnswer,
    /// F1 of the boxes matched by label and IoU ≥ 0.5 (object detection).
    Boxes,
}

/// The tasks this workload runs, with their comparison. Tasks of the Hub
/// that are not here are refused (their turn comes in the next steps).
pub(crate) const TASKS: &[(&str, Metric)] = &[
    ("text-classification", Metric::Label),
    ("token-classification", Metric::Entities),
    ("question-answering", Metric::AnswerF1),
    ("zero-shot-classification", Metric::Label),
    ("translation", Metric::Text),
    ("summarization", Metric::Text),
    ("feature-extraction", Metric::Vector),
    ("text-generation", Metric::Text),
    ("fill-mask", Metric::Label),
    ("sentence-similarity", Metric::Scores),
    ("text-ranking", Metric::Ranking),
    ("table-question-answering", Metric::ExactAnswer),
    ("image-classification", Metric::Label),
    ("zero-shot-image-classification", Metric::Label),
    ("object-detection", Metric::Boxes),
    ("image-to-text", Metric::Text),
    ("image-feature-extraction", Metric::Vector),
    ("automatic-speech-recognition", Metric::Wer),
    ("audio-classification", Metric::Label),
];

/// The comparison of `task`, when this workload runs it.
pub(crate) fn metric(task: &str) -> Option<Metric> {
    TASKS
        .iter()
        .find(|(id, _)| *id == task)
        .map(|(_, metric)| *metric)
}

impl Metric {
    /// Least mean and least single similarity of an accepted sample.
    fn thresholds(self) -> (f64, f64) {
        match self {
            Metric::Label | Metric::ExactAnswer => (0.66, 0.0),
            Metric::Text => (0.6, 0.2),
            Metric::Wer => (0.7, 0.3),
            Metric::Vector => (0.98, 0.95),
            Metric::Scores | Metric::Entities => (0.8, 0.5),
            Metric::Ranking => (0.85, 0.6),
            Metric::AnswerF1 | Metric::Boxes => (0.7, 0.3),
        }
    }

    /// Similarity in `[0, 1]` of a worker's and a verifier's output.
    pub(crate) fn similarity(self, worker: &Value, verifier: &Value) -> f64 {
        let score = match self {
            Metric::Label => equal(top_label(worker), top_label(verifier)),
            Metric::ExactAnswer => equal(
                answer(worker).map(normalized),
                answer(verifier).map(normalized),
            ),
            Metric::Text => text_similarity(text(worker), text(verifier)),
            Metric::Wer => 1.0 - word_error_rate(text(verifier), text(worker)).min(1.0),
            Metric::Vector => cosine(&numbers(worker), &numbers(verifier)),
            Metric::Scores => scores_similarity(&numbers(worker), &numbers(verifier)),
            Metric::Ranking => pairwise_agreement(&ranking(worker), &ranking(verifier)),
            Metric::Entities => f1(&entities(worker), &entities(verifier)),
            Metric::AnswerF1 => {
                word_f1(answer(worker).unwrap_or(""), answer(verifier).unwrap_or(""))
            }
            Metric::Boxes => boxes_f1(&boxes(worker), &boxes(verifier)),
        };
        if score.is_finite() {
            score.clamp(0.0, 1.0)
        } else {
            0.0
        }
    }

    /// True when the similarities of a sample pass the thresholds.
    pub(crate) fn accept(self, scores: &[f64]) -> bool {
        if scores.is_empty() {
            return false;
        }
        let (mean_min, item_min) = self.thresholds();
        let mean = scores.iter().sum::<f64>() / scores.len() as f64;
        mean >= mean_min && scores.iter().all(|score| *score >= item_min)
    }
}

fn equal<T: PartialEq>(a: Option<T>, b: Option<T>) -> f64 {
    match (a, b) {
        (Some(a), Some(b)) if a == b => 1.0,
        _ => 0.0,
    }
}

/// First element of a list (pipelines answer one item as a list).
fn first(value: &Value) -> &Value {
    match value {
        Value::Array(items) if !items.is_empty() => &items[0],
        other => other,
    }
}

/// The top label: `[{label|token_str, score}]` sorted by score, or the
/// zero-shot `{labels: [...], scores: [...]}`.
fn top_label(value: &Value) -> Option<&str> {
    if let Some(labels) = value.get("labels").and_then(Value::as_array) {
        return labels.first().and_then(Value::as_str);
    }
    let best = match value {
        Value::Array(items) => items.iter().max_by(|a, b| {
            let score = |v: &Value| v.get("score").and_then(Value::as_f64).unwrap_or(0.0);
            score(a).total_cmp(&score(b))
        })?,
        other => other,
    };
    best.get("label")
        .or_else(|| best.get("token_str"))
        .and_then(Value::as_str)
}

fn text(value: &Value) -> &str {
    let value = first(value);
    if let Some(text) = value.as_str() {
        return text;
    }
    for key in [
        "generated_text",
        "summary_text",
        "translation_text",
        "text",
        "answer",
    ] {
        if let Some(text) = value.get(key).and_then(Value::as_str) {
            return text;
        }
    }
    ""
}

fn answer(value: &Value) -> Option<&str> {
    first(value).get("answer").and_then(Value::as_str)
}

fn normalized(text: &str) -> String {
    words(text).join(" ")
}

fn numbers(value: &Value) -> Vec<f64> {
    let mut out = Vec::new();
    collect_numbers(value, &mut out);
    out
}

fn collect_numbers(value: &Value, out: &mut Vec<f64>) {
    match value {
        Value::Number(number) => out.extend(number.as_f64()),
        Value::Array(items) => items.iter().for_each(|item| collect_numbers(item, out)),
        _ => {}
    }
}

fn cosine(a: &[f64], b: &[f64]) -> f64 {
    if a.is_empty() || a.len() != b.len() {
        return 0.0;
    }
    let dot: f64 = a.iter().zip(b).map(|(x, y)| x * y).sum();
    let norm = |v: &[f64]| v.iter().map(|x| x * x).sum::<f64>().sqrt();
    let (na, nb) = (norm(a), norm(b));
    if na == 0.0 || nb == 0.0 {
        return if na == nb { 1.0 } else { 0.0 };
    }
    dot / (na * nb)
}

/// 1 when every score is within 0.01, 0 from 0.05 apart.
fn scores_similarity(a: &[f64], b: &[f64]) -> f64 {
    if a.is_empty() || a.len() != b.len() {
        return 0.0;
    }
    let worst = a
        .iter()
        .zip(b)
        .map(|(x, y)| (x - y).abs())
        .fold(0.0, f64::max);
    1.0 - ((worst - 0.01).max(0.0) / 0.04).min(1.0)
}

/// The ranked indices of `[{index, score}]`, best first.
fn ranking(value: &Value) -> Vec<u64> {
    let mut ranked: Vec<(u64, f64)> = value
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    Some((
                        item.get("index")?.as_u64()?,
                        item.get("score").and_then(Value::as_f64).unwrap_or(0.0),
                    ))
                })
                .collect()
        })
        .unwrap_or_default();
    ranked.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
    ranked.into_iter().map(|(index, _)| index).collect()
}

/// Share of the pairs of indices ranked in the same order.
fn pairwise_agreement(a: &[u64], b: &[u64]) -> f64 {
    let mut sorted_a = a.to_vec();
    let mut sorted_b = b.to_vec();
    sorted_a.sort_unstable();
    sorted_b.sort_unstable();
    if a.is_empty() || sorted_a != sorted_b {
        return 0.0;
    }
    if a.len() == 1 {
        return 1.0;
    }
    let position = |list: &[u64], index: u64| list.iter().position(|i| *i == index).unwrap_or(0);
    let (mut agree, mut pairs) = (0usize, 0usize);
    for (i, x) in a.iter().enumerate() {
        for y in &a[i + 1..] {
            pairs += 1;
            if position(b, *x) < position(b, *y) {
                agree += 1;
            }
        }
    }
    agree as f64 / pairs as f64
}

fn entities(value: &Value) -> Vec<(String, String)> {
    let mut out: Vec<(String, String)> = value
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    let kind = item
                        .get("entity_group")
                        .or_else(|| item.get("entity"))?
                        .as_str()?;
                    let word = item.get("word")?.as_str()?;
                    Some((kind.to_string(), normalized(word)))
                })
                .collect()
        })
        .unwrap_or_default();
    out.sort();
    out
}

/// F1 of two multisets (sorted).
fn f1<T: Ord>(a: &[T], b: &[T]) -> f64 {
    if a.is_empty() && b.is_empty() {
        return 1.0;
    }
    let (mut i, mut j, mut common) = (0, 0, 0usize);
    while i < a.len() && j < b.len() {
        match a[i].cmp(&b[j]) {
            std::cmp::Ordering::Equal => {
                common += 1;
                i += 1;
                j += 1;
            }
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
        }
    }
    2.0 * common as f64 / (a.len() + b.len()) as f64
}

fn word_f1(a: &str, b: &str) -> f64 {
    let (mut a, mut b) = (words(a), words(b));
    a.sort();
    b.sort();
    f1(&a, &b)
}

/// Word error rate of `hypothesis` against `reference`.
fn word_error_rate(reference: &str, hypothesis: &str) -> f64 {
    let (r, h) = (words(reference), words(hypothesis));
    if r.is_empty() {
        return if h.is_empty() { 0.0 } else { 1.0 };
    }
    let mut previous: Vec<usize> = (0..=h.len()).collect();
    for (i, rw) in r.iter().enumerate() {
        let mut current = vec![i + 1; h.len() + 1];
        for (j, hw) in h.iter().enumerate() {
            let substitution = previous[j] + usize::from(rw != hw);
            current[j + 1] = substitution.min(previous[j + 1] + 1).min(current[j] + 1);
        }
        previous = current;
    }
    previous[h.len()] as f64 / r.len() as f64
}

struct Detection {
    label: String,
    rect: [f64; 4],
}

fn boxes(value: &Value) -> Vec<Detection> {
    value
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    let label = item.get("label")?.as_str()?.to_string();
                    let b = item.get("box")?;
                    let coordinate = |key: &str| b.get(key).and_then(Value::as_f64);
                    Some(Detection {
                        label,
                        rect: [
                            coordinate("xmin")?,
                            coordinate("ymin")?,
                            coordinate("xmax")?,
                            coordinate("ymax")?,
                        ],
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

fn iou(a: &[f64; 4], b: &[f64; 4]) -> f64 {
    let width = (a[2].min(b[2]) - a[0].max(b[0])).max(0.0);
    let height = (a[3].min(b[3]) - a[1].max(b[1])).max(0.0);
    let intersection = width * height;
    let area = |r: &[f64; 4]| (r[2] - r[0]).max(0.0) * (r[3] - r[1]).max(0.0);
    let union = area(a) + area(b) - intersection;
    if union <= 0.0 {
        0.0
    } else {
        intersection / union
    }
}

fn boxes_f1(a: &[Detection], b: &[Detection]) -> f64 {
    if a.is_empty() && b.is_empty() {
        return 1.0;
    }
    let mut used = vec![false; b.len()];
    let mut matched = 0usize;
    for detection in a {
        let best = b
            .iter()
            .enumerate()
            .filter(|(j, other)| !used[*j] && other.label == detection.label)
            .map(|(j, other)| (j, iou(&detection.rect, &other.rect)))
            .filter(|(_, overlap)| *overlap >= 0.5)
            .max_by(|x, y| x.1.total_cmp(&y.1));
        if let Some((j, _)) = best {
            used[j] = true;
            matched += 1;
        }
    }
    2.0 * matched as f64 / (a.len() + b.len()) as f64
}

#[cfg(test)]
mod tests;
