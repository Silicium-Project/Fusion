//! Pages to passages: the unit that is embedded, searched and shown to the
//! user.
//!
//! Passages follow the structure of the document instead of cutting it
//! every N words:
//!
//! - a **heading** ([`heading`]: Markdown `#`, Word heading styles, and the
//!   usual numbered headings of contracts, rules and reports, `Article 6 -
//!   Préavis`, `2.3 Garanties`, `CHAPITRE II`) starts a new passage, so an
//!   article or a section is not mixed with the next one;
//! - lines are gathered until [`Chunker::max_words`]; a longer section is
//!   cut in windows overlapping by [`Chunker::overlap_words`];
//! - each passage keeps the **headings above it** ([`Passage::section`],
//!   `Article 6 - Congé et préavis`, up to [`MAX_SECTION_DEPTH`] levels):
//!   they are embedded with the passage (see
//!   [`crate::corpus::PassageRecord::embedding_input`]) and shown with the
//!   result, because a passage alone often does not say what it is about;
//! - passages stay inside a page, so each has the page number of its text.
//!
//! The defaults (150 words, about 220 to 260 tokens with the section) fit
//! the 512-token input of the e5 models with room to spare; shorter
//! passages are more precise to search, the result page shows enough
//! around them. Chunking is deterministic: the same document always gives
//! the same passages.

use crate::documents::Document;

/// Headings kept above a passage.
pub const MAX_SECTION_DEPTH: usize = 3;
/// Longest heading kept, in characters.
const MAX_HEADING_CHARS: usize = 100;
/// A line of more words is not a heading.
const MAX_HEADING_WORDS: usize = 14;
/// A numbered line (`2.3 Garanties`) of more words is a list item, not a heading.
const MAX_NUMBERED_HEADING_WORDS: usize = 8;

/// How pages are cut into passages.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Chunker {
    pub max_words: usize,
    pub overlap_words: usize,
    /// A section is cut only when the last window would keep at least this
    /// many words: a section of up to `max_words + min_words - 1` words
    /// stays one passage instead of leaving a tail of a few words.
    pub min_words: usize,
}

impl Default for Chunker {
    fn default() -> Self {
        Self {
            max_words: 150,
            overlap_words: 30,
            min_words: 25,
        }
    }
}

/// One passage of a document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Passage {
    /// Index of the document in the submission.
    pub document: usize,
    pub page: Option<u32>,
    /// Headings above the passage, outermost first, joined by ` › `.
    pub section: String,
    pub text: String,
}

/// The headings above the current line, as (level, title).
#[derive(Debug, Default)]
struct Outline(Vec<(u8, String)>);

impl Outline {
    fn enter(&mut self, level: u8, title: String) {
        self.0.retain(|(other, _)| *other < level);
        self.0.push((level, title));
    }

    fn section(&self) -> String {
        let skip = self.0.len().saturating_sub(MAX_SECTION_DEPTH);
        self.0[skip..]
            .iter()
            .map(|(_, title)| title.as_str())
            .collect::<Vec<_>>()
            .join(" › ")
    }
}

impl Chunker {
    /// Passages of `documents`, in document then page order.
    pub fn passages(&self, documents: &[Document]) -> Vec<Passage> {
        let mut passages = Vec::new();
        for (index, document) in documents.iter().enumerate() {
            let mut outline = Outline::default();
            for page in &document.pages {
                let mut words: Vec<String> = Vec::new();
                // Words of text since the last heading: headings directly
                // following one another stay in the same passage.
                let mut body_words = 0;
                let mut section = outline.section();
                for line in page.text.lines() {
                    if let Some((level, title)) = heading(line) {
                        if body_words > 0 {
                            self.flush(&mut passages, &mut words, &section, index, page.number);
                        }
                        body_words = 0;
                        words.extend(title.split_whitespace().map(str::to_string));
                        outline.enter(level, title);
                        section = outline.section();
                        continue;
                    }
                    let line_words = line.split_whitespace().map(str::to_string);
                    let before = words.len();
                    words.extend(line_words);
                    body_words += words.len() - before;
                    while words.len() >= self.max_words.max(1) + self.min_words {
                        let window: Vec<String> = words.drain(..self.max_words.max(1)).collect();
                        let kept = self.overlap_words.min(window.len());
                        let mut rest = window[window.len() - kept..].to_vec();
                        rest.append(&mut words);
                        words = rest;
                        passages.push(Passage {
                            document: index,
                            page: page.number,
                            section: section.clone(),
                            text: window.join(" "),
                        });
                    }
                }
                self.flush(&mut passages, &mut words, &section, index, page.number);
            }
        }
        passages
    }

    /// Ends the passage being gathered.
    fn flush(
        &self,
        passages: &mut Vec<Passage>,
        words: &mut Vec<String>,
        section: &str,
        document: usize,
        page: Option<u32>,
    ) {
        if words.is_empty() {
            return;
        }
        let text = words.join(" ");
        words.clear();
        passages.push(Passage {
            document,
            page,
            section: section.to_string(),
            text,
        });
    }
}

/// The level and title of a heading line, `None` for any other line.
///
/// Recognized: Markdown (`## Titre`, also written for Word heading styles
/// by [`crate::documents`]); keyword headings (`Article 6 - Préavis`,
/// `Chapitre II`, `Section 3`, `§ 4`, `Annexe A`, in French, English and
/// German); numbered headings (`2.3 Garanties`, `IV. Résiliation`); short
/// lines in capitals (`CONDITIONS GÉNÉRALES`). A heading is short (at most
/// [`MAX_HEADING_WORDS`] words) and does not end like a sentence.
pub fn heading(line: &str) -> Option<(u8, String)> {
    let line = line.trim();
    if line.is_empty() {
        return None;
    }
    if let Some(rest) = line.strip_prefix('#') {
        let hashes = 1 + rest.chars().take_while(|c| *c == '#').count();
        let title = rest.trim_start_matches('#');
        if hashes <= 6 && title.starts_with(' ') && !title.trim().is_empty() {
            return Some((hashes as u8, clean_title(title)));
        }
        return None;
    }
    let words: Vec<&str> = line.split_whitespace().collect();
    if words.len() > MAX_HEADING_WORDS || ends_like_a_sentence(line) {
        return None;
    }
    if let Some(level) = keyword_level(&words) {
        return Some((level, clean_title(line)));
    }
    if let Some(level) = numbered_level(&words) {
        return Some((level, clean_title(line)));
    }
    if is_capitalized_title(line, &words) {
        return Some((1, clean_title(line)));
    }
    None
}

fn ends_like_a_sentence(line: &str) -> bool {
    line.ends_with(['.', ',', ';', '?', '!']) && !line.ends_with("...")
}

/// Level of a heading introduced by a keyword and a number.
fn keyword_level(words: &[&str]) -> Option<u8> {
    let first = words.first()?.to_lowercase();
    let first = first.trim_end_matches(['.', ':']);
    let level = match first {
        "partie" | "part" | "teil" | "titre" | "title" | "livre" | "book" | "buch" => 1,
        "chapitre" | "chapter" | "kapitel" => 1,
        "section" | "abschnitt" | "annexe" | "appendix" | "annex" | "anhang" => 2,
        "article" | "art" | "artikel" | "§" => 2,
        _ => {
            // "§3" written without a space.
            return first
                .strip_prefix('§')
                .filter(|rest| rest.chars().next().is_some_and(|c| c.is_ascii_digit()))
                .map(|_| 2);
        }
    };
    let number = words.get(1)?.trim_end_matches(['.', ':', '-', '–', ')']);
    let is_number = !number.is_empty()
        && (number.chars().all(|c| c.is_ascii_digit() || c == '.')
            || number.chars().all(|c| "IVXLCivxlc".contains(c))
            || (number.chars().count() == 1 && number.chars().all(|c| c.is_ascii_uppercase()))
            || matches!(
                number.to_lowercase().as_str(),
                "premier" | "1er" | "first" | "erster" | "unique"
            ));
    is_number.then_some(level)
}

/// Level of a numbered heading: `2.` or `2)` is 1, `2.3` is 2, `IV.` is 1.
/// The title after the number must start with a capital letter.
fn numbered_level(words: &[&str]) -> Option<u8> {
    let (number, title) = (words.first()?, words.get(1)?);
    // A numbered list item wrapped by a PDF can look like a heading: keep
    // numbered headings short.
    if words.len() > MAX_NUMBERED_HEADING_WORDS
        || !title.chars().next().is_some_and(char::is_uppercase)
    {
        return None;
    }
    let number = number.trim_end_matches(['.', ')']);
    if number.is_empty() {
        return None;
    }
    let parts: Vec<&str> = number.split('.').collect();
    if parts
        .iter()
        .all(|part| !part.is_empty() && part.len() <= 3 && part.chars().all(|c| c.is_ascii_digit()))
    {
        return Some(parts.len().min(6) as u8);
    }
    let roman = parts.len() == 1
        && parts[0].len() <= 5
        && parts[0].chars().all(|c| "IVXLC".contains(c))
        && words[0].ends_with(['.', ')']);
    roman.then_some(1)
}

/// A short line written in capitals, with at least two words of letters.
fn is_capitalized_title(line: &str, words: &[&str]) -> bool {
    let letters: Vec<char> = line.chars().filter(|c| c.is_alphabetic()).collect();
    words.len() >= 2
        && words.len() <= 10
        && letters.len() >= 6
        && letters.iter().all(|c| !c.is_lowercase())
}

fn clean_title(title: &str) -> String {
    let title = title.split_whitespace().collect::<Vec<_>>().join(" ");
    let title = title.trim_end_matches(':').trim();
    title.chars().take(MAX_HEADING_CHARS).collect()
}

#[cfg(test)]
mod tests;
