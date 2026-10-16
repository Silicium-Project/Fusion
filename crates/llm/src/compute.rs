//! Answering items: what a worker does for its fragment and a verifier for
//! the items it recomputes, with the same code.

use crate::{
    Error, Result,
    answers::Answer,
    batch::{BatchHeader, Item},
    model::LlmModel,
    ollama::Ollama,
    prompt,
};
use std::time::Duration;

/// Longest generation of one item (a slow CPU, a long item and the longest
/// answer).
pub const ITEM_TIMEOUT: Duration = Duration::from_secs(15 * 60);

/// The answer to `item` in the job described by `header`.
pub async fn answer(
    ollama: &Ollama,
    model: &LlmModel,
    header: &BatchHeader,
    item: &Item,
) -> Result<Answer> {
    if header.model != model.id {
        return Err(Error::Format(format!(
            "batch for model {}, not {}",
            header.model, model.id
        )));
    }
    let schema = prompt::schema(&header.output);
    let generation = ollama
        .generate(
            model,
            &prompt::prompt(header, &item.text),
            header.max_tokens,
            schema.as_ref(),
            ITEM_TIMEOUT,
        )
        .await?;
    Ok(Answer {
        id: item.id,
        output: prompt::read_answer(&header.output, &generation.text),
    })
}

/// The answers to `items`, one after the other (Ollama runs one generation
/// at a time on a desktop; parallel requests would only queue).
pub async fn answer_all(
    ollama: &Ollama,
    model: &LlmModel,
    header: &BatchHeader,
    items: &[Item],
) -> Result<Vec<Answer>> {
    let mut answers = Vec::with_capacity(items.len());
    for item in items {
        answers.push(answer(ollama, model, header, item).await?);
    }
    Ok(answers)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        batch,
        model::QWEN2_5_1_5B_INSTRUCT as MODEL,
        request::{OutputSpec, Request, Source},
        testing::{self, Behaviour},
    };

    fn header(output: OutputSpec) -> (BatchHeader, Vec<Item>) {
        let request = Request {
            task: "free".into(),
            instruction: "Résume.".into(),
            output,
            max_tokens: 64,
            source: Source::default(),
            items: vec![
                "Le chat dort sur le canapé du salon.".into(),
                "Il pleut.".into(),
            ],
        };
        batch::read_all(&batch::build(&request, MODEL.id).unwrap()).unwrap()
    }

    #[tokio::test]
    async fn the_model_is_imported_once_then_items_are_answered() {
        let (url, fake) = testing::spawn("127.0.0.1:0", Behaviour::Honest)
            .await
            .unwrap();
        let ollama = Ollama::new(&url).unwrap();
        assert_eq!(ollama.version().await.unwrap(), "0.0.0-fake");
        assert!(!ollama.has_model(&MODEL).await.unwrap());
        let gguf =
            std::env::temp_dir().join(format!("silicium-llm-test-{}.gguf", std::process::id()));
        std::fs::write(&gguf, b"GGUF fake weights").unwrap();
        ollama.import(&MODEL, &gguf).await.unwrap();
        ollama.import(&MODEL, &gguf).await.unwrap();
        let _ = std::fs::remove_file(&gguf);
        assert_eq!(fake.blob_count(), 1, "the blob is uploaded once");
        assert!(ollama.has_model(&MODEL).await.unwrap());

        let (header, items) = header(OutputSpec::Text);
        let answers = answer_all(&ollama, &MODEL, &header, &items).await.unwrap();
        assert_eq!(
            answers[0].output,
            "Réponse : Le chat dort sur le canapé du salon."
        );
        assert_eq!(answers[1].id, 1);
        assert_eq!(fake.generations(), 2);

        let (header, items) = header_labels();
        let answers = answer_all(&ollama, &MODEL, &header, &items).await.unwrap();
        assert!(
            answers
                .iter()
                .all(|answer| answer.output == "oui" || answer.output == "non")
        );
    }

    fn header_labels() -> (BatchHeader, Vec<Item>) {
        header(OutputSpec::Label {
            labels: vec!["oui".into(), "non".into()],
        })
    }

    #[tokio::test]
    async fn a_batch_of_another_model_is_refused() {
        let (url, _) = testing::spawn("127.0.0.1:0", Behaviour::Honest)
            .await
            .unwrap();
        let ollama = Ollama::new(&url).unwrap();
        let (mut header, items) = header(OutputSpec::Text);
        header.model = "other".into();
        assert!(answer(&ollama, &MODEL, &header, &items[0]).await.is_err());
    }

    #[tokio::test]
    async fn an_unreachable_ollama_is_an_error() {
        let ollama = Ollama::new("http://127.0.0.1:9").unwrap();
        assert!(matches!(ollama.version().await, Err(Error::Ollama(_))));
    }
}
