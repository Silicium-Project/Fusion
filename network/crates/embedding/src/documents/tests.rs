use super::*;
use std::io::Write;
use zip::write::SimpleFileOptions;

/// A minimal PDF with one page of text per entry of `pages` (Helvetica).
pub(crate) fn pdf(pages: &[&str]) -> Vec<u8> {
    let page_count = pages.len();
    let mut objects: Vec<String> = Vec::new();
    let kids: Vec<String> = (0..page_count)
        .map(|i| format!("{} 0 R", 4 + 2 * i))
        .collect();
    objects.push("<< /Type /Catalog /Pages 2 0 R >>".into());
    objects.push(format!(
        "<< /Type /Pages /Kids [{}] /Count {page_count} >>",
        kids.join(" ")
    ));
    objects.push(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>".into(),
    );
    for (index, text) in pages.iter().enumerate() {
        let content = format!("BT /F1 12 Tf 72 720 Td ({text}) Tj ET");
        objects.push(format!(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {} 0 R >>",
            5 + 2 * index
        ));
        objects.push(format!(
            "<< /Length {} >>\nstream\n{content}\nendstream",
            content.len()
        ));
    }
    let mut out = b"%PDF-1.4\n".to_vec();
    let mut offsets = Vec::new();
    for (index, body) in objects.iter().enumerate() {
        offsets.push(out.len());
        out.extend(format!("{} 0 obj\n{body}\nendobj\n", index + 1).bytes());
    }
    let xref = out.len();
    out.extend(format!("xref\n0 {}\n0000000000 65535 f \n", objects.len() + 1).bytes());
    for offset in offsets {
        out.extend(format!("{offset:010} 00000 n \n").bytes());
    }
    out.extend(
        format!(
            "trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n",
            objects.len() + 1
        )
        .bytes(),
    );
    out
}

/// A `.docx` whose body is `body` (inner XML of `w:body`).
pub(crate) fn docx(body: &str) -> Vec<u8> {
    let xml = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>"#
    );
    zip_of(&[
        ("[Content_Types].xml", b"<Types/>".as_slice()),
        ("word/document.xml", xml.as_bytes()),
    ])
}

/// A ZIP of `(name, bytes)` entries.
pub(crate) fn zip_of(entries: &[(&str, &[u8])]) -> Vec<u8> {
    let mut writer = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
    for (name, bytes) in entries {
        writer
            .start_file(*name, SimpleFileOptions::default())
            .unwrap();
        writer.write_all(bytes).unwrap();
    }
    writer.finish().unwrap().into_inner()
}

fn texts(extraction: &Extraction) -> Vec<(String, Option<u32>, String)> {
    extraction
        .documents
        .iter()
        .flat_map(|d| {
            d.pages
                .iter()
                .map(|p| (d.name.clone(), p.number, p.text.clone()))
        })
        .collect()
}

#[test]
fn text_files_are_read_as_one_page_whatever_their_encoding() {
    let utf8 = extract_bytes(
        "notes.md",
        "\u{feff}# Titre\n\nUn  été   chaud".as_bytes(),
        &Limits::default(),
    );
    assert_eq!(
        texts(&utf8),
        vec![("notes.md".into(), None, "# Titre\n\nUn été chaud".into())]
    );
    let latin1 = extract_bytes("vieux.txt", b"caf\xe9 cr\xe8me", &Limits::default());
    assert_eq!(texts(&latin1)[0].2, "café crème");
}

#[test]
fn pdf_pages_keep_their_number() {
    let extraction = extract_bytes(
        "cours.pdf",
        &pdf(&["Premier chapitre", "Second chapitre"]),
        &Limits::default(),
    );
    let pages = texts(&extraction);
    assert_eq!(pages.len(), 2, "{extraction:?}");
    assert_eq!(pages[0].1, Some(1));
    assert!(pages[0].2.contains("Premier chapitre"));
    assert_eq!(pages[1].1, Some(2));
}

#[test]
fn a_pdf_without_text_is_reported_not_silently_dropped() {
    let extraction = extract_bytes("scan.pdf", &pdf(&[""]), &Limits::default());
    assert!(extraction.documents.is_empty());
    assert_eq!(
        extraction.skipped,
        vec![SkippedDocument {
            name: "scan.pdf".into(),
            reason: SkipReason::NoText
        }]
    );
}

#[test]
fn word_files_are_split_on_recorded_page_breaks() {
    let body = r#"<w:p><w:r><w:t>Article 1 &amp; suivants</w:t></w:r></w:p>
        <w:p><w:r><w:lastRenderedPageBreak/><w:t xml:space="preserve">Article&#160;2</w:t><w:tab/><w:t>fin</w:t></w:r></w:p>"#;
    let pages = texts(&extract_bytes(
        "contrat.docx",
        &docx(body),
        &Limits::default(),
    ));
    assert_eq!(
        pages,
        vec![
            (
                "contrat.docx".into(),
                Some(1),
                "Article 1 & suivants".into()
            ),
            ("contrat.docx".into(), Some(2), "Article 2 fin".into()),
        ]
    );
    let forced = r#"<w:p><w:r><w:t>Un</w:t><w:br w:type="page"/></w:r></w:p><w:p><w:r><w:lastRenderedPageBreak/><w:t>Deux</w:t></w:r></w:p>"#;
    let pages = texts(&extract_bytes(
        "forced.docx",
        &docx(forced),
        &Limits::default(),
    ));
    assert_eq!(
        pages.iter().map(|p| p.1).collect::<Vec<_>>(),
        vec![Some(1), Some(2)],
        "one page end, not two"
    );
    let single = texts(&extract_bytes(
        "note.docx",
        &docx("<w:p><w:r><w:t>Seule</w:t></w:r></w:p>"),
        &Limits::default(),
    ));
    assert_eq!(single, vec![("note.docx".into(), None, "Seule".into())]);
}

#[test]
fn word_heading_styles_become_markdown_headings() {
    let body = r#"<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>Bail</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Article 6</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Titre3"/></w:pPr><w:r><w:t>Préavis</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Un mois.</w:t></w:r></w:p>"#;
    let pages = texts(&extract_bytes("bail.docx", &docx(body), &Limits::default()));
    assert_eq!(pages[0].2, "# Bail\n## Article 6\n### Préavis\nUn mois.");
}

#[test]
fn archives_are_read_one_level_deep_and_skip_what_is_not_a_document() {
    let inner = zip_of(&[("deep.txt", b"profond")]);
    let archive = zip_of(&[
        ("dossier/a.txt", b"alpha"),
        (
            "dossier/b.docx",
            &docx("<w:p><w:r><w:t>beta</w:t></w:r></w:p>"),
        ),
        ("__MACOSX/._a.txt", b"junk"),
        ("dossier/.DS_Store", b"junk"),
        ("dossier/~$b.docx", b"lock"),
        ("slides.pptx", b"PK\x03\x04 not really"),
        ("nested.zip", &inner),
        ("vide.txt", b"   "),
    ]);
    let extraction = extract_bytes("envoi.zip", &archive, &Limits::default());
    let names: Vec<&str> = extraction
        .documents
        .iter()
        .map(|d| d.name.as_str())
        .collect();
    assert_eq!(names, vec!["dossier/a.txt", "dossier/b.docx"]);
    let skipped: Vec<(&str, SkipReason)> = extraction
        .skipped
        .iter()
        .map(|s| (s.name.as_str(), s.reason))
        .collect();
    assert_eq!(
        skipped,
        vec![
            ("slides.pptx", SkipReason::UnsupportedFormat),
            ("nested.zip", SkipReason::UnsupportedFormat),
            ("vide.txt", SkipReason::NoText),
        ]
    );
}

#[test]
fn archives_are_bounded() {
    let archive = zip_of(&[
        ("a.txt", b"alpha"),
        ("b.txt", b"beta"),
        ("c.txt", &[b'x'; 64]),
    ]);
    let limits = Limits {
        max_files: 2,
        max_file_bytes: 32,
        max_total_bytes: 1_000,
    };
    let extraction = extract_bytes("envoi.zip", &archive, &limits);
    assert_eq!(extraction.documents.len(), 2);
    assert_eq!(extraction.skipped[0].reason, SkipReason::TooLarge);
    let limits = Limits {
        max_files: 10,
        max_file_bytes: 32,
        max_total_bytes: 6,
    };
    let extraction = extract_bytes("envoi.zip", &archive, &limits);
    assert_eq!(
        extraction.documents.len(),
        1,
        "alpha fits, beta would pass the total"
    );
}

#[test]
fn damaged_files_are_skipped() {
    let extraction = extract_bytes("faux.pdf", b"%PDF-1.4 garbage", &Limits::default());
    assert_eq!(extraction.skipped[0].reason, SkipReason::Unreadable);
    let extraction = extract_bytes("faux.docx", b"PK\x03\x04garbage", &Limits::default());
    assert_eq!(extraction.skipped[0].reason, SkipReason::Unreadable);
}

#[test]
fn whitespace_is_normalized_but_paragraphs_kept() {
    assert_eq!(
        normalize_whitespace("  a \t b\n\n\n c\u{0}d \n"),
        "a b\n\nc d"
    );
    assert_eq!(normalize_whitespace("\n\n  \n"), "");
}
