//! `silicium-embed`: the document-search pipeline on one machine, for
//! operators and for checking the network's results.
//!
//! ```text
//! silicium-embed prepare documents.zip -o corpus.jsonl   # files -> corpus
//! silicium-embed model fetch                             # download + check the model
//! silicium-embed index corpus.jsonl -o index/            # corpus -> index (all local)
//! silicium-embed search index/ "comment résilier ?"      # best passages, JSON lines
//! ```
//!
//! Model files are kept under `--data-dir/models` (default: the
//! `SILICIUM_DATA_DIR` directory, else the current one), or
//! `SILICIUM_MODEL_DIR`; see `silicium_embedding::model::store`.

use clap::{Parser, Subcommand};
use silicium_embedding::{
    corpus,
    documents::{self, Limits},
    encoder::Encoder,
    index::{self, Index},
    model::{self, ModelSpec, store::ModelStore},
    passages::Chunker,
    vectors::VectorBlock,
};
use std::{path::PathBuf, process::ExitCode};

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
        Command::Search { index, query, k } => search(&load(spec, &data_dir)?, &index, &query, k),
    }
}

fn load(
    spec: &ModelSpec,
    data_dir: &std::path::Path,
) -> Result<Encoder, Box<dyn std::error::Error>> {
    let paths = ModelStore::from_env(data_dir)?.ensure(spec)?;
    Ok(Encoder::load(spec, &paths)?)
}

fn prepare(
    input: &std::path::Path,
    output: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error>> {
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
    let texts: Vec<&str> = records.iter().map(|record| record.text.as_str()).collect();
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
    dir: &std::path::Path,
    query: &str,
    k: usize,
) -> Result<(), Box<dyn std::error::Error>> {
    let index = Index::open(dir)?;
    let vector = encoder.embed_query(query)?;
    for hit in index.search(&vector, k)? {
        let passage = index.passage(hit.id)?;
        let line = serde_json::json!({
            "score": hit.score,
            "document": passage.document,
            "page": passage.page,
            "text": passage.text,
        });
        println!("{line}");
    }
    Ok(())
}
