//! Word files (`.docx`): the text of `word/document.xml`. A `.docx` has no
//! fixed pages, but Word records where pages ended when the file was last
//! displayed (`w:lastRenderedPageBreak`) and where the author forced one
//! (`w:br w:type="page"`): when present they number the pages, so that a
//! search result can say "page 12" as for a PDF.
//!
//! Paragraphs in a heading style (`Heading 1`, `Titre 2`, `Überschrift 3`,
//! `Title`) are written as Markdown headings (`## …`), so that passages
//! follow the structure of the document (see [`crate::passages`]).

use super::{Page, SkipReason};
use quick_xml::{Reader, events::Event};
use std::io::{Cursor, Read};

/// Largest `word/document.xml` read.
const MAX_XML_BYTES: u64 = 64 * 1024 * 1024;

/// Pages of a Word file.
pub(super) fn pages(bytes: &[u8]) -> Result<Vec<Page>, SkipReason> {
    let xml = document_xml(bytes)?;
    let (texts, breaks_seen) = parse(&xml).map_err(|_| SkipReason::Unreadable)?;
    if !breaks_seen {
        let text = texts.concat();
        return Ok(vec![Page { number: None, text }]);
    }
    Ok(texts
        .into_iter()
        .enumerate()
        .map(|(index, text)| Page {
            number: u32::try_from(index + 1).ok(),
            text,
        })
        .collect())
}

/// The main part of the document, as text.
fn document_xml(bytes: &[u8]) -> Result<String, SkipReason> {
    let mut archive =
        zip::ZipArchive::new(Cursor::new(bytes)).map_err(|_| SkipReason::Unreadable)?;
    let entry = archive
        .by_name("word/document.xml")
        .map_err(|_| SkipReason::Unreadable)?;
    if entry.size() > MAX_XML_BYTES {
        return Err(SkipReason::TooLarge);
    }
    let mut xml = String::new();
    entry
        .take(MAX_XML_BYTES + 1)
        .read_to_string(&mut xml)
        .map_err(|_| SkipReason::Unreadable)?;
    if xml.len() as u64 > MAX_XML_BYTES {
        return Err(SkipReason::TooLarge);
    }
    Ok(xml)
}

/// Text of each page, and whether any page break was recorded.
fn parse(xml: &str) -> Result<(Vec<String>, bool), quick_xml::Error> {
    let mut reader = Reader::from_str(xml);
    let mut pages = vec![String::new()];
    let mut in_text = false;
    let mut breaks_seen = false;
    // Start of the current paragraph (page, byte) and its heading level.
    let mut paragraph = (0, 0);
    let mut heading_level: Option<usize> = None;
    loop {
        match reader.read_event()? {
            Event::Start(element) if element.local_name().as_ref() == "t" => in_text = true,
            Event::Start(element) if element.local_name().as_ref() == "p" => {
                paragraph = (pages.len() - 1, current(&mut pages).len());
                heading_level = None;
            }
            Event::End(element) => match element.local_name().as_ref() {
                "t" => in_text = false,
                "p" => {
                    if let Some(level) = heading_level.take()
                        && paragraph.0 == pages.len() - 1
                    {
                        let page = current(&mut pages);
                        if page[paragraph.1..].trim().is_empty() {
                            // An empty heading paragraph: nothing to mark.
                        } else {
                            page.insert_str(paragraph.1, &format!("{} ", "#".repeat(level)));
                        }
                    }
                    current(&mut pages).push('\n');
                }
                _ => {}
            },
            Event::Empty(element) if element.local_name().as_ref() == "pStyle" => {
                heading_level = style_heading_level(&element);
            }
            Event::Empty(element) => match element.local_name().as_ref() {
                "tab" => current(&mut pages).push(' '),
                "lastRenderedPageBreak" => {
                    breaks_seen = true;
                    new_page(&mut pages);
                }
                "br" if is_page_break(&element) => {
                    breaks_seen = true;
                    new_page(&mut pages);
                }
                "br" | "cr" => current(&mut pages).push('\n'),
                _ => {}
            },
            Event::Text(text) if in_text => current(&mut pages).push_str(&text),
            Event::GeneralRef(reference) if in_text => {
                if let Some(resolved) = resolve_reference(&reference) {
                    current(&mut pages).push_str(&resolved);
                }
            }
            Event::Eof => break,
            _ => {}
        }
    }
    Ok((pages, breaks_seen))
}

/// Starts a page, unless the current one has no text yet: Word records a
/// forced break and the rendered break that follows it, which is one page
/// end, not two.
fn new_page(pages: &mut Vec<String>) {
    if pages.last().is_some_and(|page| !page.trim().is_empty()) {
        pages.push(String::new());
    }
}

fn current(pages: &mut [String]) -> &mut String {
    pages.last_mut().expect("there is always a page")
}

/// Heading level of a paragraph style (`<w:pStyle w:val="Heading2"/>`):
/// the style identifiers Word writes in English, French and German, and
/// `Title`, which is level 1.
fn style_heading_level(element: &quick_xml::events::BytesStart<'_>) -> Option<usize> {
    let attribute = element
        .attributes()
        .flatten()
        .find(|attribute| attribute.key.local_name().as_ref() == "val")?;
    let value = attribute.value.to_lowercase().replace(' ', "");
    if matches!(value.as_str(), "title" | "titre" | "titel") {
        return Some(1);
    }
    let level = ["heading", "titre", "berschrift"]
        .iter()
        .find_map(|prefix| value.find(prefix).map(|at| &value[at + prefix.len()..]))?;
    level
        .parse::<usize>()
        .ok()
        .filter(|level| (1..=6).contains(level))
}

/// True for `<w:br w:type="page"/>`.
fn is_page_break(element: &quick_xml::events::BytesStart<'_>) -> bool {
    element
        .attributes()
        .flatten()
        .any(|attribute| attribute.key.local_name().as_ref() == "type" && attribute.value == "page")
}

/// Text of an entity or character reference (`&amp;`, `&#233;`, `&#xE9;`).
fn resolve_reference(reference: &str) -> Option<String> {
    if let Some(code) = reference.strip_prefix('#') {
        let value = match code.strip_prefix(['x', 'X']) {
            Some(hex) => u32::from_str_radix(hex, 16).ok()?,
            None => code.parse().ok()?,
        };
        return char::from_u32(value).map(String::from);
    }
    quick_xml::escape::resolve_predefined_entity(reference).map(str::to_string)
}
