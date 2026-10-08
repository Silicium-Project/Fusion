//! `silicium-embed eval`: builds the index of a question set's documents
//! on this machine and measures the search (see `silicium_embedding::eval`).

use silicium_embedding::{
    corpus::{self, PassageRecord},
    documents::{self, Extraction, Limits},
    encoder::Encoder,
    eval,
    index::{self, Index},
    model::ModelSpec,
    passages::Chunker,
    search::{self, Mode},
    vectors::VectorBlock,
};
use std::path::Path;

/// Reads every file under `dir` (sorted, so the corpus is the same on
/// every machine) as one submission.
fn extract_directory(dir: &Path) -> Result<Extraction, Box<dyn std::error::Error>> {
    let mut files = Vec::new();
    let mut pending = vec![dir.to_path_buf()];
    while let Some(current) = pending.pop() {
        for entry in std::fs::read_dir(&current)? {
            let path = entry?.path();
            if path.is_dir() {
                pending.push(path);
            } else {
                files.push(path);
            }
        }
    }
    files.sort();
    let mut extraction = Extraction::default();
    for path in files {
        let name = path.strip_prefix(dir)?.to_string_lossy().replace('\\', "/");
        let read = documents::extract_bytes(&name, &std::fs::read(&path)?, &Limits::default());
        extraction.documents.extend(read.documents);
        extraction.skipped.extend(read.skipped);
    }
    Ok(extraction)
}

/// Builds the index of a question set's documents and prints the reports.
pub(crate) fn run(
    encoder: Option<&Encoder>,
    spec: &ModelSpec,
    set: &Path,
    (chunker, input): (&Chunker, Input),
    lexical_weights: &[f32],
    json: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let questions = eval::read_questions(&std::fs::read_to_string(set.join("questions.jsonl"))?)?;
    let extraction = extract_directory(&set.join("documents"))?;
    for skipped in &extraction.skipped {
        eprintln!("skipped {}: {:?}", skipped.name, skipped.reason);
    }
    let corpus_bytes = corpus::build(&extraction, chunker)?;
    let (header, body) = corpus::read_header(&corpus_bytes)?;
    let records = corpus::read_range(&corpus_bytes, body as u64, corpus_bytes.len() as u64)?;
    let vectors = match encoder {
        Some(encoder) => {
            let inputs: Vec<_> = records
                .iter()
                .map(|record| input.of(record, &header.documents))
                .collect();
            let texts: Vec<&str> = inputs.iter().map(String::as_str).collect();
            encoder.embed_passages(&texts)?
        }
        // Keywords only: any unit vectors will do, they are not searched.
        None => records
            .iter()
            .map(|_| {
                let mut unit = vec![0.0; spec.dimension];
                unit[0] = 1.0;
                unit
            })
            .collect(),
    };
    let block = VectorBlock::new(spec.dimension, 0, &vectors)?;
    let index = Index::from_files(index::assemble(&corpus_bytes, &[block], spec)?)?;
    eprintln!(
        "{} documents, {} passages, {} questions (chunks of {} words, overlap {}, min {}, headings {}, input {input:?})",
        header.documents.len(),
        header.passage_count,
        questions.len(),
        chunker.max_words,
        chunker.overlap_words,
        chunker.min_words,
        chunker.headings
    );
    let mut runs = vec![(Mode::Lexical, 1.0)];
    if encoder.is_some() {
        runs.insert(0, (Mode::Dense, 1.0));
        runs.push((Mode::Auto, search::LEXICAL_WEIGHT));
        runs.extend(lexical_weights.iter().map(|&weight| (Mode::Hybrid, weight)));
    }
    let embed = |question: &str| -> silicium_embedding::Result<Vec<f32>> {
        encoder
            .ok_or_else(|| silicium_embedding::Error::Input("no model".into()))?
            .embed_query(question)
    };
    let mut reports = Vec::new();
    for (mode, weight) in runs {
        reports.push(eval::evaluate(&index, &questions, mode, weight, &embed)?);
    }
    if json {
        println!("{}", serde_json::to_string_pretty(&reports)?);
    } else {
        for report in &reports {
            println!("{}", eval::format_report(report));
        }
    }
    Ok(())
}

/// What the model reads of a passage, in an evaluation.
#[derive(Debug, Clone, Copy)]
pub(crate) enum Input {
    /// As the network: document title, section and text.
    Full,
    Section,
    Title,
    Text,
}

impl std::str::FromStr for Input {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, String> {
        match value {
            "full" => Ok(Input::Full),
            "section" => Ok(Input::Section),
            "title" => Ok(Input::Title),
            "text" => Ok(Input::Text),
            other => Err(format!(
                "unknown input {other} (full, section, title, text)"
            )),
        }
    }
}

impl Input {
    fn of(self, record: &PassageRecord, documents: &[corpus::DocumentEntry]) -> String {
        let title = || {
            documents
                .get(record.doc as usize)
                .map(|document| corpus::document_title(&document.name))
                .unwrap_or_default()
        };
        match self {
            Input::Full => record.embedding_input(documents),
            Input::Section => corpus::embedding_text("", &record.section, &record.text),
            Input::Title => corpus::embedding_text(&title(), "", &record.text),
            Input::Text => record.text.clone(),
        }
    }
}
