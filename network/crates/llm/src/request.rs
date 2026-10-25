//! What the site submits: `silicium-llm-request/1`, one JSON document.
//!
//! ```json
//! {"format": "silicium-llm-request/1",
//!  "task": "classify",
//!  "instruction": "Classe cet avis client.",
//!  "output": {"kind": "label", "labels": ["positif", "négatif", "neutre"]},
//!  "max_tokens": 64,
//!  "source": {"name": "avis.csv", "column": "commentaire"},
//!  "items": ["Livraison rapide, très content.", "…"]}
//! ```
//!
//! The site reads the user's file (CSV, JSON Lines, text) in the browser and
//! sends the chosen column as `items`. [`Request::parse`] checks every limit
//! and cleans the texts (Unicode NFC, line ends, control characters, the
//! model's special tokens, which would let an item rewrite the prompt), so
//! that the batch built from it is canonical: the same request always gives
//! the same batch, byte for byte.

use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

/// Format identifier of a request.
pub const FORMAT: &str = "silicium-llm-request/1";

/// Most items in one job.
pub const MAX_ITEMS: usize = 20_000;
/// Longest item, in characters (an item and its answer fit the context).
pub const MAX_ITEM_CHARS: usize = 6_000;
/// Longest instruction, in characters.
pub const MAX_INSTRUCTION_CHARS: usize = 2_000;
/// Labels of a classification.
pub const MIN_LABELS: usize = 2;
pub const MAX_LABELS: usize = 50;
pub const MAX_LABEL_CHARS: usize = 80;
/// Fields of an extraction.
pub const MAX_FIELDS: usize = 20;
pub const MAX_FIELD_CHARS: usize = 40;
/// Bounds and default of the answer length, in tokens.
pub const MIN_MAX_TOKENS: u32 = 16;
pub const MAX_MAX_TOKENS: u32 = 1024;
pub const DEFAULT_MAX_TOKENS: u32 = 256;
/// Kinds of task the site offers (informational: the instruction says it).
pub const TASKS: &[&str] = &["free", "summarize", "translate", "classify", "extract"];

/// Special tokens of the chat format, removed from every text.
const SPECIAL_TOKENS: &[&str] = &["<|im_start|>", "<|im_end|>", "<|endoftext|>"];

/// What an answer is.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum OutputSpec {
    /// Free text.
    Text,
    /// Exactly one of `labels` (a classification).
    Label { labels: Vec<String> },
    /// An object with one text value per field (an extraction).
    Fields { fields: Vec<String> },
}

/// Where the items come from (shown in the result, never interpreted).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Source {
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub name: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub column: String,
}

/// A checked, cleaned request.
#[derive(Debug, Clone, PartialEq)]
pub struct Request {
    pub task: String,
    pub instruction: String,
    pub output: OutputSpec,
    pub max_tokens: u32,
    pub source: Source,
    pub items: Vec<String>,
}

#[derive(Deserialize)]
struct Raw {
    format: String,
    #[serde(default)]
    task: Option<String>,
    #[serde(default)]
    instruction: String,
    output: Value,
    #[serde(default)]
    max_tokens: Option<u32>,
    #[serde(default)]
    source: Option<Value>,
    items: Vec<Value>,
}

impl Request {
    /// The request in `bytes`, checked and cleaned, or a message for the user.
    pub fn parse(bytes: &[u8]) -> Result<Request> {
        let raw: Raw = serde_json::from_slice(bytes)
            .map_err(|_| input("La demande n'est pas lisible (JSON attendu)."))?;
        if raw.format != FORMAT {
            return Err(input("Format de demande inconnu."));
        }
        let task = raw.task.unwrap_or_else(|| "free".into());
        if !TASKS.contains(&task.as_str()) {
            return Err(input("Type de traitement inconnu."));
        }
        let instruction = clean_text(&raw.instruction);
        if instruction.chars().count() > MAX_INSTRUCTION_CHARS {
            return Err(input(&format!(
                "La consigne dépasse {MAX_INSTRUCTION_CHARS} caractères."
            )));
        }
        let output = parse_output(raw.output)?;
        if instruction.is_empty() && output != OutputSpec::Text {
            return Err(input("Écris une consigne."));
        }
        let max_tokens = raw.max_tokens.unwrap_or(DEFAULT_MAX_TOKENS);
        if !(MIN_MAX_TOKENS..=MAX_MAX_TOKENS).contains(&max_tokens) {
            return Err(input(&format!(
                "La longueur des réponses doit être entre {MIN_MAX_TOKENS} et {MAX_MAX_TOKENS} jetons."
            )));
        }
        let items = parse_items(raw.items)?;
        Ok(Request {
            task,
            instruction,
            output,
            max_tokens,
            source: parse_source(raw.source),
            items,
        })
    }
}

fn parse_output(value: Value) -> Result<OutputSpec> {
    let output: OutputSpec =
        serde_json::from_value(value).map_err(|_| input("Type de réponse inconnu."))?;
    match output {
        OutputSpec::Text => Ok(OutputSpec::Text),
        OutputSpec::Label { labels } => {
            let labels = clean_names(labels, MAX_LABEL_CHARS, "Une catégorie")?;
            if !(MIN_LABELS..=MAX_LABELS).contains(&labels.len()) {
                return Err(input(&format!(
                    "Donne entre {MIN_LABELS} et {MAX_LABELS} catégories."
                )));
            }
            Ok(OutputSpec::Label { labels })
        }
        OutputSpec::Fields { fields } => {
            let fields = clean_names(fields, MAX_FIELD_CHARS, "Un champ")?;
            if fields.is_empty() || fields.len() > MAX_FIELDS {
                return Err(input(&format!("Donne entre 1 et {MAX_FIELDS} champs.")));
            }
            Ok(OutputSpec::Fields { fields })
        }
    }
}

/// Labels or field names: trimmed, single spaces, non-empty, unique
/// (ignoring case).
fn clean_names(names: Vec<String>, max_chars: usize, what: &str) -> Result<Vec<String>> {
    let mut cleaned: Vec<String> = Vec::with_capacity(names.len());
    for name in names {
        let name = clean_text(&name)
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        if name.is_empty() {
            return Err(input(&format!("{what} est vide.")));
        }
        if name.chars().count() > max_chars {
            return Err(input(&format!(
                "{what} dépasse {max_chars} caractères : « {name} »."
            )));
        }
        if cleaned
            .iter()
            .any(|seen| seen.to_lowercase() == name.to_lowercase())
        {
            return Err(input(&format!("« {name} » est donné deux fois.")));
        }
        cleaned.push(name);
    }
    Ok(cleaned)
}

fn parse_items(values: Vec<Value>) -> Result<Vec<String>> {
    if values.is_empty() {
        return Err(input("La liste ne contient aucun élément."));
    }
    if values.len() > MAX_ITEMS {
        return Err(input(&format!(
            "La liste contient plus de {MAX_ITEMS} éléments : envoie-la en plusieurs fois."
        )));
    }
    values
        .into_iter()
        .enumerate()
        .map(|(index, value)| {
            let text = match value {
                Value::String(text) => clean_text(&text),
                Value::Number(number) => number.to_string(),
                _ => {
                    return Err(input(&format!(
                        "L'élément n° {} n'est pas un texte.",
                        index + 1
                    )));
                }
            };
            if text.is_empty() {
                return Err(input(&format!("L'élément n° {} est vide.", index + 1)));
            }
            if text.chars().count() > MAX_ITEM_CHARS {
                return Err(input(&format!(
                    "L'élément n° {} dépasse {MAX_ITEM_CHARS} caractères.",
                    index + 1
                )));
            }
            Ok(text)
        })
        .collect()
}

fn parse_source(value: Option<Value>) -> Source {
    let text = |key: &str| {
        value
            .as_ref()
            .and_then(|value| value.get(key))
            .and_then(Value::as_str)
            .map(|text| clean_text(text).chars().take(200).collect())
            .unwrap_or_default()
    };
    Source {
        name: text("name"),
        column: text("column"),
    }
}

/// `text` in canonical form: Unicode NFC, `\n` line ends, no control
/// characters but line feeds and tabs, no special token of the chat format,
/// no space around.
pub fn clean_text(text: &str) -> String {
    let mut cleaned: String = text
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .nfc()
        .filter(|c| !c.is_control() || *c == '\n' || *c == '\t')
        .collect();
    // Removing a token can join the halves of another one: repeat.
    while let Some(token) = SPECIAL_TOKENS
        .iter()
        .find(|token| cleaned.contains(**token))
    {
        cleaned = cleaned.replace(token, "");
    }
    cleaned.trim().to_string()
}

fn input(message: &str) -> Error {
    Error::Input(message.to_string())
}

#[cfg(test)]
mod tests;
