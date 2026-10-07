package documents

import (
	"archive/zip"
	"bytes"
	"mime/multipart"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

type upload struct {
	name    string
	content []byte
}

// headers builds the multipart file headers a browser would send.
func headers(t *testing.T, uploads ...upload) []*multipart.FileHeader {
	t.Helper()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	for _, file := range uploads {
		part, err := writer.CreateFormFile("files", file.name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := part.Write(file.content); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	form, err := multipart.NewReader(&body, writer.Boundary()).ReadForm(1 << 20)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = form.RemoveAll() })
	return form.File["files"]
}

func zipEntries(t *testing.T, path string) map[string]string {
	t.Helper()
	archive, err := zip.OpenReader(path)
	if err != nil {
		t.Fatal(err)
	}
	defer archive.Close()
	entries := map[string]string{}
	for _, entry := range archive.File {
		reader, err := entry.Open()
		if err != nil {
			t.Fatal(err)
		}
		var content bytes.Buffer
		_, _ = content.ReadFrom(reader)
		reader.Close()
		entries[entry.Name] = content.String()
	}
	return entries
}

func TestDocumentsAreBundledUnderUniqueNames(t *testing.T) {
	dir := t.TempDir()
	path, err := Store(dir, headers(t,
		upload{`C:\Users\me\cours.pdf`, []byte("%PDF a")},
		upload{"cours.pdf", []byte("%PDF b")},
		upload{"Notes.MD", []byte("# notes")},
	))
	if err != nil {
		t.Fatal(err)
	}
	if path != filepath.Join(dir, BundleName) {
		t.Fatalf("stored at %s", path)
	}
	entries := zipEntries(t, path)
	names := make([]string, 0, len(entries))
	for name := range entries {
		names = append(names, name)
	}
	sort.Strings(names)
	if strings.Join(names, "|") != "Notes.MD|cours (2).pdf|cours.pdf" {
		t.Fatalf("entries = %v", names)
	}
	if entries["cours (2).pdf"] != "%PDF b" {
		t.Fatalf("second upload content = %q", entries["cours (2).pdf"])
	}
}

func TestASingleZipIsKeptAsIs(t *testing.T) {
	var archive bytes.Buffer
	writer := zip.NewWriter(&archive)
	entry, _ := writer.Create("dossier/a.txt")
	_, _ = entry.Write([]byte("alpha"))
	_ = writer.Close()
	path, err := Store(t.TempDir(), headers(t, upload{"dossier.zip", archive.Bytes()}))
	if err != nil {
		t.Fatal(err)
	}
	stored, _ := os.ReadFile(path)
	if !bytes.Equal(stored, archive.Bytes()) {
		t.Fatal("the uploaded ZIP must be stored unchanged")
	}
}

func TestSubmissionsTheNodeCannotReadAreRefusedWithAMessage(t *testing.T) {
	cases := map[string][]upload{
		"pas pris en charge": {{"slides.pptx", []byte("x")}},
		"mais pas les deux":  {{"a.zip", []byte("PK")}, {"b.pdf", []byte("%PDF")}},
	}
	for want, uploads := range cases {
		_, err := Store(t.TempDir(), headers(t, uploads...))
		if !strings.Contains(UserMessage(err), want) {
			t.Fatalf("%v: got %v, want a message containing %q", uploads, err, want)
		}
	}
	if _, err := Store(t.TempDir(), nil); UserMessage(err) == "" {
		t.Fatal("no file must be refused with a message")
	}
}

func TestStoredDocumentsAreServedBackByTheirNodeName(t *testing.T) {
	dir := t.TempDir()
	path, err := Store(dir, headers(t, upload{"contrat.pdf", []byte("%PDF-1.4 contrat")}, upload{"notes.txt", []byte("notes")}))
	if err != nil {
		t.Fatal(err)
	}
	document, err := Open(path, "contrat.pdf")
	if err != nil {
		t.Fatal(err)
	}
	if document.ContentType != "application/pdf" || string(document.Content) != "%PDF-1.4 contrat" {
		t.Fatalf("document = %+v", document)
	}
	if text, _ := Open(path, "notes.txt"); !strings.HasPrefix(text.ContentType, "text/plain") {
		t.Fatalf("text content type = %q", text.ContentType)
	}
	for _, missing := range []string{"", "../contrat.pdf", "absent.pdf"} {
		if _, err := Open(path, missing); err != ErrNotFound {
			t.Fatalf("Open(%q) = %v, want ErrNotFound", missing, err)
		}
	}
}

func TestAFinishedIndexIsExportedWithAGuide(t *testing.T) {
	dir := t.TempDir()
	for _, name := range IndexFiles {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(name), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	var output bytes.Buffer
	if err := WriteIndexArchive(&output, dir); err != nil {
		t.Fatal(err)
	}
	exported := filepath.Join(t.TempDir(), "index.zip")
	_ = os.WriteFile(exported, output.Bytes(), 0o600)
	entries := zipEntries(t, exported)
	if len(entries) != 4 || entries["vectors.f32"] != "vectors.f32" || !strings.Contains(entries["LISEZMOI.txt"], "numpy") {
		t.Fatalf("entries = %v", entries)
	}
	if err := WriteIndexArchive(&output, t.TempDir()); err == nil {
		t.Fatal("a missing index must fail")
	}
}

func TestNamesMatchWhatTheNodeReports(t *testing.T) {
	if runes := []rune(cp437High); len(runes) != 128 || runes[0x82-0x80] != 'é' {
		t.Fatalf("code page 437 table has %d characters", len(runes))
	}
	var archive bytes.Buffer
	writer := zip.NewWriter(&archive)
	for _, header := range []*zip.FileHeader{
		{Name: "R\x82sum\x82.pdf", NonUTF8: true},
		{Name: `dossier\notes.txt`},
	} {
		entry, _ := writer.CreateHeader(header)
		_, _ = entry.Write([]byte(header.Name))
	}
	_ = writer.Close()
	path := filepath.Join(t.TempDir(), BundleName)
	_ = os.WriteFile(path, archive.Bytes(), 0o600)
	for _, name := range []string{"Résumé.pdf", "dossier/notes.txt"} {
		if _, err := Open(path, name); err != nil {
			t.Fatalf("Open(%q) = %v", name, err)
		}
	}
}

func TestHiddenOrLockFileNamesAreKeptReadable(t *testing.T) {
	for raw, want := range map[string]string{".notes.md": "notes.md", "~$contrat.docx": "contrat.docx", "...": "document", `C:\x\cours.pdf`: "cours.pdf"} {
		if got := baseName(raw); got != want {
			t.Fatalf("baseName(%q) = %q, want %q", raw, got, want)
		}
	}
}
