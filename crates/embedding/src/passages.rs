//! Pages to passages: the unit that is embedded, searched and shown to the
//! user.
//!
//! A passage is a window of at most [`Chunker::max_words`] words of one
//! page, overlapping the previous one by [`Chunker::overlap_words`] so that
//! an idea cut by a window boundary is still whole in one passage. Windows
//! stay inside a page, so every passage has the page number of its text.
//!
//! The defaults fit the 512-token input of the e5 models: 200 French or
//! English words are about 300 to 350 tokens with their tokenizer.
//! Chunking is deterministic: the same document always gives the same
//! passages, which verifiers rely on.

use crate::documents::Document;

/// How pages are cut into passages.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Chunker {
    pub max_words: usize,
    pub overlap_words: usize,
    /// A page with fewer words is still one passage; a trailing window
    /// with fewer words is merged into the previous one.
    pub min_words: usize,
}

impl Default for Chunker {
    fn default() -> Self {
        Self {
            max_words: 200,
            overlap_words: 40,
            min_words: 30,
        }
    }
}

/// One passage of a document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Passage {
    /// Index of the document in the submission.
    pub document: usize,
    pub page: Option<u32>,
    pub text: String,
}

impl Chunker {
    /// Passages of `documents`, in document then page order.
    pub fn passages(&self, documents: &[Document]) -> Vec<Passage> {
        let mut passages = Vec::new();
        for (index, document) in documents.iter().enumerate() {
            for page in &document.pages {
                for text in self.windows(&page.text) {
                    passages.push(Passage {
                        document: index,
                        page: page.number,
                        text,
                    });
                }
            }
        }
        passages
    }

    /// Overlapping windows of words of one page.
    pub fn windows(&self, text: &str) -> Vec<String> {
        let words: Vec<&str> = text.split_whitespace().collect();
        if words.is_empty() {
            return Vec::new();
        }
        let max = self.max_words.max(1);
        let step = max.saturating_sub(self.overlap_words).max(1);
        let mut windows = Vec::new();
        let mut start = 0;
        loop {
            let mut end = (start + max).min(words.len());
            // A short tail is merged into this window instead of becoming a
            // passage of a few words.
            if words.len() - end < self.min_words.min(step) {
                end = words.len();
            }
            windows.push(words[start..end].join(" "));
            if end == words.len() {
                break;
            }
            start += step;
        }
        windows
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::documents::Page;

    fn words(count: usize) -> String {
        (0..count)
            .map(|n| format!("w{n}"))
            .collect::<Vec<_>>()
            .join(" ")
    }

    #[test]
    fn a_short_page_is_one_passage() {
        let chunker = Chunker::default();
        assert_eq!(
            chunker.windows("  un   deux\ntrois "),
            vec!["un deux trois"]
        );
        assert!(chunker.windows(" \n ").is_empty());
    }

    #[test]
    fn windows_overlap_and_cover_every_word() {
        let chunker = Chunker {
            max_words: 10,
            overlap_words: 3,
            min_words: 2,
        };
        let windows = chunker.windows(&words(24));
        assert_eq!(windows[0], words(10));
        assert!(windows[1].starts_with("w7 w8 w9 w10"), "3 words of overlap");
        assert!(windows.last().unwrap().ends_with("w23"));
        assert!(windows.iter().all(|w| w.split(' ').count() <= 10));
    }

    #[test]
    fn a_short_tail_is_merged_into_the_last_window() {
        let chunker = Chunker {
            max_words: 10,
            overlap_words: 0,
            min_words: 3,
        };
        let windows = chunker.windows(&words(21));
        assert_eq!(windows.len(), 2, "w20 alone would be a useless passage");
        assert_eq!(windows[1].split(' ').count(), 11);
    }

    #[test]
    fn passages_keep_their_document_and_page() {
        let documents = vec![
            Document {
                name: "a.pdf".into(),
                pages: vec![
                    Page {
                        number: Some(1),
                        text: "un".into(),
                    },
                    Page {
                        number: Some(2),
                        text: "deux".into(),
                    },
                ],
            },
            Document {
                name: "b.txt".into(),
                pages: vec![Page {
                    number: None,
                    text: "trois".into(),
                }],
            },
        ];
        let passages = Chunker::default().passages(&documents);
        let summary: Vec<(usize, Option<u32>, &str)> = passages
            .iter()
            .map(|p| (p.document, p.page, p.text.as_str()))
            .collect();
        assert_eq!(
            summary,
            vec![(0, Some(1), "un"), (0, Some(2), "deux"), (1, None, "trois")]
        );
    }
}
