//! The corpus: the canonical input of a document-search job.
//!
//! The publisher turns the submitted files into one JSON Lines file
//! (format `silicium-corpus/2`), shared with the workers by hash:
//!
//! ```text
//! {"format":"silicium-corpus/2","passage_count":3,"documents":[...],"skipped":[...]}
//! {"id":0,"doc":0,"page":1,"section":"Article 6 - Préavis","text":"…"}
//! {"id":1,"doc":0,"page":2,"section":"Article 6 - Préavis","text":"…"}
//! {"id":2,"doc":1,"page":null,"text":"…"}
//! ```
//!
//! Format 2 adds the `section` of a passage (the headings above it). The
//! model reads the document title, the section and the text
//! ([`PassageRecord::embedding_input`]). Format 1 corpora (no section) are
//! still read.
//!
//! The first line is the [`CorpusHeader`]; every other line is a
//! [`PassageRecord`], ids counting from 0 in order. A fragment of the job
//! is a byte range of whole passage lines ([`plan_fragments`]), so a worker
//! reads exactly its passages ([`read_range`]) and the ids tell where its
//! vectors go in the final index.

use crate::{
    Error, Result,
    documents::{Extraction, SkipReason, SkippedDocument},
    passages::Chunker,
};
use serde::{Deserialize, Serialize};

/// Identifier of the format written, first field of the header.
pub const FORMAT: &str = "silicium-corpus/2";
/// Formats read.
const READ_FORMATS: &[&str] = &["silicium-corpus/1", FORMAT];

/// First line of a corpus.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CorpusHeader {
    pub format: String,
    pub passage_count: u64,
    pub documents: Vec<DocumentEntry>,
    #[serde(default)]
    pub skipped: Vec<SkippedDocument>,
}

/// A document of the corpus.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DocumentEntry {
    pub name: String,
    pub pages: u32,
    pub passages: u64,
}

/// One passage line.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PassageRecord {
    pub id: u64,
    /// Index in [`CorpusHeader::documents`].
    pub doc: u32,
    pub page: Option<u32>,
    /// Headings above the passage, outermost first (format 2).
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub section: String,
    pub text: String,
}

impl PassageRecord {
    /// The text given to the model for this passage of a corpus whose
    /// documents are `documents` (see [`embedding_text`]). Every node builds
    /// it the same way, so that workers and verifiers embed the same input.
    pub fn embedding_input(&self, documents: &[DocumentEntry]) -> String {
        let title = documents
            .get(self.doc as usize)
            .map(|document| document_title(&document.name))
            .unwrap_or_default();
        embedding_text(&title, &self.section, &self.text)
    }
}

/// The title of a document for the model: its file name without folders
/// nor extension, `-` and `_` read as spaces (`docs/contrat-de-bail.pdf`
/// gives `contrat de bail`).
pub fn document_title(name: &str) -> String {
    let file = name.rsplit(['/', '\\']).next().unwrap_or(name);
    let stem = match file.rsplit_once('.') {
        Some((stem, _)) if !stem.is_empty() => stem,
        _ => file,
    };
    stem.replace(['-', '_'], " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

/// Document title, section and passage text, one per line. A line is left
/// out when empty or when the next one already starts with it (a section
/// that opens with the document title, a passage that opens with its
/// heading), compared without case.
pub fn embedding_text(title: &str, section: &str, text: &str) -> String {
    let parts = [title, section, text];
    let mut lines = Vec::with_capacity(3);
    for (position, part) in parts.iter().enumerate() {
        let repeated = parts[position + 1..]
            .iter()
            .find(|next| !next.is_empty())
            .is_some_and(|next| next.to_lowercase().starts_with(&part.to_lowercase()));
        if !part.is_empty() && !repeated {
            lines.push(*part);
        }
    }
    lines.join("\n")
}

/// The passages of one fragment: a byte range of the corpus file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FragmentPlan {
    pub start: u64,
    pub end: u64,
    pub first_id: u64,
    pub count: u64,
}

/// Builds the corpus of an extraction. Fails with a message for the user
/// when no passage could be made.
pub fn build(extraction: &Extraction, chunker: &Chunker) -> Result<Vec<u8>> {
    let passages = chunker.passages(&extraction.documents);
    if passages.is_empty() {
        return Err(Error::Input(no_text_message(&extraction.skipped)));
    }
    let documents = extraction
        .documents
        .iter()
        .enumerate()
        .map(|(index, document)| DocumentEntry {
            name: document.name.clone(),
            pages: document.pages.len() as u32,
            passages: passages.iter().filter(|p| p.document == index).count() as u64,
        })
        .collect();
    let header = CorpusHeader {
        format: FORMAT.to_string(),
        passage_count: passages.len() as u64,
        documents,
        skipped: extraction.skipped.clone(),
    };
    let mut bytes = json_line(&header)?;
    for (id, passage) in passages.into_iter().enumerate() {
        let record = PassageRecord {
            id: id as u64,
            doc: passage.document as u32,
            page: passage.page,
            section: passage.section,
            text: passage.text,
        };
        bytes.extend(json_line(&record)?);
    }
    Ok(bytes)
}

/// The header of a corpus and the offset of its first passage line.
pub fn read_header(bytes: &[u8]) -> Result<(CorpusHeader, usize)> {
    let end = bytes
        .iter()
        .position(|byte| *byte == b'\n')
        .ok_or_else(|| Error::Format("corpus without header line".into()))?;
    let header: CorpusHeader = serde_json::from_slice(&bytes[..end])
        .map_err(|err| Error::Format(format!("corpus header: {err}")))?;
    if !READ_FORMATS.contains(&header.format.as_str()) {
        return Err(Error::Format(format!(
            "unknown corpus format {}",
            header.format
        )));
    }
    Ok((header, end + 1))
}

/// Splits the passages of a corpus into fragments of about
/// `per_fragment` passages, at most `max_fragments` (or exactly
/// `requested` when given, never more than there are passages).
pub fn plan_fragments(
    bytes: &[u8],
    per_fragment: usize,
    max_fragments: usize,
    requested: Option<usize>,
) -> Result<Vec<FragmentPlan>> {
    let (header, body) = read_header(bytes)?;
    let starts = line_starts(bytes, body);
    let total = starts.len();
    if total as u64 != header.passage_count || total == 0 {
        return Err(Error::Format(format!(
            "corpus has {total} passage lines, header says {}",
            header.passage_count
        )));
    }
    let count = match requested {
        Some(count) => count,
        None => total
            .div_ceil(per_fragment.max(1))
            .min(max_fragments.max(1)),
    }
    .clamp(1, total);
    let mut plans = Vec::with_capacity(count);
    for index in 0..count {
        // Spread the passages evenly: the first `total % count` fragments
        // get one more.
        let first = index * total / count;
        let last = (index + 1) * total / count;
        let end = starts.get(last).copied().unwrap_or(bytes.len());
        plans.push(FragmentPlan {
            start: starts[first] as u64,
            end: end as u64,
            first_id: first as u64,
            count: (last - first) as u64,
        });
    }
    Ok(plans)
}

/// The passages of `bytes[start..end]`, which must be whole lines with
/// consecutive ids.
pub fn read_range(bytes: &[u8], start: u64, end: u64) -> Result<Vec<PassageRecord>> {
    let range = usize::try_from(start).ok().zip(usize::try_from(end).ok());
    let slice = range
        .and_then(|(start, end)| bytes.get(start..end))
        .ok_or_else(|| Error::Format("passage range outside the corpus".into()))?;
    let mut records = Vec::new();
    for line in slice
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
    {
        let record: PassageRecord = serde_json::from_slice(line)
            .map_err(|err| Error::Format(format!("passage line: {err}")))?;
        if let Some(previous) = records.last().map(|r: &PassageRecord| r.id)
            && record.id != previous + 1
        {
            return Err(Error::Format("passage ids are not consecutive".into()));
        }
        records.push(record);
    }
    Ok(records)
}

/// Offsets of the lines starting at or after `from`.
fn line_starts(bytes: &[u8], from: usize) -> Vec<usize> {
    let mut starts = Vec::new();
    let mut position = from;
    while position < bytes.len() {
        starts.push(position);
        match bytes[position..].iter().position(|byte| *byte == b'\n') {
            Some(offset) => position += offset + 1,
            None => break,
        }
    }
    starts
}

fn json_line(value: &impl Serialize) -> Result<Vec<u8>> {
    let mut line = serde_json::to_vec(value).map_err(|err| Error::Format(err.to_string()))?;
    line.push(b'\n');
    Ok(line)
}

/// What to tell the user when nothing could be read.
fn no_text_message(skipped: &[SkippedDocument]) -> String {
    let all = |reason| !skipped.is_empty() && skipped.iter().all(|s| s.reason == reason);
    if skipped.is_empty() {
        "Aucun texte n'a été trouvé dans les documents envoyés.".to_string()
    } else if all(SkipReason::NoText) {
        "Aucun texte n'a pu être lu : les PDF envoyés sont probablement des images scannées."
            .to_string()
    } else if all(SkipReason::UnsupportedFormat) {
        "Aucun document pris en charge : envoie des PDF, des fichiers Word (.docx), texte, Markdown ou un ZIP."
            .to_string()
    } else {
        "Aucun des documents envoyés n'a pu être lu (format non pris en charge, fichier abîmé ou trop gros)."
            .to_string()
    }
}

#[cfg(test)]
pub(crate) mod tests;
