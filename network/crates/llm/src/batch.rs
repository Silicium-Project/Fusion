//! The canonical input of a job: `silicium-llm-batch/1`, JSON Lines.
//!
//! ```text
//! {"format":"silicium-llm-batch/1","model":"qwen2.5-1.5b-instruct","item_count":2,"task":"summarize","instruction":"…","output":{"kind":"text"},"max_tokens":256,"source":{"name":"avis.csv"}}
//! {"id":0,"text":"…"}
//! {"id":1,"text":"…"}
//! ```
//!
//! The publisher builds it from the request ([`build`]) and shares it with
//! the workers. A fragment is a byte range of whole item lines
//! ([`plan_fragments`]); the header travels with every fragment since the
//! whole file is shared, and a worker reads its items with [`read_range`].

use crate::{
    Error, Result,
    request::{OutputSpec, Request, Source},
};
use serde::{Deserialize, Serialize};

/// Format identifier of a batch.
pub const FORMAT: &str = "silicium-llm-batch/1";

/// First line of a batch.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BatchHeader {
    pub format: String,
    /// Identifier of the model the answers must come from.
    pub model: String,
    pub item_count: u64,
    pub task: String,
    pub instruction: String,
    pub output: OutputSpec,
    pub max_tokens: u32,
    #[serde(default)]
    pub source: Source,
}

/// One item of a batch.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Item {
    pub id: u64,
    pub text: String,
}

/// A fragment: bytes `start..end` of the batch, items
/// `first_id..first_id + count`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FragmentPlan {
    pub start: u64,
    pub end: u64,
    pub first_id: u64,
    pub count: u64,
}

/// The batch of `request` for `model`.
pub fn build(request: &Request, model: &str) -> Result<Vec<u8>> {
    let header = BatchHeader {
        format: FORMAT.into(),
        model: model.into(),
        item_count: request.items.len() as u64,
        task: request.task.clone(),
        instruction: request.instruction.clone(),
        output: request.output.clone(),
        max_tokens: request.max_tokens,
        source: request.source.clone(),
    };
    let mut bytes = serde_json::to_vec(&header)?;
    bytes.push(b'\n');
    for (id, text) in request.items.iter().enumerate() {
        let item = Item {
            id: id as u64,
            text: text.clone(),
        };
        serde_json::to_writer(&mut bytes, &item)?;
        bytes.push(b'\n');
    }
    Ok(bytes)
}

/// The header of a batch and the offset of its first item line.
pub fn read_header(bytes: &[u8]) -> Result<(BatchHeader, usize)> {
    let end = bytes
        .iter()
        .position(|&b| b == b'\n')
        .ok_or_else(|| Error::Format("batch without header line".into()))?;
    let header: BatchHeader = serde_json::from_slice(&bytes[..end])?;
    if header.format != FORMAT {
        return Err(Error::Format(format!(
            "unknown batch format {}",
            header.format
        )));
    }
    Ok((header, end + 1))
}

/// Splits the items of `bytes` into fragments of about `per_fragment`
/// items, at most `max_fragments`; `requested` (the user's count) wins.
/// Items are spread evenly.
pub fn plan_fragments(
    bytes: &[u8],
    per_fragment: usize,
    max_fragments: usize,
    requested: Option<usize>,
) -> Result<Vec<FragmentPlan>> {
    let (header, body) = read_header(bytes)?;
    let starts = line_starts(bytes, body);
    let total = starts.len();
    if total as u64 != header.item_count || total == 0 {
        return Err(Error::Format(format!(
            "batch has {total} item lines, header says {}",
            header.item_count
        )));
    }
    let count = match requested {
        Some(count) => count,
        None => total
            .div_ceil(per_fragment.max(1))
            .min(max_fragments.max(1)),
    }
    .clamp(1, total);
    Ok((0..count)
        .map(|index| {
            let first = index * total / count;
            let last = (index + 1) * total / count;
            let end = starts.get(last).copied().unwrap_or(bytes.len());
            FragmentPlan {
                start: starts[first] as u64,
                end: end as u64,
                first_id: first as u64,
                count: (last - first) as u64,
            }
        })
        .collect())
}

/// The items of `bytes[start..end]`: whole lines with consecutive ids.
pub fn read_range(bytes: &[u8], start: u64, end: u64) -> Result<Vec<Item>> {
    let (_, body) = read_header(bytes)?;
    let (start, end) = (start as usize, end as usize);
    if start < body || end > bytes.len() || start > end {
        return Err(Error::Format("item range outside the batch".into()));
    }
    if (start > body && bytes[start - 1] != b'\n') || (end < bytes.len() && bytes[end - 1] != b'\n')
    {
        return Err(Error::Format("item range does not hold whole lines".into()));
    }
    let mut items = Vec::new();
    for line in bytes[start..end].split(|&b| b == b'\n') {
        if line.is_empty() {
            continue;
        }
        let item: Item = serde_json::from_slice(line)?;
        if let Some(previous) = items.last().map(|item: &Item| item.id)
            && item.id != previous + 1
        {
            return Err(Error::Format("item ids are not consecutive".into()));
        }
        items.push(item);
    }
    Ok(items)
}

/// Every item of a batch.
pub fn read_all(bytes: &[u8]) -> Result<(BatchHeader, Vec<Item>)> {
    let (header, body) = read_header(bytes)?;
    let items = read_range(bytes, body as u64, bytes.len() as u64)?;
    if items.len() as u64 != header.item_count {
        return Err(Error::Format("item count differs from the header".into()));
    }
    Ok((header, items))
}

fn line_starts(bytes: &[u8], body: usize) -> Vec<usize> {
    let mut starts = Vec::new();
    let mut position = body;
    while position < bytes.len() {
        let end = bytes[position..]
            .iter()
            .position(|&b| b == b'\n')
            .map_or(bytes.len(), |offset| position + offset + 1);
        if end - position > 1 {
            starts.push(position);
        }
        position = end;
    }
    starts
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::request::DEFAULT_MAX_TOKENS;

    fn request(count: usize) -> Request {
        Request {
            task: "free".into(),
            instruction: "Traduis en anglais.".into(),
            output: OutputSpec::Text,
            max_tokens: DEFAULT_MAX_TOKENS,
            source: Source::default(),
            items: (0..count).map(|index| format!("texte {index}")).collect(),
        }
    }

    #[test]
    fn a_batch_round_trips() {
        let bytes = build(&request(3), "m").unwrap();
        let (header, items) = read_all(&bytes).unwrap();
        assert_eq!(header.model, "m");
        assert_eq!(header.item_count, 3);
        assert_eq!(
            items[2],
            Item {
                id: 2,
                text: "texte 2".into()
            }
        );
        assert_eq!(build(&request(3), "m").unwrap(), bytes, "canonical");
    }

    #[test]
    fn fragments_hold_whole_items_spread_evenly() {
        let bytes = build(&request(10), "m").unwrap();
        let plans = plan_fragments(&bytes, 4, 32, None).unwrap();
        assert_eq!(
            plans.iter().map(|plan| plan.count).collect::<Vec<_>>(),
            [3, 3, 4]
        );
        let mut next = 0;
        for plan in &plans {
            let items = read_range(&bytes, plan.start, plan.end).unwrap();
            assert_eq!(items.len() as u64, plan.count);
            assert_eq!(items[0].id, next);
            assert_eq!(plan.first_id, next);
            next += plan.count;
        }
        assert_eq!(next, 10);
        assert_eq!(plan_fragments(&bytes, 1, 4, None).unwrap().len(), 4, "max");
        assert_eq!(
            plan_fragments(&bytes, 4, 32, Some(50)).unwrap().len(),
            10,
            "at most one per item"
        );
    }

    #[test]
    fn bad_ranges_are_refused() {
        let bytes = build(&request(3), "m").unwrap();
        let (_, body) = read_header(&bytes).unwrap();
        assert!(read_range(&bytes, 0, bytes.len() as u64).is_err(), "header");
        assert!(read_range(&bytes, body as u64 + 1, bytes.len() as u64).is_err());
        assert!(read_range(&bytes, body as u64, bytes.len() as u64 + 1).is_err());
        assert!(read_header(b"{\"format\":\"x\"}\n").is_err());
    }
}
