//! The exact prompt of an item, the schema of its answer, and how a raw
//! answer is read.
//!
//! Workers and verifiers must send the model the same tokens: the prompt is
//! written here in the chat format of the model (ChatML for Qwen) and sent
//! in Ollama's `raw` mode, so the template of the Ollama version installed
//! on a machine never comes into play. Changing anything here changes the
//! answers: increment [`PROMPT_VERSION`] and, before nodes mix, the workload.
//!
//! Classifications and extractions are constrained by a JSON schema
//! (Ollama's structured outputs): the answer is always one of the labels,
//! or an object with the requested fields.

use crate::{
    batch::BatchHeader,
    request::{OutputSpec, clean_text},
};
use serde_json::{Map, Value, json};

/// Version of the prompt format, written in the result.
pub const PROMPT_VERSION: u32 = 1;

const SYSTEM: &str = "You are a careful assistant that processes one item of a list at a time. \
Follow the instruction exactly. Reply with the result only: no introduction, no explanation, \
no repetition of the instruction. Unless the instruction asks otherwise, reply in the language \
of the instruction.";

const SYSTEM_PROMPT_ONLY: &str = "You are a helpful assistant. Reply concisely, in the \
language of the user's message.";

/// The raw prompt of `item` in the job described by `header`.
pub fn prompt(header: &BatchHeader, item: &str) -> String {
    let (system, user) = if header.instruction.is_empty() {
        (SYSTEM_PROMPT_ONLY, item.to_string())
    } else {
        let guide = match &header.output {
            OutputSpec::Text => String::new(),
            OutputSpec::Label { labels } => format!(
                "\n\nAnswer with exactly one of these categories: {}.",
                labels.join(", ")
            ),
            OutputSpec::Fields { fields } => format!(
                "\n\nAnswer in JSON with these fields: {}. Use an empty string for a field the text does not give.",
                fields.join(", ")
            ),
        };
        (
            SYSTEM,
            format!("{}{guide}\n\n<text>\n{item}\n</text>", header.instruction),
        )
    };
    format!(
        "<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
    )
}

/// JSON schema the answer must follow (Ollama's `format`), none for text.
pub fn schema(output: &OutputSpec) -> Option<Value> {
    match output {
        OutputSpec::Text => None,
        OutputSpec::Label { labels } => Some(json!({
            "type": "object",
            "properties": {"label": {"type": "string", "enum": labels}},
            "required": ["label"],
        })),
        OutputSpec::Fields { fields } => {
            let properties: Map<String, Value> = fields
                .iter()
                .map(|field| (field.clone(), json!({"type": "string"})))
                .collect();
            Some(json!({
                "type": "object",
                "properties": properties,
                "required": fields,
            }))
        }
    }
}

/// The answer the model wrote (`raw`), as published: a string for a text
/// or a label, an object `{field: text}` for an extraction, `null` when a
/// constrained answer is unusable (cut by the length limit, unknown label).
pub fn read_answer(output: &OutputSpec, raw: &str) -> Value {
    match output {
        OutputSpec::Text => Value::String(clean_text(raw)),
        OutputSpec::Label { labels } => {
            let label = serde_json::from_str::<Value>(raw.trim())
                .ok()
                .and_then(|value| value.get("label").and_then(Value::as_str).map(clean_text));
            label
                .and_then(|label| {
                    labels
                        .iter()
                        .find(|known| known.to_lowercase() == label.to_lowercase())
                })
                .map_or(Value::Null, |known| Value::String(known.clone()))
        }
        OutputSpec::Fields { fields } => {
            let Ok(Value::Object(object)) = serde_json::from_str::<Value>(raw.trim()) else {
                return Value::Null;
            };
            let values: Map<String, Value> = fields
                .iter()
                .map(|field| {
                    let text = match object.get(field) {
                        Some(Value::String(text)) => clean_text(text),
                        Some(Value::Null) | None => String::new(),
                        Some(other) => clean_text(&other.to_string()),
                    };
                    (field.clone(), Value::String(text))
                })
                .collect();
            Value::Object(values)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::request::Source;

    fn header(instruction: &str, output: OutputSpec) -> BatchHeader {
        BatchHeader {
            format: crate::batch::FORMAT.into(),
            model: "m".into(),
            item_count: 1,
            task: "free".into(),
            instruction: instruction.into(),
            output,
            max_tokens: 64,
            source: Source::default(),
        }
    }

    fn labels() -> OutputSpec {
        OutputSpec::Label {
            labels: vec!["positif".into(), "négatif".into()],
        }
    }

    #[test]
    fn the_prompt_is_chatml_with_the_item_delimited() {
        let text = prompt(&header("Résume.", OutputSpec::Text), "Bonjour.");
        assert!(text.starts_with("<|im_start|>system\nYou are a careful"));
        assert!(text.contains("<|im_start|>user\nRésume.\n\n<text>\nBonjour.\n</text><|im_end|>"));
        assert!(text.ends_with("<|im_start|>assistant\n"));
        let labelled = prompt(&header("Classe.", labels()), "x");
        assert!(labelled.contains("categories: positif, négatif."));
        let free = prompt(&header("", OutputSpec::Text), "Écris un haïku.");
        assert!(free.contains("<|im_start|>user\nÉcris un haïku.<|im_end|>"));
    }

    #[test]
    fn schemas_constrain_labels_and_fields() {
        assert!(schema(&OutputSpec::Text).is_none());
        let label = schema(&labels()).unwrap();
        assert_eq!(label["properties"]["label"]["enum"][1], "négatif");
        let fields = schema(&OutputSpec::Fields {
            fields: vec!["nom".into(), "date".into()],
        })
        .unwrap();
        assert_eq!(fields["required"], json!(["nom", "date"]));
    }

    #[test]
    fn answers_are_read_by_kind() {
        assert_eq!(
            read_answer(&OutputSpec::Text, "  Salut.\n"),
            json!("Salut.")
        );
        assert_eq!(
            read_answer(&labels(), r#"{"label":"Positif"}"#),
            json!("positif")
        );
        assert_eq!(read_answer(&labels(), r#"{"label":"autre"}"#), Value::Null);
        assert_eq!(read_answer(&labels(), r#"{"label":"pos"#), Value::Null);
        let fields = OutputSpec::Fields {
            fields: vec!["nom".into(), "montant".into(), "date".into()],
        };
        assert_eq!(
            read_answer(&fields, r#"{"nom":" Alice ","montant":12.5,"extra":1}"#),
            json!({"nom": "Alice", "montant": "12.5", "date": ""})
        );
        assert_eq!(read_answer(&fields, "[1]"), Value::Null);
    }
}
