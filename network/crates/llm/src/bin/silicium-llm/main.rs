//! `silicium-llm`: the batch AI processing of Silicium on one machine.
//!
//! ```text
//! silicium-llm prepare request.json batch.jsonl          # check a request, write its batch
//! silicium-llm run batch.jsonl answers.jsonl --gguf model.gguf
//! silicium-llm compare batch.jsonl a.jsonl b.jsonl       # calibrate the verification
//! ```
//!
//! `run` uses the Ollama server of `--ollama` (default
//! `http://127.0.0.1:11434`), importing the pinned model from `--gguf` when
//! it is missing. `compare` gives the similarity of two runs of the same
//! batch (two machines, a GPU and a CPU...) item by item, and what share of
//! verifications would pass with the current thresholds.

use clap::{Parser, Subcommand};
use silicium_llm::{
    answers::{self, Answer},
    batch, compute,
    model::{self, LlmModel},
    ollama::Ollama,
    request::Request,
    similarity::{Thresholds, answer_similarity, sample_size},
};
use std::{path::PathBuf, process::ExitCode};

#[derive(Parser)]
#[command(name = "silicium-llm", about = "Batch AI processing of Silicium")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Checks a request (`silicium-llm-request/1`) and writes its batch.
    Prepare {
        request: PathBuf,
        batch: PathBuf,
        #[arg(long, default_value = "qwen2.5-1.5b-instruct")]
        model: String,
    },
    /// Answers every item of a batch with a local Ollama.
    Run {
        batch: PathBuf,
        answers: PathBuf,
        #[arg(long, default_value = "http://127.0.0.1:11434")]
        ollama: String,
        /// The pinned GGUF file, imported into Ollama when missing there.
        #[arg(long)]
        gguf: Option<PathBuf>,
    },
    /// Compares two answer files of the same batch.
    Compare {
        batch: PathBuf,
        first: PathBuf,
        second: PathBuf,
    },
    /// Serves a fake Ollama (tests and the local end-to-end check).
    #[cfg(feature = "test-ollama")]
    FakeOllama {
        #[arg(long, default_value = "127.0.0.1:11435")]
        bind: String,
        /// Answer nonsense, as a cheating worker would.
        #[arg(long)]
        liar: bool,
    },
}

#[tokio::main]
async fn main() -> ExitCode {
    match run(Cli::parse().command).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

async fn run(command: Command) -> Result<(), String> {
    match command {
        Command::Prepare {
            request,
            batch: output,
            model,
        } => {
            let model = find_model(&model)?;
            let bytes = std::fs::read(&request).map_err(|err| err.to_string())?;
            let request = Request::parse(&bytes).map_err(|err| err.to_string())?;
            let bytes = batch::build(&request, model.id).map_err(|err| err.to_string())?;
            std::fs::write(&output, bytes).map_err(|err| err.to_string())?;
            println!("{} items", request.items.len());
            Ok(())
        }
        Command::Run {
            batch: input,
            answers: output,
            ollama,
            gguf,
        } => {
            let bytes = std::fs::read(&input).map_err(|err| err.to_string())?;
            let (header, items) = batch::read_all(&bytes).map_err(|err| err.to_string())?;
            let model = find_model(&header.model)?;
            let ollama = Ollama::new(&ollama).map_err(|err| err.to_string())?;
            let version = ollama.version().await.map_err(|err| err.to_string())?;
            println!("Ollama {version}");
            if !ollama
                .has_model(model)
                .await
                .map_err(|err| err.to_string())?
            {
                let gguf = gguf.ok_or("model missing in Ollama: give its GGUF file with --gguf")?;
                println!("Importing {}…", model.ollama_name());
                ollama
                    .import(model, &gguf)
                    .await
                    .map_err(|err| err.to_string())?;
            }
            let started = std::time::Instant::now();
            let answers = compute::answer_all(&ollama, model, &header, &items)
                .await
                .map_err(|err| err.to_string())?;
            let bytes = answers::to_bytes(&answers).map_err(|err| err.to_string())?;
            std::fs::write(&output, bytes).map_err(|err| err.to_string())?;
            println!(
                "{} items in {:.1} s",
                answers.len(),
                started.elapsed().as_secs_f64()
            );
            Ok(())
        }
        Command::Compare {
            batch: input,
            first,
            second,
        } => compare(&input, &first, &second),
        #[cfg(feature = "test-ollama")]
        Command::FakeOllama { bind, liar } => {
            let behaviour = if liar {
                silicium_llm::testing::Behaviour::Liar
            } else {
                silicium_llm::testing::Behaviour::Honest
            };
            let (url, _) = silicium_llm::testing::spawn(&bind, behaviour)
                .await
                .map_err(|err| err.to_string())?;
            println!("Fake Ollama on {url}");
            std::future::pending::<()>().await;
            Ok(())
        }
    }
}

fn compare(input: &PathBuf, first: &PathBuf, second: &PathBuf) -> Result<(), String> {
    let bytes = std::fs::read(input).map_err(|err| err.to_string())?;
    let (header, items) = batch::read_all(&bytes).map_err(|err| err.to_string())?;
    let load = |path: &PathBuf| -> Result<Vec<Answer>, String> {
        let bytes = std::fs::read(path).map_err(|err| err.to_string())?;
        answers::check(
            &bytes,
            0,
            items.len() as u64,
            &header.output,
            header.max_tokens,
        )
        .map_err(|err| format!("{}: {err}", path.display()))
    };
    let (a, b) = (load(first)?, load(second)?);
    let scores: Vec<f64> = a
        .iter()
        .zip(&b)
        .map(|(a, b)| answer_similarity(&header.output, &a.output, &b.output))
        .collect();
    let mut sorted = scores.clone();
    sorted.sort_by(f64::total_cmp);
    let quantile = |q: f64| sorted[((sorted.len() - 1) as f64 * q).round() as usize];
    let identical = scores.iter().filter(|score| **score >= 1.0).count();
    println!("{} items, {identical} identical answers", scores.len());
    println!(
        "similarity: min {:.3}  p5 {:.3}  p25 {:.3}  median {:.3}  mean {:.3}",
        quantile(0.0),
        quantile(0.05),
        quantile(0.25),
        quantile(0.5),
        scores.iter().sum::<f64>() / scores.len() as f64
    );
    // Verifications over consecutive fragments of 16 items, every item of
    // the sample size drawn in turn: the share that would pass.
    let thresholds = Thresholds::for_output(&header.output);
    let fragment = 16.min(scores.len());
    let k = sample_size(&header.output, fragment);
    let windows: Vec<&[f64]> = scores.windows(k).step_by(k).collect();
    let passed = windows
        .iter()
        .filter(|window| thresholds.accept(window))
        .count();
    println!(
        "verifications of {k} items: {passed} / {} would pass (mean ≥ {}, each ≥ {})",
        windows.len(),
        thresholds.min_mean,
        thresholds.min_item
    );
    Ok(())
}

fn find_model(id: &str) -> Result<&'static LlmModel, String> {
    model::find(id).ok_or_else(|| format!("unknown model {id}"))
}
