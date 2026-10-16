package batchai

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

// Row is one answered item: `{"id","input","output"}`, the format of the
// node's `answers.jsonl` and of the previews of verified fragments
// (`fragments/fragment-NNN.jsonl`).
type Row struct {
	ID     int             `json:"id"`
	Input  string          `json:"input"`
	Output json.RawMessage `json:"output"`
}

// maxLineBytes bounds one line (an item of 6,000 characters and its answer).
const maxLineBytes = 1 << 20

// ReadAnswers returns rows `offset..offset+limit` of the answers file at
// `path`, and the number of rows in the file.
func ReadAnswers(path string, offset, limit int) ([]Row, int, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, 0, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64<<10), maxLineBytes)
	rows := []Row{}
	total := 0
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		if total >= offset && len(rows) < limit {
			var row Row
			if err := json.Unmarshal(line, &row); err != nil {
				return nil, 0, err
			}
			rows = append(rows, row)
		}
		total++
	}
	return rows, total, scanner.Err()
}

// ReadPreviews returns rows `offset..offset+limit` of the verified
// fragments of an unfinished job (`<jobDir>/fragments/fragment-*.jsonl`),
// in item order, and the number of items answered so far.
func ReadPreviews(jobDir string, offset, limit int) ([]Row, int, error) {
	paths, err := filepath.Glob(filepath.Join(jobDir, "fragments", "fragment-*.jsonl"))
	if err != nil {
		return nil, 0, err
	}
	all := []Row{}
	for _, path := range paths {
		rows, _, err := ReadAnswers(path, 0, MaxItems)
		if err != nil {
			continue
		}
		all = append(all, rows...)
	}
	sort.Slice(all, func(i, j int) bool { return all[i].ID < all[j].ID })
	if offset >= len(all) {
		return []Row{}, len(all), nil
	}
	end := min(len(all), offset+limit)
	return all[offset:end], len(all), nil
}
