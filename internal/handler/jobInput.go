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

func safeFilename(name string) string {
	// Browsers on Windows may submit a backslash-delimited client path even
	// when the API itself runs on Linux.
	name = strings.ReplaceAll(name, "\\", "/")
	base := filepath.Base(name)
	base = strings.ReplaceAll(base, " ", "_")
	if base == "." || base == string(filepath.Separator) || base == "" {
		return "input.json"
	}
	return base
}

// storeUploadedJobInput stores the single `file` field of a job form (a
// scene, or the file to hash). On failure it returns the HTTP status and
// message to answer.
func storeUploadedJobInput(r *http.Request, jobID, inputDir string) (string, int, string) {
	file, header, err := r.FormFile("file")
	if err != nil {
		return "", http.StatusBadRequest, "Input file is required"
	}
	defer file.Close()
	if header.Size > maxJobInputBytes {
		return "", http.StatusRequestEntityTooLarge, "Input file exceeds the 16 MiB limit"
	}
	inputPath, err := storeJobInput(inputDir, header.Filename, file)
	if err == nil {
		return inputPath, 0, ""
	}
	log.Printf("store job %q input in %q: %v", jobID, inputDir, err)
	switch {
	case errors.Is(err, errEmptyJobInput):
		return "", http.StatusBadRequest, "Input file cannot be empty"
	case errors.Is(err, errJobInputTooLarge):
		return "", http.StatusRequestEntityTooLarge, "Input file exceeds the 16 MiB limit"
	default:
		return "", http.StatusInternalServerError, "Could not store input file"
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
