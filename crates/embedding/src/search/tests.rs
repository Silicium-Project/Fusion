use super::*;
use crate::{
    corpus,
    documents::{Document, Extraction, Page},
    index,
    passages::Chunker,
    testing,
    vectors::VectorBlock,
};

/// An index of `texts` (one document per text) with the tiny model.
fn index_of(texts: &[&str]) -> Index {
    let extraction = Extraction {
        documents: texts
            .iter()
            .enumerate()
            .map(|(n, text)| Document {
                name: format!("doc{n}.txt"),
                pages: vec![Page {
                    number: None,
                    text: text.to_string(),
                }],
            })
            .collect(),
        skipped: Vec::new(),
    };
    let bytes = corpus::build(&extraction, &Chunker::default()).unwrap();
    let (header, body) = corpus::read_header(&bytes).unwrap();
    let records = corpus::read_range(&bytes, body as u64, bytes.len() as u64).unwrap();
    let encoder = testing::tiny_encoder().unwrap();
    let inputs: Vec<_> = records
        .iter()
        .map(|r| r.embedding_input(&header.documents))
        .collect();
    let texts: Vec<&str> = inputs.iter().map(String::as_str).collect();
    let vectors = encoder.embed_passages(&texts).unwrap();
    let block = VectorBlock::new(testing::TINY.dimension, 0, &vectors).unwrap();
    Index::from_files(index::assemble(&bytes, &[block], &testing::TINY).unwrap()).unwrap()
}

#[test]
fn keywords_find_an_exact_number_the_tiny_model_cannot() {
    let a = index_of(&["le chat de la maison", "le loyer est de 780 euros"]);
    let b = index_of(&["la voiture du client", "le chien et le chat"]);
    let encoder = testing::tiny_encoder().unwrap();
    let vector = encoder.embed_query("780").unwrap();
    let lexical = search(&[&a, &b], None, "780", 5, Mode::Lexical).unwrap();
    assert_eq!((lexical[0].index, lexical[0].id), (0, 1));
    assert_eq!(lexical.len(), 1, "only passages with the term");
    // Every result, so that the counts do not depend on the margin.
    let all = Tuning {
        margin: None,
        ..Tuning::default()
    };
    let hybrid = search_tuned(&[&a, &b], Some(&vector), "780", 3, Mode::Hybrid, &all).unwrap();
    assert_eq!(
        (hybrid[0].index, hybrid[0].id),
        (0, 1),
        "keyword match first"
    );
    assert_eq!(hybrid.len(), 3);
    assert!(search(&[&a], None, "780", 3, Mode::Hybrid).is_err());
    let auto = search_tuned(&[&a, &b], Some(&vector), "780", 3, Mode::Auto, &all).unwrap();
    assert_eq!(auto, hybrid, "a number: keywords too");
    let vector = encoder.embed_query("le chat").unwrap();
    assert_eq!(
        search(&[&a, &b], Some(&vector), "le chat", 3, Mode::Auto).unwrap(),
        search(&[&a, &b], Some(&vector), "le chat", 3, Mode::Dense).unwrap(),
        "no exact token: meaning only"
    );
    let dense = search_tuned(&[&a, &b], Some(&vector), "780", 4, Mode::Dense, &all).unwrap();
    assert_eq!(dense.len(), 4);
}

#[test]
fn overlapping_neighbours_are_shown_once() {
    let words: Vec<String> = (0..400).map(|n| format!("mot{n}")).collect();
    let index = index_of(&[&words.join(" ")]);
    let all = search(&[&index], None, "mot125 mot140", 10, Mode::Lexical).unwrap();
    let ids: Vec<u64> = all.iter().map(|f| f.id).collect();
    assert_eq!(
        ids.len(),
        1,
        "mot125 and mot140 are in two overlapping windows: {ids:?}"
    );
}

fn found(index: usize, id: u64) -> Found {
    Found {
        index,
        id,
        score: 0.0,
    }
}

#[test]
fn fusion_favours_passages_found_by_both_rankings() {
    let dense = [found(0, 1), found(0, 2), found(0, 3)];
    let lexical = [found(0, 3), found(0, 4)];
    let fused: Vec<u64> = fuse(&[(&dense, 1.0), (&lexical, 1.0)])
        .iter()
        .map(|f| f.id)
        .collect();
    assert_eq!(fused[0], 3, "found by both");
    assert_eq!(fused[1], 1, "first of a ranking");
    assert_eq!(fused[2..], [2, 4], "equal scores keep the smaller id first");
}

#[test]
fn a_lighter_ranking_counts_less() {
    let dense = [found(0, 1), found(0, 2)];
    let lexical = [found(0, 2), found(0, 1)];
    let order = |weight| -> Vec<u64> {
        fuse(&[(&dense, 1.0), (&lexical, weight)])
            .iter()
            .map(|f| f.id)
            .collect()
    };
    assert_eq!(order(0.5), [1, 2], "the meaning decides");
    assert_eq!(order(2.0), [2, 1], "the keywords decide");
}

#[test]
fn exact_tokens_are_numbers_codes_and_acronyms() {
    for query in [
        "article 9",
        "l'erreur E3",
        "positions GPS",
        "port TCP ?",
        "60 €",
    ] {
        assert!(has_exact_terms(query), "{query}");
    }
    for query in ["Comment résilier le contrat ?", "Le PC", "Été", "A b"] {
        assert_eq!(has_exact_terms(query), query == "Le PC", "{query}");
    }
}

#[test]
fn overlap_is_detected_from_the_start_of_the_later_window() {
    let earlier = "a b c d e f g h i j k l";
    assert!(continues(earlier, "e f g h i j k l m n"));
    assert!(!continues(earlier, "x f g h i j k l m n"));
    assert!(!continues(earlier, "e f g"), "too short to tell");
}

#[test]
fn results_far_below_the_best_are_dropped_except_keyword_matches() {
    let index = index_of(&[
        "le chat de la maison",
        "la voiture rouge",
        "le loyer de 780 euros",
    ]);
    let encoder = testing::tiny_encoder().unwrap();
    let first = index.passage(0).unwrap();
    let input = corpus::embedding_text(
        &corpus::document_title(&first.document),
        &first.section,
        &first.text,
    );
    let vector = encoder.embed_passages(&[input.as_str()]).unwrap().remove(0);
    assert!((index.similarity(0, &vector).unwrap() - 1.0).abs() < 1e-5);
    assert_eq!(index.similarity(9, &vector), None, "unknown passage");
    assert_eq!(index.similarity(0, &[1.0]), None, "wrong dimension");
    let all = || (0..3).map(|id| found(0, id)).collect::<Vec<_>>();
    let ids = |found: &[Found]| found.iter().map(|f| f.id).collect::<Vec<_>>();
    let mut kept = all();
    keep_relevant(&[&index], &vector, &mut kept, &[], 2.0);
    assert_eq!(ids(&kept), [0, 1, 2], "a wide margin keeps everything");
    let mut kept = all();
    keep_relevant(&[&index], &vector, &mut kept, &[], 0.0);
    assert_eq!(ids(&kept), [0], "no margin keeps the best only");
    let mut kept = all();
    keep_relevant(&[&index], &vector, &mut kept, &[(0, 2)], 0.0);
    assert_eq!(ids(&kept), [0, 2], "a keyword match stays");
}
