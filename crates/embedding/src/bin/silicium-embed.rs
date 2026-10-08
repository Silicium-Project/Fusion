//! `silicium-embed`: the document-search pipeline on one machine, for
//! operators and for checking the network's results.
//!
//! ```text
//! silicium-embed prepare documents.zip -o corpus.jsonl   # files -> corpus
//! silicium-embed model fetch                             # download + check the model
//! silicium-embed index corpus.jsonl -o index/            # corpus -> index (all local)
//! silicium-embed search index/ "comment résilier ?"      # best passages, JSON lines
//! silicium-embed eval crates/embedding/eval              # search quality on a question set
//! ```
//!
//! `eval` builds an index of the set's documents on this machine (the
//! model is downloaded once), then reports recall@1/3/5/10 and MRR for the
//! search by meaning, by keywords and hybrid. `--lexical-only` skips the
//! model (keywords only); `--max-words`, `--overlap-words` and
//! `--min-words` try other chunkings.
//!
//! Model files are kept under `--data-dir/models` (default: the
//! `SILICIUM_DATA_DIR` directory, else the current one), or
//! `SILICIUM_MODEL_DIR`; see `silicium_embedding::model::store`.

use clap::{Parser, Subcommand};
use silicium_embedding::{
    corpus::{self, PassageRecord},
    documents::{self, Extraction, Limits},
    encoder::Encoder,
    eval,
    index::{self, Index},
    model::{self, ModelSpec, store::ModelStore},
    passages::Chunker,
    search::{self, Mode},
    vectors::VectorBlock,
};
use std::{
    path::{Path, PathBuf},
    process::ExitCode,
};

#[derive(Parser)]
#[command(
    name = "silicium-embed",
    about = "Silicium document search, on one machine"
)]
struct Cli {
    /// Directory holding `models/` (default: $SILICIUM_DATA_DIR or `.`).
    #[arg(long, global = true)]
    data_dir: Option<PathBuf>,
    /// Model identifier.
    #[arg(long, global = true, default_value = "multilingual-e5-small")]
    model: String,
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Turns documents (PDF, .docx, text, Markdown, or a ZIP) into a corpus.
    Prepare {
        input: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
    },
    /// Model files.
    Model {
        #[command(subcommand)]
        action: ModelAction,
    },
    /// Embeds every passage of a corpus and writes the index files.
    Index {
        corpus: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
    },
    /// Searches an index.
    Search {
        index: PathBuf,
        query: String,
        #[arg(short, default_value_t = 10)]
        k: usize,
        /// `auto` (default: hybrid when the query has a number, code or
        /// acronym, meaning otherwise), `hybrid`, `dense` or `lexical`.
        #[arg(long, default_value = "auto")]
        mode: String,
    },
    /// Measures the search on a question set (`documents/` + `questions.jsonl`).
    Eval {
        set: PathBuf,
        /// Keywords only: no model needed.
        #[arg(long)]
        lexical_only: bool,
        #[arg(long)]
        max_words: Option<usize>,
        #[arg(long)]
        overlap_words: Option<usize>,
        #[arg(long)]
        min_words: Option<usize>,
        /// Weights of the keywords tried in hybrid mode (the meaning weighs 1).
        #[arg(long, value_delimiter = ',', default_values_t = [0.2, 0.35, 0.5, 0.75, 1.0])]
        lexical_weights: Vec<f32>,
        /// Prints the reports as JSON.
        #[arg(long)]
        json: bool,
    },
}

#[derive(Subcommand)]
enum ModelAction {
    /// Downloads the model files (if missing) and checks their hashes.
    Fetch,
}

fn main() -> ExitCode {
    match run(Cli::parse()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("silicium-embed: {err}");
            ExitCode::FAILURE
        }
    }
}

fn run(cli: Cli) -> Result<(), Box<dyn std::error::Error>> {
    let spec = model::find(&cli.model).ok_or_else(|| format!("unknown model {}", cli.model))?;
    let data_dir = cli
        .data_dir
        .or_else(|| std::env::var_os("SILICIUM_DATA_DIR").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("."));
    match cli.command {
        Command::Prepare { input, output } => prepare(&input, &output),
        Command::Model {
            action: ModelAction::Fetch,
        } => {
            let paths = ModelStore::from_env(&data_dir)?.ensure(spec)?;
            Encoder::load(spec, &paths)?;
            println!("{} ready in {}", spec.id, paths.weights.display());
            Ok(())
        }
        Command::Index { corpus, output } => {
            build_index(&load(spec, &data_dir)?, spec, &corpus, &output)
        }
        Command::Search {
            index,
            query,
            k,
            mode,
        } => search(&load(spec, &data_dir)?, &index, &query, k, mode.parse()?),
        Command::Eval {
            set,
            lexical_only,
            max_words,
            overlap_words,
            min_words,
            lexical_weights,
            json,
        } => {
            let defaults = Chunker::default();
            let chunker = Chunker {
                max_words: max_words.unwrap_or(defaults.max_words),
                overlap_words: overlap_words.unwrap_or(defaults.overlap_words),
                min_words: min_words.unwrap_or(defaults.min_words),
            };
            let encoder = if lexical_only {
                None
            } else {
                Some(load(spec, &data_dir)?)
            };
            run_eval(
                encoder.as_ref(),
                spec,
                &set,
                &chunker,
                &lexical_weights,
                json,
            )
        }
    }
}

fn load(
    spec: &ModelSpec,
    data_dir: &std::path::Path,
) -> Result<Encoder, Box<dyn std::error::Error>> {
    let paths = ModelStore::from_env(data_dir)?.ensure(spec)?;
    Ok(Encoder::load(spec, &paths)?)
}

fn prepare(input: &Path, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let extraction = documents::extract(input, &Limits::default())?;
    let bytes = corpus::build(&extraction, &Chunker::default())?;
    std::fs::write(output, &bytes)?;
    let (header, _) = corpus::read_header(&bytes)?;
    println!("{}", serde_json::to_string_pretty(&header.documents)?);
    for skipped in &header.skipped {
        eprintln!("skipped {}: {:?}", skipped.name, skipped.reason);
    }
    eprintln!(
        "{} passages written to {}",
        header.passage_count,
        output.display()
    );
    Ok(())
}

fn build_index(
    encoder: &Encoder,
    spec: &ModelSpec,
    corpus_path: &std::path::Path,
    output: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let corpus_bytes = std::fs::read(corpus_path)?;
    let (_, body) = corpus::read_header(&corpus_bytes)?;
    let records = corpus::read_range(&corpus_bytes, body as u64, corpus_bytes.len() as u64)?;
    let inputs: Vec<_> = records.iter().map(PassageRecord::embedding_input).collect();
    let texts: Vec<&str> = inputs.iter().map(AsRef::as_ref).collect();
    let vectors = encoder.embed_passages(&texts)?;
    let block = VectorBlock::new(spec.dimension, 0, &vectors)?;
    let files = index::assemble(&corpus_bytes, &[block], spec)?;
    std::fs::create_dir_all(output)?;
    std::fs::write(output.join(index::VECTORS_FILE), &files.vectors)?;
    std::fs::write(output.join(index::PASSAGES_FILE), &files.passages)?;
    std::fs::write(output.join(index::MANIFEST_FILE), &files.manifest)?;
    eprintln!("{} passages indexed in {}", records.len(), output.display());
    Ok(())
}

fn search(
    encoder: &Encoder,
    dir: &Path,
    query: &str,
    k: usize,
    mode: Mode,
) -> Result<(), Box<dyn std::error::Error>> {
    let index = Index::open(dir)?;
    let vector = encoder.embed_query(query)?;
    for hit in search::search(&[&index], Some(&vector), query, k, mode)? {
        let passage = index.passage(hit.id)?;
        let line = serde_json::json!({
            "score": hit.score,
            "document": passage.document,
            "page": passage.page,
            "section": passage.section,
            "text": passage.text,
        });
        println!("{line}");
    }
    Ok(())
}

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
fn run_eval(
    encoder: Option<&Encoder>,
    spec: &ModelSpec,
    set: &Path,
    chunker: &Chunker,
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
            let inputs: Vec<_> = records.iter().map(PassageRecord::embedding_input).collect();
            let texts: Vec<&str> = inputs.iter().map(AsRef::as_ref).collect();
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
        "{} documents, {} passages, {} questions (chunks of {} words, overlap {}, min {})",
        header.documents.len(),
        header.passage_count,
        questions.len(),
        chunker.max_words,
        chunker.overlap_words,
        chunker.min_words
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
