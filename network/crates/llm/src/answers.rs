//! The answers a worker publishes for a fragment: `silicium-llm-answers/1`,
//! one JSON line per item, in item order.
//!
//! ```text
//! {"id":12,"output":"Livraison rapide et produit conforme."}
//! {"id":13,"output":null}
//! ```
//!
//! `output` is a string (text or label), an object `{field: text}`
//! (extraction) or `null` (a constrained answer the model could not give,
//! see [`crate::prompt::read_answer`]). [`check`] refuses answers whose
//! ids, count, shape or size do not fit the fragment: the publisher and the
//! verifiers run it before anything else.

use crate::{Error, Result, request::OutputSpec};
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Upper bound of an answer, in characters per token of the length limit
/// (a token is a few characters; this only stops absurd answers).
const CHARS_PER_TOKEN: usize = 32;

/// The answer to one item.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Answer {
    pub id: u64,
    pub output: Value,
}

/// The answers as published.
pub fn to_bytes(answers: &[Answer]) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    for answer in answers {
        serde_json::to_writer(&mut bytes, answer)?;
        bytes.push(b'\n');
    }
    Ok(bytes)
}

/// The answers in `bytes` when they are those of items
/// `first_id..first_id + count`, each a plain string, object or null (the
/// check of a node that does not know the job's output kind).
pub fn parse(bytes: &[u8], first_id: u64, count: u64) -> Result<Vec<Answer>> {
    let mut answers = Vec::with_capacity(count as usize);
    for line in bytes.split(|&b| b == b'\n').filter(|line| !line.is_empty()) {
        if answers.len() as u64 >= count {
            return Err(Error::Format("more answers than items".into()));
        }
        let answer: Answer = serde_json::from_slice(line)?;
        let expected = first_id + answers.len() as u64;
        if answer.id != expected {
            return Err(Error::Format(format!(
                "answer {} where {expected} was expected",
                answer.id
            )));
        }
        if !matches!(
            answer.output,
            Value::String(_) | Value::Object(_) | Value::Null
        ) {
            return Err(Error::Format(format!("answer {} has no output", answer.id)));
        }
        answers.push(answer);
    }
    if answers.len() as u64 != count {
        return Err(Error::Format(format!(
            "{} answers for {count} items",
            answers.len()
        )));
    }
    Ok(answers)
}

/// [`parse`], then the shape of every output for `output` and its size
/// for `max_tokens`.
pub fn check(
    bytes: &[u8],
    first_id: u64,
    count: u64,
    output: &OutputSpec,
    max_tokens: u32,
) -> Result<Vec<Answer>> {
    let answers = parse(bytes, first_id, count)?;
    let max_chars = max_tokens as usize * CHARS_PER_TOKEN;
    for answer in &answers {
        if !fits(&answer.output, output, max_chars) {
            return Err(Error::Format(format!(
                "answer {} does not fit the requested output",
                answer.id
            )));
        }
    }
    Ok(answers)
}

fn fits(value: &Value, output: &OutputSpec, max_chars: usize) -> bool {
    let short = |text: &str| text.chars().count() <= max_chars;
    match (output, value) {
        (_, Value::Null) => !matches!(output, OutputSpec::Text),
        (OutputSpec::Text, Value::String(text)) => short(text),
        (OutputSpec::Label { labels }, Value::String(label)) => labels.contains(label),
        (OutputSpec::Fields { fields }, Value::Object(object)) => {
            object.len() == fields.len()
                && fields
                    .iter()
                    .all(|field| object.get(field).and_then(Value::as_str).is_some_and(short))
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn answers(outputs: &[Value]) -> Vec<u8> {
        let list: Vec<Answer> = outputs
            .iter()
            .enumerate()
            .map(|(index, output)| Answer {
                id: 10 + index as u64,
                output: output.clone(),
            })
            .collect();
        to_bytes(&list).unwrap()
    }

    #[test]
    fn answers_round_trip() {
        let bytes = answers(&[json!("a"), json!("b")]);
        let parsed = check(&bytes, 10, 2, &OutputSpec::Text, 16).unwrap();
        assert_eq!(
            parsed[1],
            Answer {
                id: 11,
                output: json!("b")
            }
        );
    }

    #[test]
    fn ids_and_counts_must_be_those_of_the_fragment() {
        let bytes = answers(&[json!("a"), json!("b")]);
        assert!(parse(&bytes, 11, 2).is_err());
        assert!(parse(&bytes, 10, 3).is_err());
        assert!(parse(&bytes, 10, 1).is_err());
        assert!(parse(&answers(&[json!(3)]), 10, 1).is_err());
    }

    #[test]
    fn outputs_must_fit_the_requested_kind() {
        let labels = OutputSpec::Label {
            labels: vec!["oui".into(), "non".into()],
        };
        assert!(check(&answers(&[json!("oui"), Value::Null]), 10, 2, &labels, 16).is_ok());
        assert!(check(&answers(&[json!("peut-être")]), 10, 1, &labels, 16).is_err());
        assert!(check(&answers(&[Value::Null]), 10, 1, &OutputSpec::Text, 16).is_err());
        let long = "x".repeat(16 * CHARS_PER_TOKEN + 1);
        assert!(check(&answers(&[json!(long)]), 10, 1, &OutputSpec::Text, 16).is_err());
        let fields = OutputSpec::Fields {
            fields: vec!["nom".into()],
        };
        assert!(check(&answers(&[json!({"nom": "A"})]), 10, 1, &fields, 16).is_ok());
        assert!(
            check(
                &answers(&[json!({"nom": "A", "x": "B"})]),
                10,
                1,
                &fields,
                16
            )
            .is_err()
        );
        assert!(check(&answers(&[json!({"nom": 1})]), 10, 1, &fields, 16).is_err());
    }
}
