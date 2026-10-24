use super::*;
use crate::{
    corpus::{self, tests::sample_extraction},
    passages::Chunker,
    testing,
};

/// Index of a sample corpus, split in fragments of `per_fragment`.
fn sample_index(per_fragment: usize) -> (Vec<u8>, IndexFiles) {
    let encoder = testing::tiny_encoder().unwrap();
    let corpus_bytes = corpus::build(&sample_extraction(5), &Chunker::default()).unwrap();
    let (header, _) = corpus::read_header(&corpus_bytes).unwrap();
    let plans = corpus::plan_fragments(&corpus_bytes, per_fragment, 64, None).unwrap();
    let blocks: Vec<VectorBlock> = plans
        .iter()
        .map(|plan| {
            let records = corpus::read_range(&corpus_bytes, plan.start, plan.end).unwrap();
            let inputs: Vec<_> = records
                .iter()
                .map(|r| r.embedding_input(&header.documents))
                .collect();
            let texts: Vec<&str> = inputs.iter().map(String::as_str).collect();
            let vectors = encoder.embed_passages(&texts).unwrap();
            VectorBlock::new(testing::TINY.dimension, plan.first_id, &vectors).unwrap()
        })
        .collect();
    let files = assemble(&corpus_bytes, &blocks, &testing::TINY).unwrap();
    (corpus_bytes, files)
}

#[test]
fn an_assembled_index_has_every_passage_in_order() {
    let (_, files) = sample_index(2);
    let index = Index::from_files(files.clone()).unwrap();
    assert_eq!(index.manifest.passage_count, 6);
    assert_eq!(index.manifest.documents.len(), 2);
    assert_eq!(index.manifest.skipped.len(), 1);
    assert_eq!(files.vectors.len(), 6 * testing::TINY.dimension * 4);
    let last = index.passage(5).unwrap();
    assert_eq!(
        (last.document.as_str(), last.page, last.text.as_str()),
        ("notes.txt", None, "mes notes")
    );
    assert_eq!(index.passage(0).unwrap().page, Some(1));
    assert!(index.passage(6).is_err());
}

#[test]
fn the_split_changes_vectors_by_rounding_only() {
    let (one, four) = (sample_index(1).1, sample_index(4).1);
    assert_eq!(one.manifest, four.manifest);
    assert_eq!(one.passages, four.passages);
    // Batches of different lengths are padded differently: the vectors
    // differ in their last bits, which is why verification compares them
    // by cosine and not by hash.
    let (one, four) = (
        Index::from_files(one).unwrap(),
        Index::from_files(four).unwrap(),
    );
    let d = testing::TINY.dimension;
    for (left, right) in one
        .vectors
        .chunks_exact(d)
        .zip(four.vectors.chunks_exact(d))
    {
        assert!(crate::vectors::cosine(left, right) > 0.99999);
    }
}

#[test]
fn search_finds_the_passage_of_the_same_text_first() {
    let (_, files) = sample_index(3);
    let index = Index::from_files(files).unwrap();
    let encoder = testing::tiny_encoder().unwrap();
    let wanted = index.passage(5).unwrap();
    let input = corpus::embedding_text(
        &corpus::document_title(&wanted.document),
        &wanted.section,
        &wanted.text,
    );
    let query = encoder.embed_passages(&[input.as_str()]).unwrap().remove(0);
    let hits = index.search(&query, 3).unwrap();
    assert_eq!(hits.len(), 3);
    assert_eq!(hits[0].id, 5);
    assert!(hits[0].score > 0.9999);
    assert!(hits.windows(2).all(|pair| pair[0].score >= pair[1].score));
    assert!(index.search(&[1.0], 3).is_err(), "wrong dimension");
}

#[test]
fn assembly_refuses_missing_or_misplaced_vectors() {
    let corpus_bytes = corpus::build(&sample_extraction(1), &Chunker::default()).unwrap();
    let d = testing::TINY.dimension;
    let unit = |i: usize| {
        let mut v = vec![0.0; d];
        v[i] = 1.0;
        v
    };
    let one = VectorBlock::new(d, 0, &[unit(0)]).unwrap();
    assert!(
        assemble(&corpus_bytes, std::slice::from_ref(&one), &testing::TINY).is_err(),
        "2 passages"
    );
    let misplaced = VectorBlock::new(d, 5, &[unit(1)]).unwrap();
    assert!(assemble(&corpus_bytes, &[one.clone(), misplaced], &testing::TINY).is_err());
    let second = VectorBlock::new(d, 1, &[unit(1)]).unwrap();
    assert!(assemble(&corpus_bytes, &[one, second], &testing::TINY).is_ok());
}

#[test]
fn files_that_disagree_are_refused() {
    let (_, files) = sample_index(2);
    let mut short = files.clone();
    short.vectors.truncate(short.vectors.len() - 4);
    assert!(Index::from_files(short).is_err());
    let mut fewer = files;
    fewer.passages = fewer
        .passages
        .splitn(2, |b| *b == b'\n')
        .nth(1)
        .unwrap()
        .to_vec();
    assert!(Index::from_files(fewer).is_err());
}

#[test]
fn top_k_keeps_the_best_and_breaks_ties_by_key() {
    let items = [(3u64, 0.5), (1, 0.9), (2, 0.5), (4, f32::NAN), (5, 0.1)];
    assert_eq!(
        top_k(items.into_iter(), 3),
        vec![(1, 0.9), (2, 0.5), (3, 0.5)]
    );
    assert!(top_k(items.into_iter(), 0).is_empty());
    assert_eq!(top_k(items.into_iter(), 10).len(), 4, "NaN is dropped");
}
