// Storage of uploaded job input files.

package handler

import (
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const maxJobInputBytes int64 = 16 << 20

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
