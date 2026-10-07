//! Checks with the real model (`multilingual-e5-small`, 490 MB downloaded
//! once). Ignored by default; run on a machine with Internet access:
//!
//! ```text
//! cargo test -p silicium-embedding --release --test real_model -- --ignored
//! ```
//!
//! The files go to `SILICIUM_MODEL_DIR`, or `target/models`.

use silicium_embedding::{
    encoder::Encoder,
    model::{MULTILINGUAL_E5_SMALL, store::ModelStore},
    vectors::{cosine, dot},
};
use std::path::PathBuf;

fn encoder() -> Encoder {
    let data_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../target");
    let store = ModelStore::from_env(&data_dir).expect("model store");
    let paths = store.ensure(&MULTILINGUAL_E5_SMALL).expect("download");
    Encoder::load(&MULTILINGUAL_E5_SMALL, &paths).expect("load")
}

#[test]
#[ignore = "downloads the 490 MB model"]
fn the_real_model_ranks_passages_by_meaning() {
    let encoder = encoder();
    let passages = [
        "Le client peut mettre fin à l'abonnement par lettre recommandée avec un préavis de trente jours.",
        "La tarte aux pommes se cuit quarante minutes à 180 degrés.",
        "Le train pour Lyon part de la gare de Lyon à Paris.",
    ];
    let vectors = encoder.embed_passages(&passages).unwrap();
    for vector in &vectors {
        assert_eq!(vector.len(), 384);
        assert!((dot(vector, vector) - 1.0).abs() < 1e-4);
    }
    let query = encoder
        .embed_query("comment résilier le contrat ?")
        .unwrap();
    let scores: Vec<f32> = vectors.iter().map(|v| dot(&query, v)).collect();
    assert!(scores[0] > scores[1] && scores[0] > scores[2], "{scores:?}");
    let english = encoder
        .embed_query("how do I cancel my subscription?")
        .unwrap();
    assert!(
        dot(&english, &vectors[0]) > dot(&english, &vectors[1]),
        "multilingual"
    );
}

#[test]
#[ignore = "downloads the 490 MB model"]
fn batching_changes_vectors_by_rounding_only() {
    let encoder = encoder();
    let texts = [
        "court",
        "un texte nettement plus long que le premier, pour que le lot soit complété",
    ];
    let batch = encoder.embed_passages(&texts).unwrap();
    let alone = encoder.embed_passages(&texts[..1]).unwrap();
    let similarity = cosine(&batch[0], &alone[0]);
    assert!(
        similarity > MULTILINGUAL_E5_SMALL.min_verification_cosine,
        "{similarity}"
    );
}
