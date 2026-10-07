//! Text and Markdown files: UTF-8 (with or without BOM), or Windows-1252
//! for files saved by older Windows editors.

use super::Page;

/// The single page of a text file.
pub(super) fn page(bytes: &[u8]) -> Page {
    let bytes = bytes.strip_prefix(b"\xEF\xBB\xBF").unwrap_or(bytes);
    let text = match std::str::from_utf8(bytes) {
        Ok(text) => text.to_string(),
        Err(_) => encoding_rs::WINDOWS_1252.decode(bytes).0.into_owned(),
    };
    Page { number: None, text }
}
