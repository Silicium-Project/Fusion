//! Syntax of scenes: `key = value` / `name = { ... }` (`:` works like `=`),
//! read into a tree.
//!
//! It understands comments (`#`, `//`), quoted text,
//! exponents (`1e-3`), lists of bare values (`vertices = { 0 0 0  1 0 0 }`),
//! keyframes (`x = { 0 = 1  48 = 5 }`) and libconfig lists (`( ... )`).

use std::fmt;

/// A value: a number, a word (`glass`, `"car body"`) or a block.
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Number(f64),
    Word(String),
    Block(Vec<Entry>),
}

/// One item of a block: `key = value`, or a bare value (`key` is `None`).
#[derive(Clone, Debug, PartialEq)]
pub struct Entry {
    pub key: Option<String>,
    pub value: Value,
    /// 1-based line of the key (or of the bare value).
    pub line: usize,
}

/// Syntax error with its line.
#[derive(Clone, Debug, PartialEq)]
pub struct SyntaxError {
    pub line: usize,
    /// `unbalanced_braces` or `syntax_error`.
    pub code: &'static str,
    pub message: String,
}

impl fmt::Display for SyntaxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

#[derive(Clone, Debug, PartialEq)]
enum Token {
    Open,
    Close,
    Assign,
    Text(String, bool),
}

fn tokenize(text: &str) -> Result<Vec<(Token, usize)>, SyntaxError> {
    let mut tokens = Vec::new();
    let mut chars = text.chars().peekable();
    let mut line = 1;
    let mut current = String::new();
    let flush = |current: &mut String, tokens: &mut Vec<(Token, usize)>, line: usize| {
        if !current.is_empty() {
            tokens.push((Token::Text(std::mem::take(current), false), line));
        }
    };
    while let Some(character) = chars.next() {
        let sign_allowed = current.is_empty()
            || (current.ends_with(['e', 'E'])
                && current
                    .chars()
                    .next()
                    .is_some_and(|c| c.is_ascii_digit() || c == '.' || c == '-' || c == '+'));
        match character {
            c if c.is_ascii_alphanumeric() || c == '_' || c == '.' => current.push(c),
            '-' | '+' if sign_allowed => current.push(character),
            '#' => {
                flush(&mut current, &mut tokens, line);
                while chars.peek().is_some_and(|c| *c != '\n') {
                    chars.next();
                }
            }
            '/' if chars.peek() == Some(&'/') => {
                flush(&mut current, &mut tokens, line);
                while chars.peek().is_some_and(|c| *c != '\n') {
                    chars.next();
                }
            }
            '"' => {
                flush(&mut current, &mut tokens, line);
                let start = line;
                let mut word = String::new();
                loop {
                    match chars.next() {
                        Some('"') => break,
                        Some('\n') | None => {
                            return Err(SyntaxError {
                                line: start,
                                code: "syntax_error",
                                message: "unterminated text: a `\"` is missing".into(),
                            })
                        }
                        Some(c) => word.push(c),
                    }
                }
                tokens.push((Token::Text(word, true), start));
            }
            _ => {
                flush(&mut current, &mut tokens, line);
                match character {
                    '{' | '(' => tokens.push((Token::Open, line)),
                    '}' | ')' => tokens.push((Token::Close, line)),
                    '=' | ':' => tokens.push((Token::Assign, line)),
                    '\n' => line += 1,
                    _ => {}
                }
            }
        }
    }
    flush(&mut current, &mut tokens, line);
    Ok(tokens)
}

fn scalar(text: String, quoted: bool) -> Value {
    if !quoted {
        if let Ok(number) = text.parse::<f64>() {
            return Value::Number(number);
        }
    }
    Value::Word(text)
}

struct Parser {
    tokens: Vec<(Token, usize)>,
    position: usize,
}

impl Parser {
    fn peek(&self, offset: usize) -> Option<&Token> {
        self.tokens
            .get(self.position + offset)
            .map(|(token, _)| token)
    }

    fn line(&self) -> usize {
        self.tokens
            .get(self.position)
            .or(self.tokens.last())
            .map(|(_, line)| *line)
            .unwrap_or(1)
    }

    /// Entries until the matching `}` (consumed) or the end of the file.
    fn block(&mut self, opened_at: Option<usize>) -> Result<Vec<Entry>, SyntaxError> {
        let mut entries = Vec::new();
        loop {
            let line = self.line();
            let Some(token) = self.peek(0).cloned() else {
                return match opened_at {
                    Some(line) => Err(SyntaxError {
                        line,
                        code: "unbalanced_braces",
                        message: "this block is never closed: a `}` is missing".into(),
                    }),
                    None => Ok(entries),
                };
            };
            match token {
                Token::Close => {
                    self.position += 1;
                    return match opened_at {
                        Some(_) => Ok(entries),
                        None => Err(SyntaxError {
                            line,
                            code: "unbalanced_braces",
                            message: "this `}` closes nothing".into(),
                        }),
                    };
                }
                Token::Assign => {
                    // A stray `=` or `:` (e.g. `camera : { ... };` leftovers).
                    self.position += 1;
                }
                Token::Open => {
                    self.position += 1;
                    let inner = self.block(Some(line))?;
                    entries.push(Entry {
                        key: None,
                        value: Value::Block(inner),
                        line,
                    });
                }
                Token::Text(text, quoted) => {
                    self.position += 1;
                    if self.peek(0) == Some(&Token::Assign) {
                        self.position += 1;
                        let value = match self.peek(0).cloned() {
                            Some(Token::Open) => {
                                let opened = self.line();
                                self.position += 1;
                                Value::Block(self.block(Some(opened))?)
                            }
                            Some(Token::Text(value, quoted)) => {
                                self.position += 1;
                                scalar(value, quoted)
                            }
                            _ => {
                                return Err(SyntaxError {
                                    line,
                                    code: "syntax_error",
                                    message: format!("`{text}` has no value after `=`"),
                                })
                            }
                        };
                        entries.push(Entry {
                            key: Some(text),
                            value,
                            line,
                        });
                    } else {
                        entries.push(Entry {
                            key: None,
                            value: scalar(text, quoted),
                            line,
                        });
                    }
                }
            }
        }
    }
}

/// Parses a whole scene file into its top-level entries.
pub fn parse(text: &str) -> Result<Vec<Entry>, SyntaxError> {
    let tokens = tokenize(text)?;
    Parser {
        tokens,
        position: 0,
    }
    .block(None)
}

/// The blocks described by a value: the block itself, or each block of a
/// list (`point = ( { ... }, { ... } )`, the libconfig form).
pub fn items(value: &Value) -> Vec<&[Entry]> {
    match value {
        Value::Block(entries)
            if !entries.is_empty()
                && entries
                    .iter()
                    .all(|e| e.key.is_none() && matches!(e.value, Value::Block(_))) =>
        {
            entries
                .iter()
                .filter_map(|e| match &e.value {
                    Value::Block(inner) => Some(inner.as_slice()),
                    _ => None,
                })
                .collect()
        }
        Value::Block(entries) => vec![entries.as_slice()],
        _ => Vec::new(),
    }
}

/// Helpers to read a block.
pub trait BlockExt {
    fn entries(&self) -> &[Entry];

    /// First entry named `key`.
    fn entry(&self, key: &str) -> Option<&Entry> {
        self.entries()
            .iter()
            .find(|entry| entry.key.as_deref() == Some(key))
    }

    /// Every entry named `key`, in order.
    fn all<'a>(&'a self, key: &'a str) -> Box<dyn Iterator<Item = &'a Entry> + 'a> {
        Box::new(
            self.entries()
                .iter()
                .filter(move |entry| entry.key.as_deref() == Some(key)),
        )
    }

    /// The block named `key`, if any.
    fn block(&self, key: &str) -> Option<&[Entry]> {
        match &self.entry(key)?.value {
            Value::Block(entries) => Some(entries),
            _ => None,
        }
    }

    /// The word named `key`, if any.
    fn word(&self, key: &str) -> Option<&str> {
        match &self.entry(key)?.value {
            Value::Word(word) => Some(word),
            _ => None,
        }
    }

    /// Number `key` at animation frame `frame` (keyframes are interpolated).
    fn number(&self, key: &str, default: f64, frame: f64) -> f64 {
        self.entry(key)
            .and_then(|entry| evaluate(&entry.value, frame))
            .unwrap_or(default)
    }

    /// Bare numbers of the block (`vertices = { 0 0 0  1 0 0 }`).
    fn numbers(&self) -> Vec<f64> {
        self.entries()
            .iter()
            .filter(|entry| entry.key.is_none())
            .filter_map(|entry| match entry.value {
                Value::Number(number) => Some(number),
                _ => None,
            })
            .collect()
    }
}

impl BlockExt for [Entry] {
    fn entries(&self) -> &[Entry] {
        self
    }
}

impl BlockExt for Vec<Entry> {
    fn entries(&self) -> &[Entry] {
        self
    }
}

/// Keyframes of a value: `{ 0 = 1  48 = 5  ease = smooth }`, sorted by frame.
pub fn keyframes(entries: &[Entry]) -> Option<(Vec<(f64, f64)>, bool)> {
    let mut keys = Vec::new();
    let mut smooth = false;
    for entry in entries {
        let key = entry.key.as_deref()?;
        if key == "ease" {
            smooth = matches!(&entry.value, Value::Word(word) if word == "smooth");
            continue;
        }
        let frame = key.parse::<f64>().ok()?;
        let Value::Number(value) = entry.value else {
            return None;
        };
        keys.push((frame, value));
    }
    if keys.is_empty() {
        return None;
    }
    keys.sort_by(|a, b| a.0.total_cmp(&b.0));
    Some((keys, smooth))
}

/// Value of a number or of keyframes at `frame` (clamped to the first and
/// last keys, linear or smoothstep in between).
pub fn evaluate(value: &Value, frame: f64) -> Option<f64> {
    match value {
        Value::Number(number) => Some(*number),
        Value::Block(entries) => {
            let (keys, smooth) = keyframes(entries)?;
            let first = keys[0];
            let last = keys[keys.len() - 1];
            if frame <= first.0 {
                return Some(first.1);
            }
            if frame >= last.0 {
                return Some(last.1);
            }
            let index = keys.iter().position(|(at, _)| *at > frame)?;
            let (a, b) = (keys[index - 1], keys[index]);
            let mut t = (frame - a.0) / (b.0 - a.0);
            if smooth {
                t = t * t * (3.0 - 2.0 * t);
            }
            Some(a.1 + (b.1 - a.1) * t)
        }
        Value::Word(_) => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_blocks_words_lists_comments_and_keyframes() {
        let text = "# scene\nrender : { samples = 16 mode = path } // end\n\
                    primitives : ( { name = \"car body\" } );\n\
                    mesh = { vertices = { 0 0 0  1e-3 -2 +3 } }\n\
                    x = { 0 = 1  10 = 3 }\n";
        let entries = parse(text).unwrap();
        let render = entries.block("render").unwrap();
        assert_eq!(render.number("samples", 1.0, 0.0), 16.0);
        assert_eq!(render.word("mode"), Some("path"));
        let primitives = entries.block("primitives").unwrap();
        let Value::Block(inner) = &primitives[0].value else {
            panic!("bare block expected")
        };
        assert_eq!(inner.word("name"), Some("car body"));
        let mesh = entries.block("mesh").unwrap();
        assert_eq!(
            mesh.block("vertices").unwrap().numbers(),
            vec![0.0, 0.0, 0.0, 1e-3, -2.0, 3.0]
        );
        assert_eq!(entries.number("x", 0.0, -5.0), 1.0);
        assert_eq!(entries.number("x", 0.0, 5.0), 2.0);
        assert_eq!(entries.number("x", 0.0, 50.0), 3.0);
        assert_eq!(entries.entry("x").unwrap().line, 5);
    }

    #[test]
    fn reports_unbalanced_braces_with_their_line() {
        assert_eq!(parse("a = {\nb = 1\n").unwrap_err().line, 1);
        assert_eq!(parse("a = 1\n}\n").unwrap_err().line, 2);
        assert_eq!(parse("a = \"oops\n").unwrap_err().line, 1);
    }
}
