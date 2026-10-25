use super::*;
use crate::{
    testing,
    vectors::{cosine, dot},
};

#[test]
fn vectors_are_unit_length_and_deterministic() {
    let encoder = testing::tiny_encoder().unwrap();
    let texts = [
        "le client peut résilier le contrat",
        "un chat et un chien",
        "paris lyon train",
    ];
    let first = encoder.embed_passages(&texts).unwrap();
    let again = testing::tiny_encoder()
        .unwrap()
        .embed_passages(&texts)
        .unwrap();
    assert_eq!(first.len(), 3);
    for (vector, same) in first.iter().zip(&again) {
        assert_eq!(vector.len(), testing::TINY.dimension);
        assert!((dot(vector, vector) - 1.0).abs() < 1e-5);
        assert_eq!(vector, same, "another process builds the same model");
    }
    assert!(
        cosine(&first[0], &first[1]) < 0.999,
        "different texts, different vectors"
    );
}

#[test]
fn a_text_has_the_same_vector_alone_or_in_a_padded_batch() {
    let encoder = testing::tiny_encoder().unwrap();
    let batch = encoder
        .embed_passages(&[
            "contrat",
            "le client peut mettre fin à un abonnement par lettre recommandée",
        ])
        .unwrap();
    let alone = encoder.embed_passages(&["contrat"]).unwrap();
    // What a verifier relies on: padding does not change a vector beyond
    // rounding.
    assert!(cosine(&batch[0], &alone[0]) > 0.99999);
}

#[test]
fn queries_and_passages_get_their_prefix() {
    let encoder = testing::tiny_encoder().unwrap();
    let query = encoder.embed_query("contrat").unwrap();
    let passage = encoder.embed_passages(&["contrat"]).unwrap().remove(0);
    assert_ne!(query, passage);
}

#[test]
fn long_texts_are_truncated_not_refused() {
    let encoder = testing::tiny_encoder().unwrap();
    let long = vec!["contrat"; 1_000].join(" ");
    assert_eq!(encoder.embed_passages(&[long.as_str()]).unwrap().len(), 1);
}

#[test]
fn more_texts_than_a_batch_keep_their_order() {
    let encoder = testing::tiny_encoder().unwrap();
    let words = ["chat", "chien", "voiture", "maison"];
    let texts: Vec<&str> = (0..BATCH_SIZE + 3).map(|i| words[i % 4]).collect();
    let vectors = encoder.embed_passages(&texts).unwrap();
    assert_eq!(vectors.len(), texts.len());
    assert!(
        cosine(&vectors[BATCH_SIZE], &vectors[0]) > 0.99999,
        "same word as the first"
    );
}

#[test]
fn a_model_is_loaded_from_files_only_when_their_hashes_match() {
    let dir = std::env::temp_dir().join(format!("silicium-encoder-{}", std::process::id()));
    let (spec, paths) = testing::write_tiny_files(&dir).unwrap();
    let loaded = Encoder::load(&spec, &paths).unwrap();
    let built = testing::tiny_encoder().unwrap();
    assert_eq!(
        loaded.embed_query("contrat").unwrap(),
        built.embed_query("contrat").unwrap()
    );
    std::fs::write(&paths.tokenizer, b"{}").unwrap();
    assert!(Encoder::load(&spec, &paths).is_err(), "changed on disk");
}
