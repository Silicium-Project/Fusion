//! PDF files: the text of each page (`pdf-extract`). A scanned PDF has no
//! text layer and yields empty pages; the caller reports it as
//! [`super::SkipReason::NoText`].

use super::{Page, SkipReason};

/// Pages of a PDF, numbered from 1.
pub(super) fn pages(bytes: &[u8]) -> Result<Vec<Page>, SkipReason> {
    let pages =
        pdf_extract::extract_text_from_mem_by_pages(bytes).map_err(|_| SkipReason::Unreadable)?;
    Ok(pages
        .into_iter()
        .enumerate()
        .map(|(index, text)| Page {
            number: u32::try_from(index + 1).ok(),
            text,
        })
        .collect())
}
