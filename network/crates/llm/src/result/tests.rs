use super::*;
use crate::{
    model::QWEN2_5_1_5B_INSTRUCT as MODEL,
    request::{Request, Source},
};

fn batch(output: OutputSpec, items: &[&str]) -> Vec<u8> {
    let request = Request {
        task: "free".into(),
        instruction: "Fais-le.".into(),
        output,
        max_tokens: 64,
        source: Source {
            name: "avis.csv".into(),
            column: "texte".into(),
        },
        items: items.iter().map(|item| item.to_string()).collect(),
    };
    batch::build(&request, MODEL.id).unwrap()
}

fn published(first: u64, outputs: &[Value]) -> Vec<u8> {
    let list: Vec<Answer> = outputs
        .iter()
        .enumerate()
        .map(|(index, output)| Answer {
            id: first + index as u64,
            output: output.clone(),
        })
        .collect();
    answers::to_bytes(&list).unwrap()
}

#[test]
fn a_result_is_assembled_from_its_fragments() {
    let bytes = batch(OutputSpec::Text, &["un", "deux", "trois"]);
    let first = published(0, &[json!("one"), json!("two")]);
    let second = published(2, &[json!("=SUM(A1)")]);
    let files = assemble(
        &bytes,
        &[
            FragmentAnswers {
                bytes: &first,
                first_id: 0,
                count: 2,
            },
            FragmentAnswers {
                bytes: &second,
                first_id: 2,
                count: 1,
            },
        ],
        &MODEL,
    )
    .unwrap();
    let lines: Vec<Value> = files
        .answers
        .split(|&b| b == b'\n')
        .filter(|line| !line.is_empty())
        .map(|line| serde_json::from_slice(line).unwrap())
        .collect();
    assert_eq!(lines[1], json!({"id": 1, "input": "deux", "output": "two"}));
    let csv = String::from_utf8(files.csv).unwrap();
    assert!(csv.starts_with("\u{feff}\"id\",\"input\",\"output\"\r\n\"1\",\"un\",\"one\"\r\n"));
    assert!(csv.contains("\"3\",\"trois\",\"'=SUM(A1)\""), "no formula");
    let manifest: Value = serde_json::from_slice(&files.manifest).unwrap();
    assert_eq!(manifest["format"], FORMAT);
    assert_eq!(manifest["item_count"], 3);
    assert_eq!(manifest["answered"], 3);
    assert_eq!(manifest["model"]["sha256"], MODEL.weights.sha256);
    assert_eq!(manifest["source"]["column"], "texte");
}

#[test]
fn extractions_get_one_column_per_field() {
    let fields = OutputSpec::Fields {
        fields: vec!["nom".into(), "ville".into()],
    };
    let bytes = batch(fields, &["Alice, de Lyon", "?"]);
    let answers = published(0, &[json!({"nom": "Alice", "ville": "Lyon"}), Value::Null]);
    let files = assemble(
        &bytes,
        &[FragmentAnswers {
            bytes: &answers,
            first_id: 0,
            count: 2,
        }],
        &MODEL,
    )
    .unwrap();
    let csv = String::from_utf8(files.csv).unwrap();
    assert!(csv.contains("\"id\",\"input\",\"nom\",\"ville\"\r\n"));
    assert!(csv.contains("\"1\",\"Alice, de Lyon\",\"Alice\",\"Lyon\"\r\n"));
    assert!(csv.contains("\"2\",\"?\",\"\",\"\"\r\n"));
    let manifest: Value = serde_json::from_slice(&files.manifest).unwrap();
    assert_eq!(manifest["answered"], 1);
}

#[test]
fn missing_or_misplaced_answers_are_refused() {
    let bytes = batch(OutputSpec::Text, &["un", "deux"]);
    let first = published(0, &[json!("one")]);
    let wrong = published(0, &[json!("two")]);
    assert!(
        assemble(
            &bytes,
            &[FragmentAnswers {
                bytes: &first,
                first_id: 0,
                count: 1
            }],
            &MODEL
        )
        .is_err()
    );
    assert!(
        assemble(
            &bytes,
            &[
                FragmentAnswers {
                    bytes: &first,
                    first_id: 0,
                    count: 1
                },
                FragmentAnswers {
                    bytes: &wrong,
                    first_id: 1,
                    count: 1
                },
            ],
            &MODEL,
        )
        .is_err(),
        "ids of another fragment"
    );
}

#[test]
fn csv_cells_are_quoted_and_negative_numbers_kept() {
    let mut text = String::new();
    push_row(
        &mut text,
        &[
            "-12.5".into(),
            "- une liste".into(),
            "-x".into(),
            "a \"b\"\nc".into(),
        ],
    );
    assert_eq!(
        text,
        "\"-12.5\",\"- une liste\",\"'-x\",\"a \"\"b\"\"\nc\"\r\n"
    );
}
