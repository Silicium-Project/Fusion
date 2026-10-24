//! Submitted files to plain text pages.
//!
//! The person searching their documents drops PDF, Word (`.docx`), text or
//! Markdown files, or a ZIP of them. [`extract`] turns each file into a
//! [`Document`] (its pages of text) and lists the files it had to skip with
//! the reason (a scanned PDF has no text, a `.pptx` is not supported...), so
//! that the site can tell the user instead of failing silently.
//!
//! The input comes from users of the site: every size is bounded
//! ([`Limits`]), archives are not recursed into, and a parser panic on a
//! malformed file skips that file instead of crashing the caller.

mod archive;
mod docx;
mod pdf;
mod text;

use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

/// One submitted document, as pages of text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Document {
    /// File name (path inside the archive for a ZIP entry).
    pub name: String,
    pub pages: Vec<Page>,
}

/// A page of a document. Formats without pages (text, Markdown, Word
/// without page break) have a single page numbered `None`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Page {
    /// Page number, starting at 1.
    pub number: Option<u32>,
    pub text: String,
}

/// Why a submitted file was not used.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SkipReason {
    /// No text could be read (a scanned PDF is an image).
    NoText,
    /// Not a supported format.
    UnsupportedFormat,
    /// The file is damaged or protected.
    Unreadable,
    /// The file or the archive is over the limits.
    TooLarge,
}

/// A submitted file that was not used.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SkippedDocument {
    pub name: String,
    pub reason: SkipReason,
}

/// Documents read from a submission.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Extraction {
    pub documents: Vec<Document>,
    pub skipped: Vec<SkippedDocument>,
}

/// Bounds on what a submission may contain.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Limits {
    /// Files read from one archive.
    pub max_files: usize,
    /// Size of one file (uncompressed).
    pub max_file_bytes: u64,
    /// Total uncompressed size of an archive.
    pub max_total_bytes: u64,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            max_files: 1_000,
            max_file_bytes: 64 * 1024 * 1024,
            max_total_bytes: 256 * 1024 * 1024,
        }
    }
}

/// Supported kinds of file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Kind {
    Pdf,
    Docx,
    Text,
    Zip,
    Unsupported,
}

/// Reads the submission at `path`: one document, or a ZIP of documents (a
/// ZIP may weigh up to the total limit: its entries are bounded one by one).
pub fn extract(path: &Path, limits: &Limits) -> Result<Extraction> {
    let size = std::fs::metadata(path)?.len();
    let is_archive = path
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("zip"));
    let limit = if is_archive {
        limits.max_total_bytes
    } else {
        limits.max_file_bytes
    };
    if size > limit {
        return Err(Error::Input(
            "Le fichier envoyé dépasse la taille maximale.".to_string(),
        ));
    }
    let bytes = std::fs::read(path)?;
    let name = path
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "document".to_string());
    Ok(extract_bytes(&name, &bytes, limits))
}

/// Reads one submitted file given as bytes (see [`extract`]).
pub fn extract_bytes(name: &str, bytes: &[u8], limits: &Limits) -> Extraction {
    let mut extraction = Extraction::default();
    match kind_of(name, bytes) {
        Kind::Zip => archive::read(bytes, limits, &mut extraction),
        _ => read_single(name, bytes, &mut extraction),
    }
    extraction
}

/// Reads one non-archive file into `out`.
fn read_single(name: &str, bytes: &[u8], out: &mut Extraction) {
    let pages = match kind_of(name, bytes) {
        Kind::Pdf => guarded(|| pdf::pages(bytes)),
        Kind::Docx => guarded(|| docx::pages(bytes)),
        Kind::Text => Ok(vec![text::page(bytes)]),
        Kind::Zip | Kind::Unsupported => Err(SkipReason::UnsupportedFormat),
    };
    let pages = pages.map(|pages| {
        pages
            .into_iter()
            .map(|page| Page {
                number: page.number,
                text: normalize_whitespace(&page.text),
            })
            .filter(|page| !page.text.is_empty())
            .collect::<Vec<_>>()
    });
    match pages {
        Ok(pages) if !pages.is_empty() => out.documents.push(Document {
            name: name.to_string(),
            pages,
        }),
        Ok(_) => out.skip(name, SkipReason::NoText),
        Err(reason) => out.skip(name, reason),
    }
}

impl Extraction {
    fn skip(&mut self, name: &str, reason: SkipReason) {
        self.skipped.push(SkippedDocument {
            name: name.to_string(),
            reason,
        });
    }
}

/// Runs a parser, turning a panic on a malformed file into
/// [`SkipReason::Unreadable`].
fn guarded(
    parse: impl FnOnce() -> std::result::Result<Vec<Page>, SkipReason>,
) -> std::result::Result<Vec<Page>, SkipReason> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(parse))
        .unwrap_or(Err(SkipReason::Unreadable))
}

/// Kind of a file, from its extension, confirmed by its first bytes.
fn kind_of(name: &str, bytes: &[u8]) -> Kind {
    let extension = name
        .rsplit_once('.')
        .map(|(_, extension)| extension.to_ascii_lowercase())
        .unwrap_or_default();
    let is_zip = bytes.starts_with(b"PK\x03\x04") || bytes.starts_with(b"PK\x05\x06");
    match extension.as_str() {
        "pdf" if bytes.starts_with(b"%PDF") => Kind::Pdf,
        "docx" if is_zip => Kind::Docx,
        "zip" if is_zip => Kind::Zip,
        "txt" | "md" | "markdown" | "text" | "csv" if !is_zip => Kind::Text,
        _ => Kind::Unsupported,
    }
}

/// Collapses runs of spaces and blank lines, keeps paragraph breaks, and
/// removes control characters (PDF extraction leaves many).
pub(crate) fn normalize_whitespace(text: &str) -> String {
    let mut lines: Vec<String> = Vec::new();
    let mut blank = false;
    for line in text.lines() {
        let words: Vec<&str> = line
            .split(|c: char| c.is_whitespace() || c.is_control())
            .filter(|word| !word.is_empty())
            .collect();
        if words.is_empty() {
            blank = !lines.is_empty();
            continue;
        }
        if blank {
            lines.push(String::new());
            blank = false;
        }
        lines.push(words.join(" "));
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests;
