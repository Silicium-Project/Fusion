//! Formats of the Hugging Face workload.
//!
//! - **Request** (`silicium-hf-request/1`, from the BackEnd): the task, the
//!   model manifest, the parameters and the items (each one the `inputs` of
//!   the task's Hub schema; binary inputs as `{"$bytes": "<base64>"}`).
//! - **Batch** (shared with the workers): a header line (task, manifest,
//!   parameters, item count), then one line per item `{"id", "inputs"}`. A
//!   fragment is a byte range of whole item lines.
//! - **Answers** (a fragment's result): one line per item `{"id", "output"}`.

use super::manifest::Manifest;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

pub(crate) const REQUEST_FORMAT: &str = "silicium-hf-request/1";
pub(crate) const BATCH_FORMAT: &str = "silicium-hf-batch/1";
pub(crate) const RESULT_FORMAT: &str = "silicium-hf-result/1";

/// Items of a request.
pub(crate) const MAX_ITEMS: usize = 20_000;
/// One item, as JSON (an image or a sound in base64).
pub(crate) const MAX_ITEM_BYTES: usize = 8 << 20;
/// The parameters, as JSON.
const MAX_PARAMETERS_BYTES: usize = 64 << 10;
/// One output, as JSON.
pub(crate) const MAX_OUTPUT_BYTES: usize = 1 << 20;

#[derive(Debug, Deserialize)]
struct RawRequest {
    format: String,
    task: String,
    model: Manifest,
    #[serde(default)]
    parameters: Option<Value>,
    items: Vec<Value>,
}

/// The header line of a batch.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct Header {
    pub(crate) format: String,
    pub(crate) task: String,
    pub(crate) model: Manifest,
    pub(crate) parameters: Map<String, Value>,
    pub(crate) item_count: u64,
}

/// An item of a batch.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct Item {
    pub(crate) id: u64,
    pub(crate) inputs: Value,
}

/// An answer of a fragment.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub(crate) struct Answer {
    pub(crate) id: u64,
    pub(crate) output: Value,
}

/// Turns a request into the canonical batch, after checking it is for
/// `task` with the model `key`. The error is a message for the user.
pub(crate) fn build(request: &[u8], task: &str, key: &str) -> Result<Vec<u8>, String> {
    let raw: RawRequest = serde_json::from_slice(request)
        .map_err(|_| "La demande n'a pas pu être lue.".to_string())?;
    if raw.format != REQUEST_FORMAT {
        return Err("Format de demande inconnu.".into());
    }
    if raw.task != task || raw.model.task != task || raw.model.key != key {
        return Err("La demande ne correspond pas au modèle choisi.".into());
    }
    raw.model
        .check()
        .map_err(|err| format!("Le modèle a été refusé : {err}."))?;
    if raw.items.is_empty() {
        return Err("La demande ne contient aucun élément.".into());
    }
    if raw.items.len() > MAX_ITEMS {
        return Err(format!("La demande dépasse {MAX_ITEMS} éléments."));
    }
    let parameters = match raw.parameters {
        None | Some(Value::Null) => Map::new(),
        Some(Value::Object(map)) => map,
        Some(_) => return Err("Les paramètres doivent être un objet.".into()),
    };
    if serde_json::to_vec(&parameters).map_or(true, |p| p.len() > MAX_PARAMETERS_BYTES) {
        return Err("Les paramètres sont trop gros.".into());
    }
    let header = Header {
        format: BATCH_FORMAT.into(),
        task: task.into(),
        model: raw.model,
        parameters,
        item_count: raw.items.len() as u64,
    };
    let mut bytes = serde_json::to_vec(&header).map_err(|err| err.to_string())?;
    bytes.push(b'\n');
    for (id, inputs) in raw.items.into_iter().enumerate() {
        if inputs.is_null() {
            return Err(format!("L'élément {} est vide.", id + 1));
        }
        let line = serde_json::to_vec(&Item {
            id: id as u64,
            inputs,
        })
        .map_err(|err| err.to_string())?;
        if line.len() > MAX_ITEM_BYTES {
            return Err(format!(
                "L'élément {} est trop gros (8 Mo au plus).",
                id + 1
            ));
        }
        bytes.extend_from_slice(&line);
        bytes.push(b'\n');
    }
    Ok(bytes)
}

/// The header of a batch and where its items start.
pub(crate) fn read_header(bytes: &[u8]) -> Result<(Header, usize), String> {
    let end = bytes
        .iter()
        .position(|&b| b == b'\n')
        .ok_or("batch without header line")?;
    let header: Header = serde_json::from_slice(&bytes[..end]).map_err(|err| err.to_string())?;
    if header.format != BATCH_FORMAT {
        return Err(format!("unknown batch format {}", header.format));
    }
    Ok((header, end + 1))
}

/// Reads only the header line of the batch file at `path`.
pub(crate) fn read_header_file(path: &std::path::Path) -> Result<Header, String> {
    use std::io::{BufRead, BufReader, Read};
    let file = std::fs::File::open(path).map_err(|err| err.to_string())?;
    // A header holds a manifest: well below this bound.
    let mut reader = BufReader::new(file.take(4 << 20));
    let mut line = Vec::new();
    reader
        .read_until(b'\n', &mut line)
        .map_err(|err| err.to_string())?;
    if line.last() != Some(&b'\n') {
        return Err("batch without header line".into());
    }
    read_header(&line).map(|(header, _)| header)
}

/// A fragment: the byte range of its item lines and its first item.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Plan {
    pub(crate) start: u64,
    pub(crate) end: u64,
    pub(crate) first_id: u64,
    pub(crate) count: u64,
}

/// Splits the items in fragments of `per_fragment` items (more per fragment
/// when there would be more than `max_fragments`, fewer when `requested`).
pub(crate) fn plan(
    bytes: &[u8],
    per_fragment: usize,
    max_fragments: usize,
    requested: Option<usize>,
) -> Result<Vec<Plan>, String> {
    let (header, body) = read_header(bytes)?;
    let starts = line_starts(bytes, body);
    let total = starts.len();
    if total == 0 || total as u64 != header.item_count {
        return Err(format!(
            "batch has {total} item lines, header says {}",
            header.item_count
        ));
    }
    let mut fragments = total.div_ceil(per_fragment.max(1));
    if let Some(requested) = requested.filter(|n| *n > 0) {
        fragments = requested;
    }
    let fragments = fragments.clamp(1, max_fragments.max(1)).min(total);
    let per = total.div_ceil(fragments);
    let mut plans = Vec::new();
    let mut first = 0;
    while first < total {
        let last = (first + per).min(total);
        let end = starts.get(last).copied().unwrap_or(bytes.len());
        plans.push(Plan {
            start: starts[first] as u64,
            end: end as u64,
            first_id: first as u64,
            count: (last - first) as u64,
        });
        first = last;
    }
    Ok(plans)
}

fn line_starts(bytes: &[u8], body: usize) -> Vec<usize> {
    let mut starts = Vec::new();
    let mut position = body;
    while position < bytes.len() {
        starts.push(position);
        match bytes[position..].iter().position(|&b| b == b'\n') {
            Some(offset) => position += offset + 1,
            None => break,
        }
    }
    starts
}

/// The items of the byte range `start..end` (whole lines, ids in order).
pub(crate) fn read_range(bytes: &[u8], start: u64, end: u64) -> Result<Vec<Item>, String> {
    let (_, body) = read_header(bytes)?;
    let (start, end) = (start as usize, end as usize);
    if start < body || end > bytes.len() || start >= end {
        return Err("item range outside the batch".into());
    }
    if bytes[start - 1] != b'\n' || (end < bytes.len() && bytes[end - 1] != b'\n') {
        return Err("item range does not hold whole lines".into());
    }
    let mut items: Vec<Item> = Vec::new();
    for line in bytes[start..end].split(|&b| b == b'\n') {
        if line.is_empty() {
            continue;
        }
        let item: Item = serde_json::from_slice(line).map_err(|err| err.to_string())?;
        if let Some(previous) = items.last()
            && item.id != previous.id + 1
        {
            return Err("item ids out of order".into());
        }
        items.push(item);
    }
    Ok(items)
}

/// Answers as published (one JSON line each).
pub(crate) fn answers_to_bytes(answers: &[Answer]) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    for answer in answers {
        let line = serde_json::to_vec(answer).map_err(|err| err.to_string())?;
        if line.len() > MAX_OUTPUT_BYTES {
            return Err(format!("output of item {} too large", answer.id));
        }
        bytes.extend_from_slice(&line);
        bytes.push(b'\n');
    }
    Ok(bytes)
}

/// Reads published answers: exactly `count` answers, ids `first..`, each
/// with an output.
pub(crate) fn parse_answers(bytes: &[u8], first: u64, count: u64) -> Result<Vec<Answer>, String> {
    let mut answers = Vec::new();
    for line in bytes.split(|&b| b == b'\n') {
        if line.is_empty() {
            continue;
        }
        if line.len() > MAX_OUTPUT_BYTES {
            return Err("answer too large".into());
        }
        let answer: Answer = serde_json::from_slice(line).map_err(|err| err.to_string())?;
        if answer.id != first + answers.len() as u64 || answer.output.is_null() {
            return Err(format!("unexpected answer {}", answer.id));
        }
        answers.push(answer);
    }
    if answers.len() as u64 != count {
        return Err(format!("{} answers, expected {count}", answers.len()));
    }
    Ok(answers)
}
