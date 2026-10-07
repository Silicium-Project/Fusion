// Storage of uploaded job input files.

package handler

import (
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"unicode"

	"github.com/silicium/internal/documents"
)

const maxJobInputBytes int64 = 16 << 20

// maxJobRequestBytes bounds a job creation request: the largest input (the
// documents of a document search) and the form fields around it.
const maxJobRequestBytes = documents.MaxUploadBytes + 1<<20

var (
	errEmptyJobInput    = errors.New("input file is empty")
	errJobInputTooLarge = errors.New("input file exceeds the 16 MiB limit")
)

// maxStoredNameRunes bounds the name of a stored input file.
const maxStoredNameRunes = 100

// safeFilename is the name an uploaded file is stored under: its base name
// (browsers on Windows may send a backslash path), with every character but
// ASCII letters, digits, dots, hyphens and underscores replaced, no leading
// dot (no hidden file, no ".."), at most 100 characters.
func safeFilename(name string) string {
	name = strings.ReplaceAll(name, "\\", "/")
	base := filepath.Base(name)
	cleaned := []rune{}
	for _, r := range base {
		switch {
		case r < 0x80 && (unicode.IsLetter(r) || unicode.IsDigit(r) || r == '.' || r == '-' || r == '_'):
			cleaned = append(cleaned, r)
		default:
			cleaned = append(cleaned, '_')
		}
	}
	safe := strings.TrimLeft(string(cleaned), ".")
	if len(safe) > maxStoredNameRunes {
		safe = safe[len(safe)-maxStoredNameRunes:]
		safe = strings.TrimLeft(safe, ".")
	}
	if strings.Trim(safe, "_") == "" {
		return "input.bin"
	}
	return safe
}

// storeUploadedJobInput stores the single `file` field of a job form (a
// scene, or the file to hash). On failure it returns the HTTP status and
// the i18n key of the message.
func storeUploadedJobInput(r *http.Request, jobID, inputDir string) (string, int, string) {
	file, header, err := r.FormFile("file")
	if err != nil {
		return "", http.StatusBadRequest, "job.input_required"
	}
	defer file.Close()
	if header.Size > maxJobInputBytes {
		return "", http.StatusRequestEntityTooLarge, "job.input_too_large"
	}
	inputPath, err := storeJobInput(inputDir, header.Filename, file)
	if err == nil {
		return inputPath, 0, ""
	}
	log.Printf("store job %q input in %q: %v", jobID, inputDir, err)
	switch {
	case errors.Is(err, errEmptyJobInput):
		return "", http.StatusBadRequest, "job.input_empty"
	case errors.Is(err, errJobInputTooLarge):
		return "", http.StatusRequestEntityTooLarge, "job.input_too_large"
	default:
		return "", http.StatusInternalServerError, "job.input_store_failed"
	}
}

func storeJobInput(inputDir, filename string, source io.Reader) (string, error) {
	if err := os.MkdirAll(inputDir, 0o755); err != nil {
		return "", err
	}
	inputPath := filepath.Join(inputDir, safeFilename(filename))
	target, err := os.Create(inputPath)
	if err != nil {
		return "", err
	}

	written, copyErr := io.CopyN(target, source, maxJobInputBytes+1)
	closeErr := target.Close()
	if copyErr != nil && !errors.Is(copyErr, io.EOF) {
		_ = os.Remove(inputPath)
		return "", copyErr
	}
	if closeErr != nil {
		_ = os.Remove(inputPath)
		return "", closeErr
	}
	if written == 0 {
		_ = os.Remove(inputPath)
		return "", errEmptyJobInput
	}
	if written > maxJobInputBytes {
		_ = os.Remove(inputPath)
		return "", errJobInputTooLarge
	}
	return inputPath, nil
}
