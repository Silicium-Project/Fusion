// Package documents holds what the site does with the files of a document
// search ("Recherche dans mes documents"): it bundles the uploaded files
// into one ZIP for the Rust node, serves a document back from that ZIP
// when the user opens a search result, and exports the finished index.
//
// The node reads the documents itself (PDF, Word, text, Markdown); this
// package only checks names, extensions and sizes, so that a user gets a
// clear message before a job is created.
package documents

import (
	"archive/zip"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"os"
	"path"
	"path/filepath"
	"strings"
)

// MaxUploadBytes bounds the files of one submission, as the node bounds
// the documents it reads.
const MaxUploadBytes int64 = 64 << 20

// MaxFiles bounds the number of files sent at once (a folder is sent as a
// ZIP instead).
const MaxFiles = 200

// BundleName is the file the node receives.
const BundleName = "documents.zip"

// Extensions read by the node, archives aside.
var documentExtensions = map[string]bool{
	".pdf": true, ".docx": true, ".txt": true, ".md": true, ".markdown": true,
}

// UserError is a refusal that can be shown to the user: Key is the message
// of the API catalog (package i18n) and Args its arguments.
type UserError struct {
	Key  string
	Args []any
}

func (e *UserError) Error() string { return fmt.Sprint(append([]any{e.Key, " "}, e.Args...)...) }

var (
	errNoFiles   = &UserError{Key: "documents.none"}
	errTooMany   = &UserError{Key: "documents.too_many", Args: []any{MaxFiles}}
	errTooLarge  = &UserError{Key: "documents.too_large"}
	errZipAndDoc = &UserError{Key: "documents.zip_and_files"}
)

func unsupported(name string) error {
	return &UserError{Key: "documents.unsupported", Args: []any{name}}
}

// Store writes the uploaded files to `dir` as the node's input and returns
// its path: a single ZIP is kept as is, documents are bundled into
// BundleName under unique names.
func Store(dir string, files []*multipart.FileHeader) (string, error) {
	if len(files) == 0 {
		return "", errNoFiles
	}
	if len(files) > MaxFiles {
		return "", errTooMany
	}
	var total int64
	archives := 0
	for _, file := range files {
		total += file.Size
		switch extension(file.Filename) {
		case ".zip":
			archives++
		default:
			if !documentExtensions[extension(file.Filename)] {
				return "", unsupported(baseName(file.Filename))
			}
		}
	}
	if total > MaxUploadBytes {
		return "", errTooLarge
	}
	if archives > 0 && len(files) > 1 {
		return "", errZipAndDoc
	}
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return "", err
	}
	target := filepath.Join(dir, BundleName)
	var err error
	if archives == 1 {
		err = copyUpload(target, files[0])
	} else {
		err = writeBundle(target, files)
	}
	if err != nil {
		_ = os.Remove(target)
		return "", err
	}
	return target, nil
}

// copyUpload copies one uploaded file, refusing more than MaxUploadBytes
// whatever its declared size.
func copyUpload(target string, header *multipart.FileHeader) error {
	source, err := header.Open()
	if err != nil {
		return err
	}
	defer source.Close()
	output, err := os.Create(target)
	if err != nil {
		return err
	}
	written, copyErr := io.Copy(output, io.LimitReader(source, MaxUploadBytes+1))
	if closeErr := output.Close(); copyErr == nil {
		copyErr = closeErr
	}
	if copyErr != nil {
		return copyErr
	}
	if written > MaxUploadBytes {
		return errTooLarge
	}
	return nil
}

// writeBundle writes the documents into one ZIP, renaming duplicates.
func writeBundle(target string, files []*multipart.FileHeader) error {
	output, err := os.Create(target)
	if err != nil {
		return err
	}
	archive := zip.NewWriter(output)
	names := uniqueNames(files)
	budget := MaxUploadBytes
	for index, file := range files {
		written, err := addToBundle(archive, names[index], file, budget)
		if err != nil {
			_ = archive.Close()
			_ = output.Close()
			return err
		}
		budget -= written
	}
	if err := archive.Close(); err != nil {
		_ = output.Close()
		return err
	}
	return output.Close()
}

func addToBundle(archive *zip.Writer, name string, file *multipart.FileHeader, budget int64) (int64, error) {
	source, err := file.Open()
	if err != nil {
		return 0, err
	}
	defer source.Close()
	entry, err := archive.CreateHeader(&zip.FileHeader{Name: name, Method: zip.Deflate})
	if err != nil {
		return 0, err
	}
	written, err := io.Copy(entry, io.LimitReader(source, budget+1))
	if err != nil {
		return written, err
	}
	if written > budget {
		return written, errTooLarge
	}
	return written, nil
}

// uniqueNames gives each upload a safe file name, unique in the bundle:
// `cours.pdf`, `cours (2).pdf`...
func uniqueNames(files []*multipart.FileHeader) []string {
	seen := map[string]bool{}
	names := make([]string, len(files))
	for index, file := range files {
		name := baseName(file.Filename)
		stem, ext := strings.TrimSuffix(name, path.Ext(name)), path.Ext(name)
		for copyNumber := 2; seen[strings.ToLower(name)]; copyNumber++ {
			name = fmt.Sprintf("%s (%d)%s", stem, copyNumber, ext)
		}
		seen[strings.ToLower(name)] = true
		names[index] = name
	}
	return names
}

// baseName is the file name of a client path (browsers on Windows may send
// backslashes), without control characters.
func baseName(name string) string {
	name = path.Base(strings.ReplaceAll(name, "\\", "/"))
	name = strings.Map(func(r rune) rune {
		if r < 0x20 || r == 0x7f {
			return -1
		}
		return r
	}, name)
	// The node skips hidden files and Office lock files (`.x`, `~$x`) of an
	// archive: a document sent under such a name keeps it without the prefix.
	name = strings.TrimLeft(strings.TrimPrefix(name, "~$"), ".")
	if strings.TrimSpace(name) == "" || path.Ext(name) == name {
		return "document" + path.Ext(name)
	}
	return name
}

func extension(name string) string {
	return strings.ToLower(path.Ext(baseName(name)))
}

// UserMessage is the i18n key and arguments of the message to show for err,
// or "" when err is internal.
func UserMessage(err error) (string, []any) {
	var userError *UserError
	if errors.As(err, &userError) {
		return userError.Key, userError.Args
	}
	return "", nil
}
