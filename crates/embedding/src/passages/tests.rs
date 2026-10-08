use super::*;
use crate::documents::Page;

fn words(prefix: &str, count: usize) -> String {
    (0..count)
        .map(|n| format!("{prefix}{n}"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn document(pages: &[(Option<u32>, &str)]) -> Document {
    Document {
        name: "doc.pdf".into(),
        pages: pages
            .iter()
            .map(|(number, text)| Page {
                number: *number,
                text: text.to_string(),
            })
            .collect(),
    }
}

fn chunker(max_words: usize, overlap_words: usize, min_words: usize) -> Chunker {
    Chunker {
        max_words,
        overlap_words,
        min_words,
    }
}

#[test]
fn headings_are_recognized_in_three_languages() {
    let cases = [
        ("## Préavis", Some((2, "Préavis"))),
        (
            "Article 6 - Congé et préavis",
            Some((2, "Article 6 - Congé et préavis")),
        ),
        ("ARTICLE 1er : Objet", Some((2, "ARTICLE 1er : Objet"))),
        ("Chapitre II", Some((1, "Chapitre II"))),
        ("§ 4 Kündigung", Some((2, "§ 4 Kündigung"))),
        ("§4 Kündigung", Some((2, "§4 Kündigung"))),
        ("Section 3: Warranty", Some((2, "Section 3: Warranty"))),
        ("2.3 Garanties", Some((2, "2.3 Garanties"))),
        ("1. Tranquillité", Some((1, "1. Tranquillité"))),
        ("IV. Résiliation", Some((1, "IV. Résiliation"))),
        (
            "CONDITIONS GÉNÉRALES DE VENTE",
            Some((1, "CONDITIONS GÉNÉRALES DE VENTE")),
        ),
    ];
    for (line, expected) in cases {
        let expected = expected.map(|(level, title)| (level, title.to_string()));
        assert_eq!(heading(line), expected, "{line}");
    }
}

#[test]
fn sentences_and_list_items_are_not_headings() {
    for line in [
        "Le locataire doit prévenir le bailleur.",
        "1. le locataire paie le loyer",
        "2 euros par mois",
        "Article premier du code civil, alinéa 2, dispose que le bail est conclu pour une durée déterminée.",
        "#hashtag",
        "OK",
        "Article sans numéro",
        "1999 fut une année",
        "2. Le locataire paie le loyer au plus tard le 5 du mois",
    ] {
        assert_eq!(heading(line), None, "{line}");
    }
}

#[test]
fn a_heading_starts_a_passage_and_names_the_following_ones() {
    let text = format!(
        "# Contrat\n{}\n## Article 1 - Durée\n{}\n## Article 2 - Loyer\n{}",
        words("i", 30),
        words("d", 30),
        words("l", 30)
    );
    let passages = chunker(100, 10, 5).passages(&[document(&[(Some(1), &text)])]);
    let summary: Vec<(&str, bool)> = passages
        .iter()
        .map(|p| {
            (
                p.section.as_str(),
                p.text.contains("d0") && p.text.contains("l0"),
            )
        })
        .collect();
    assert_eq!(
        summary,
        vec![
            ("Contrat", false),
            ("Contrat › Article 1 - Durée", false),
            ("Contrat › Article 2 - Loyer", false)
        ]
    );
    assert!(passages[1].text.starts_with("Article 1 - Durée d0"));
}

#[test]
fn a_long_section_is_cut_in_overlapping_windows_covering_every_word() {
    let text = words("w", 64);
    let passages = chunker(20, 5, 3).passages(&[document(&[(None, &text)])]);
    assert!(passages.len() >= 3);
    assert!(passages.iter().all(|p| p.text.split(' ').count() <= 23));
    assert!(
        passages[1].text.starts_with("w15 w16 w17 w18 w19 w20"),
        "5 words of overlap"
    );
    let all: std::collections::HashSet<&str> =
        passages.iter().flat_map(|p| p.text.split(' ')).collect();
    assert_eq!(all.len(), 64);
    assert!(passages.last().unwrap().text.ends_with("w63"));
}

#[test]
fn a_section_slightly_over_the_limit_is_not_cut() {
    let text = format!("{}\nfin de la page", words("w", 20));
    let passages = chunker(20, 0, 5).passages(&[document(&[(Some(3), &text)])]);
    assert_eq!(passages.len(), 1, "24 words: a tail of 4 would be useless");
    assert!(passages[0].text.ends_with("w19 fin de la page"));
    assert_eq!(
        chunker(20, 0, 5)
            .passages(&[document(&[(None, &words("w", 25))])])
            .len(),
        2
    );
}

#[test]
fn headings_without_text_between_them_stay_together() {
    let text = "# Contrat de location
## Article 1 - Parties
Le bailleur et le locataire.";
    let passages = Chunker::default().passages(&[document(&[(Some(1), text)])]);
    assert_eq!(passages.len(), 1);
    assert_eq!(
        passages[0].section,
        "Contrat de location › Article 1 - Parties"
    );
    assert_eq!(
        passages[0].text,
        "Contrat de location Article 1 - Parties Le bailleur et le locataire."
    );
}

#[test]
fn sections_continue_across_pages_and_passages_keep_their_page() {
    let passages = Chunker::default().passages(&[document(&[
        (
            Some(1),
            "## Article 5 - Dépôt de garantie\nLe dépôt est de 1 560 euros.",
        ),
        (Some(2), "Il est restitué dans un délai d'un mois."),
    ])]);
    let summary: Vec<(Option<u32>, &str)> = passages
        .iter()
        .map(|p| (p.page, p.section.as_str()))
        .collect();
    assert_eq!(
        summary,
        vec![
            (Some(1), "Article 5 - Dépôt de garantie"),
            (Some(2), "Article 5 - Dépôt de garantie")
        ]
    );
}

#[test]
fn only_the_three_innermost_headings_are_kept() {
    let text = "# A\n## B\n### C\n#### D\ntexte";
    let passages = Chunker::default().passages(&[document(&[(None, text)])]);
    assert_eq!(passages.last().unwrap().section, "B › C › D");
}

#[test]
fn passages_keep_their_document_and_page() {
    let documents = vec![
        document(&[(Some(1), "un"), (Some(2), "deux")]),
        Document {
            name: "b.txt".into(),
            pages: vec![Page {
                number: None,
                text: "trois".into(),
            }],
        },
    ];
    let passages = Chunker::default().passages(&documents);
    let summary: Vec<(usize, Option<u32>, &str)> = passages
        .iter()
        .map(|p| (p.document, p.page, p.text.as_str()))
        .collect();
    assert_eq!(
        summary,
        vec![(0, Some(1), "un"), (0, Some(2), "deux"), (1, None, "trois")]
    );
}
