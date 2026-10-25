package documents

// Reading back what was stored: one document of a submission (opened from
// a search result), and the export of a finished index.

import (
	"archive/zip"
	"bytes"
	"errors"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"
)

// ErrNotFound: the submission has no document of that name.
var ErrNotFound = errors.New("document not found")

// IndexFiles are the files of a finished index, as the node writes them.
var IndexFiles = []string{"index.json", "vectors.f32", "passages.jsonl"}

// Document is one stored document, ready to send.
type Document struct {
	Name        string
	ContentType string
	Content     []byte
}

// Open returns the document `name` (as the node reports it in a search
// result) of the submission stored at `inputPath`.
func Open(inputPath, name string) (Document, error) {
	name = strings.TrimSpace(strings.ReplaceAll(name, "\\", "/"))
	if name == "" {
		return Document{}, ErrNotFound
	}
	if !strings.EqualFold(filepath.Ext(inputPath), ".zip") {
		// A submission stored before bundling: a single document.
		if name != filepath.Base(inputPath) {
			return Document{}, ErrNotFound
		}
		content, err := readLimited(inputPath)
		return Document{Name: name, ContentType: contentType(name), Content: content}, err
	}
	archive, err := zip.OpenReader(inputPath)
	if err != nil {
		return Document{}, err
	}
	defer archive.Close()
	for _, entry := range archive.File {
		if entryName(entry) != name || entry.FileInfo().IsDir() {
			continue
		}
		if entry.UncompressedSize64 > uint64(MaxUploadBytes) {
			return Document{}, ErrNotFound
		}
		content, err := readEntry(entry)
		return Document{Name: path.Base(name), ContentType: contentType(name), Content: content}, err
	}
	return Document{}, ErrNotFound
}

// WriteIndexArchive writes a ZIP of the index in `indexDir` to `w`, with a
// short guide to its formats.
func WriteIndexArchive(w io.Writer, indexDir string) error {
	archive := zip.NewWriter(w)
	for _, name := range IndexFiles {
		if err := addFile(archive, filepath.Join(indexDir, name), name); err != nil {
			_ = archive.Close()
			return err
		}
	}
	guide, err := archive.Create("LISEZMOI.txt")
	if err == nil {
		_, err = io.WriteString(guide, indexGuide)
	}
	if err != nil {
		_ = archive.Close()
		return err
	}
	return archive.Close()
}

func addFile(archive *zip.Writer, source, name string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	entry, err := archive.Create(name)
	if err != nil {
		return err
	}
	_, err = io.Copy(entry, input)
	return err
}

func readEntry(entry *zip.File) ([]byte, error) {
	reader, err := entry.Open()
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	return readAllLimited(reader)
}

func readLimited(path string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	return readAllLimited(file)
}

func readAllLimited(reader io.Reader) ([]byte, error) {
	var buffer bytes.Buffer
	written, err := io.Copy(&buffer, io.LimitReader(reader, MaxUploadBytes+1))
	if err != nil {
		return nil, err
	}
	if written > MaxUploadBytes {
		return nil, ErrNotFound
	}
	return buffer.Bytes(), nil
}

// entryName is the name of an archive entry as the node reports it:
// slashes only, and CP437 names (ZIPs made on Windows without the UTF-8
// flag) decoded as the node's ZIP reader decodes them.
func entryName(entry *zip.File) string {
	name := entry.Name
	if entry.NonUTF8 {
		name = decodeCP437(name)
	}
	return strings.ReplaceAll(name, "\\", "/")
}

func contentType(name string) string {
	switch strings.ToLower(path.Ext(name)) {
	case ".pdf":
		return "application/pdf"
	case ".docx":
		return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	case ".md", ".markdown", ".txt":
		return "text/plain; charset=utf-8"
	default:
		return "application/octet-stream"
	}
}

const indexGuide = `Index de recherche Silicium (format silicium-index/1)

index.json      le modèle, la dimension des vecteurs, les documents et les fichiers ignorés
passages.jsonl  un passage par ligne : id, document, page, texte
vectors.f32     un vecteur par passage, dans le même ordre, en float32 little-endian

Lire les vecteurs en Python :
    import json, numpy as np
    index = json.load(open("index.json"))
    vectors = np.fromfile("vectors.f32", dtype="<f4").reshape(-1, index["dimension"])

Les vecteurs sont de norme 1 : la similarité de deux passages est leur produit scalaire.
Pour chercher, une question se vectorise avec le même modèle et le préfixe "query: ".
`
