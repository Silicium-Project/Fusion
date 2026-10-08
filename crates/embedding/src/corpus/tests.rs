use super::*;
use crate::documents::{Document, Page};

pub(crate) fn sample_extraction(pages: usize) -> Extraction {
    Extraction {
        documents: vec![
            Document {
                name: "cours.pdf".into(),
                pages: (1..=pages as u32)
                    .map(|n| Page {
                        number: Some(n),
                        text: format!("page {n} du cours de droit"),
                    })
                    .collect(),
            },
            Document {
                name: "notes.txt".into(),
                pages: vec![Page {
                    number: None,
                    text: "mes notes".into(),
                }],
            },
        ],
        skipped: vec![SkippedDocument {
            name: "scan.pdf".into(),
            reason: SkipReason::NoText,
        }],
    }
}

#[test]
fn a_corpus_has_a_header_then_one_line_per_passage() {
    let bytes = build(&sample_extraction(3), &Chunker::default()).unwrap();
    let (header, body) = read_header(&bytes).unwrap();
    assert_eq!(header.passage_count, 4);
    assert_eq!(
        header.documents[0],
        DocumentEntry {
            name: "cours.pdf".into(),
            pages: 3,
            passages: 3
        }
    );
    assert_eq!(header.documents[1].passages, 1);
    assert_eq!(header.skipped.len(), 1);
    let records = read_range(&bytes, body as u64, bytes.len() as u64).unwrap();
    assert_eq!(records.len(), 4);
    assert_eq!(
        records[3],
        PassageRecord {
            id: 3,
            doc: 1,
            page: None,
            section: String::new(),
            text: "mes notes".into()
        }
    );
}

#[test]
fn building_is_deterministic() {
    let extraction = sample_extraction(5);
    assert_eq!(
        build(&extraction, &Chunker::default()).unwrap(),
        build(&extraction, &Chunker::default()).unwrap()
    );
}

#[test]
fn nothing_to_read_gives_a_message_for_the_user() {
    let scanned = Extraction {
        documents: vec![],
        skipped: vec![SkippedDocument {
            name: "scan.pdf".into(),
            reason: SkipReason::NoText,
        }],
    };
    let error = build(&scanned, &Chunker::default()).unwrap_err();
    assert!(error.user_message().unwrap().contains("images scannées"));
    let unsupported = Extraction {
        documents: vec![],
        skipped: vec![SkippedDocument {
            name: "a.pptx".into(),
            reason: SkipReason::UnsupportedFormat,
        }],
    };
    assert!(
        build(&unsupported, &Chunker::default())
            .unwrap_err()
            .user_message()
            .unwrap()
            .contains(".docx")
    );
}

#[test]
fn fragments_cover_every_passage_once_in_order() {
    let bytes = build(&sample_extraction(9), &Chunker::default()).unwrap();
    for (per_fragment, max, requested, expected) in [
        (3, 64, None, 4),
        (100, 64, None, 1),
        (1, 3, None, 3),
        (3, 64, Some(7), 7),
        (3, 64, Some(500), 10),
    ] {
        let plans = plan_fragments(&bytes, per_fragment, max, requested).unwrap();
        assert_eq!(plans.len(), expected, "{per_fragment} {max} {requested:?}");
        let mut next = 0;
        for plan in &plans {
            let records = read_range(&bytes, plan.start, plan.end).unwrap();
            assert_eq!(records.len() as u64, plan.count);
            assert_eq!(records[0].id, next);
            assert_eq!(plan.first_id, next);
            next += plan.count;
        }
        assert_eq!(next, 10);
        assert_eq!(plans.last().unwrap().end, bytes.len() as u64);
    }
}

#[test]
fn malformed_corpora_and_ranges_are_refused() {
    let bytes = build(&sample_extraction(2), &Chunker::default()).unwrap();
    assert!(
        read_header(b"{\"format\":\"other/1\",\"passage_count\":0,\"documents\":[]}\n").is_err()
    );
    assert!(read_header(b"no newline").is_err());
    assert!(read_range(&bytes, 0, bytes.len() as u64 + 1).is_err());
    let (_, body) = read_header(&bytes).unwrap();
    let mut gap = bytes[..body].to_vec();
    gap.extend(b"{\"id\":0,\"doc\":0,\"page\":1,\"text\":\"a\"}\n{\"id\":2,\"doc\":0,\"page\":1,\"text\":\"b\"}\n");
    assert!(
        read_range(&gap, body as u64, gap.len() as u64).is_err(),
        "ids must follow each other"
    );
    assert!(
        plan_fragments(&gap, 1, 8, None).is_err(),
        "header says 3 passages"
    );
}

#[test]
fn the_model_reads_title_section_and_text_without_repeats() {
    assert_eq!(embedding_text("", "", "texte"), "texte");
    assert_eq!(
        embedding_text("bail", "Article 6", "Le préavis"),
        "bail\nArticle 6\nLe préavis"
    );
    assert_eq!(
        embedding_text(
            "contrat de location",
            "Contrat de location meublé › Article 6",
            "Un mois"
        ),
        "Contrat de location meublé › Article 6\nUn mois",
        "title already in the section"
    );
    assert_eq!(
        embedding_text("bail", "Article 6", "Article 6 Le préavis"),
        "bail\nArticle 6 Le préavis",
        "heading already in the text"
    );
    assert_eq!(
        embedding_text("notice", "", "Notice du lave-linge"),
        "Notice du lave-linge"
    );
}

#[test]
fn a_document_title_comes_from_its_file_name() {
    assert_eq!(
        document_title("docs/contrat-de-bail.pdf"),
        "contrat de bail"
    );
    assert_eq!(
        document_title("C:\\dossier\\notice_L700.txt"),
        "notice L700"
    );
    assert_eq!(document_title(".bashrc"), ".bashrc");
    assert_eq!(document_title("sans extension"), "sans extension");
    let record = PassageRecord {
        id: 0,
        doc: 0,
        page: None,
        section: String::new(),
        text: "Un mois.".into(),
    };
    let documents = [DocumentEntry {
        name: "bail.md".into(),
        pages: 1,
        passages: 1,
    }];
    assert_eq!(record.embedding_input(&documents), "bail\nUn mois.");
    assert_eq!(record.embedding_input(&[]), "Un mois.");
}
