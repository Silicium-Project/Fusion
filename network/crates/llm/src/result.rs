//! The result of a job, assembled by the publisher from the answers of its
//! fragments:
//!
//! | File | Content |
//! | --- | --- |
//! | `answers.jsonl` | `{"id","input","output"}` per item, in order |
//! | `answers.csv` | the same table for a spreadsheet (UTF-8 with BOM, one column per field of an extraction) |
//! | `result.json` | `silicium-llm-result/1`: model, prompt version, instruction, counts; written last, it marks the job done |

use crate::{
    Error, Result,
    answers::{self, Answer},
    batch::{self, BatchHeader, Item},
    model::LlmModel,
    prompt::PROMPT_VERSION,
    request::OutputSpec,
};
use serde_json::{Value, json};

/// Format identifier of `result.json`.
pub const FORMAT: &str = "silicium-llm-result/1";

/// The files of a finished job.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResultFiles {
    pub answers: Vec<u8>,
    pub csv: Vec<u8>,
    pub manifest: Vec<u8>,
}

/// Answers of fragment `index`: the bytes a worker published and the items
/// they answer.
pub struct FragmentAnswers<'a> {
    pub bytes: &'a [u8],
    pub first_id: u64,
    pub count: u64,
}

/// The result of the batch `batch_bytes` from the answers of its fragments,
/// in order.
pub fn assemble(
    batch_bytes: &[u8],
    fragments: &[FragmentAnswers<'_>],
    model: &LlmModel,
) -> Result<ResultFiles> {
    let (header, items) = batch::read_all(batch_bytes)?;
    if header.model != model.id {
        return Err(Error::Format(format!(
            "batch for model {}, not {}",
            header.model, model.id
        )));
    }
    let mut all: Vec<Answer> = Vec::with_capacity(items.len());
    for fragment in fragments {
        if fragment.first_id != all.len() as u64 {
            return Err(Error::Format("fragments do not follow each other".into()));
        }
        all.extend(answers::check(
            fragment.bytes,
            fragment.first_id,
            fragment.count,
            &header.output,
            header.max_tokens,
        )?);
    }
    if all.len() != items.len() {
        return Err(Error::Format(format!(
            "{} answers for {} items",
            all.len(),
            items.len()
        )));
    }
    Ok(ResultFiles {
        answers: answers_jsonl(&items, &all)?,
        csv: answers_csv(&header, &items, &all),
        manifest: manifest(&header, model, &all)?,
    })
}

/// One line `{"id","input","output"}` per item.
pub fn answers_jsonl(items: &[Item], answers: &[Answer]) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    for (item, answer) in items.iter().zip(answers) {
        serde_json::to_writer(
            &mut bytes,
            &json!({"id": item.id, "input": item.text, "output": answer.output}),
        )?;
        bytes.push(b'\n');
    }
    Ok(bytes)
}

fn answers_csv(header: &BatchHeader, items: &[Item], answers: &[Answer]) -> Vec<u8> {
    let mut columns = vec!["id".to_string(), "input".to_string()];
    match &header.output {
        OutputSpec::Fields { fields } => columns.extend(fields.iter().cloned()),
        _ => columns.push("output".into()),
    }
    let mut text = String::from('\u{feff}');
    push_row(&mut text, &columns);
    for (item, answer) in items.iter().zip(answers) {
        let mut row = vec![(item.id + 1).to_string(), item.text.clone()];
        match &header.output {
            OutputSpec::Fields { fields } => row.extend(fields.iter().map(|field| {
                answer
                    .output
                    .get(field)
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string()
            })),
            _ => row.push(answer.output.as_str().unwrap_or_default().to_string()),
        }
        push_row(&mut text, &row);
    }
    text.into_bytes()
}

/// Appends a CSV row (RFC 4180, CRLF). A cell a spreadsheet would read as a
/// formula (`=`, `+`, `@`, `-` followed by a non-space) is prefixed with `'`.
fn push_row(text: &mut String, cells: &[String]) {
    let row: Vec<String> = cells
        .iter()
        .map(|cell| {
            let mut chars = cell.chars();
            let formula = match chars.next() {
                Some('=' | '+' | '@' | '\t' | '\r') => true,
                Some('-') => chars.next().is_some_and(|next| !next.is_whitespace()),
                _ => false,
            };
            let cell = if formula && cell.parse::<f64>().is_err() {
                format!("'{cell}")
            } else {
                cell.clone()
            };
            format!("\"{}\"", cell.replace('"', "\"\""))
        })
        .collect();
    text.push_str(&row.join(","));
    text.push_str("\r\n");
}

fn manifest(header: &BatchHeader, model: &LlmModel, answers: &[Answer]) -> Result<Vec<u8>> {
    let answered = answers
        .iter()
        .filter(|answer| !answer.output.is_null())
        .count();
    Ok(serde_json::to_vec_pretty(&json!({
        "format": FORMAT,
        "model": {
            "id": model.id,
            "repository": model.repository,
            "revision": model.revision,
            "file": model.weights.name,
            "sha256": model.weights.sha256,
            "licence": model.licence,
        },
        "prompt_version": PROMPT_VERSION,
        "task": header.task,
        "instruction": header.instruction,
        "output": header.output,
        "max_tokens": header.max_tokens,
        "source": header.source,
        "item_count": answers.len(),
        "answered": answered,
        "files": {"answers": "answers.jsonl", "table": "answers.csv"},
    }))?)
}

#[cfg(test)]
mod tests;
