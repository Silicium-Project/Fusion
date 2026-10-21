// Package aijobs holds what the site does with a job of the AI catalogue
// ("Catalogue IA", workloads `ai/hf/<task>/<model key>`): the request the
// site sends, the request the node receives, what the job page shows, and
// the answers.
//
// The site sends the task, the items and the parameters
// (`silicium-hf-site-request/1`); it never sends the model: the BackEnd
// takes the manifest from its catalogue (`internal/catalog`), so a job
// always runs a model the catalogue admitted. The node checks it all again
// (Network, `workload/hf`).
package aijobs

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Formats.
const (
	SiteFormat = "silicium-hf-site-request/1"
	NodeFormat = "silicium-hf-request/1"
)

// Limits, those of the node (60 MB for the whole request).
const (
	MaxItems           = 20_000
	MaxItemBytes       = 8 << 20
	MaxSiteRequestByte = 56 << 20
	MaxParameterBytes  = 64 << 10
)

// Files of a job's input directory.
const (
	RequestName = "request.json"
	SummaryName = "request-summary.json"
)

// UserError is a refusal for the user: Key is the message of the API
// catalog (package i18n) and Args its arguments.
type UserError struct {
	Key  string
	Args []any
}

func (e *UserError) Error() string { return fmt.Sprint(append([]any{e.Key, " "}, e.Args...)...) }

func refuse(key string, args ...any) error { return &UserError{Key: key, Args: args} }

// Source names the file the items come from (shown on the job page).
type Source struct {
	Name string `json:"name,omitempty"`
}

// SiteRequest is what the site sends.
type SiteRequest struct {
	Format     string            `json:"format"`
	Task       string            `json:"task"`
	Parameters json.RawMessage   `json:"parameters"`
	Items      []json.RawMessage `json:"items"`
	Source     Source            `json:"source"`
}

// Model is what the job page shows of the model.
type Model struct {
	Key           string `json:"key"`
	Repository    string `json:"repository"`
	Revision      string `json:"revision"`
	Licence       string `json:"licence"`
	HardwareClass string `json:"hardwareClass"`
}

// Summary is what the job page shows about a request (`request-summary.json`).
type Summary struct {
	Task       string          `json:"task"`
	Model      Model           `json:"model"`
	ItemCount  int             `json:"itemCount"`
	Parameters json.RawMessage `json:"parameters"`
	Source     Source          `json:"source"`
	// Previews are the first items when they are short texts (files are
	// not repeated on the page).
	Previews []string `json:"previews"`
}

// Store checks the site request `data` for `task`, writes the request of the
// node (with `manifest`, the catalogue's JSON) and its summary under
// `inputDir`, and returns the request's path.
func Store(inputDir string, data []byte, task string, manifest json.RawMessage, model Model, canaries []json.RawMessage) (string, error) {
	var site SiteRequest
	decoder := json.NewDecoder(bytes.NewReader(data))
	if err := decoder.Decode(&site); err != nil || site.Format != SiteFormat {
		return "", refuse("hf.request_invalid")
	}
	if site.Task != task {
		return "", refuse("hf.task_mismatch")
	}
	if len(site.Items) == 0 {
		return "", refuse("hf.no_items")
	}
	if len(site.Items) > MaxItems {
		return "", refuse("hf.too_many_items", MaxItems)
	}
	for index, item := range site.Items {
		trimmed := bytes.TrimSpace(item)
		var text string
		blankText := json.Unmarshal(trimmed, &text) == nil && strings.TrimSpace(text) == ""
		if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) || blankText {
			return "", refuse("hf.item_empty", index+1)
		}
		if len(trimmed) > MaxItemBytes {
			return "", refuse("hf.item_too_large", index+1)
		}
	}
	parameters := bytes.TrimSpace(site.Parameters)
	if len(parameters) == 0 || bytes.Equal(parameters, []byte("null")) {
		parameters = []byte("{}")
	}
	if parameters[0] != '{' || !json.Valid(parameters) {
		return "", refuse("hf.parameters_invalid")
	}
	if len(parameters) > MaxParameterBytes {
		return "", refuse("hf.parameters_invalid")
	}
	if len(site.Source.Name) > 200 {
		site.Source.Name = site.Source.Name[:200]
	}

	node := map[string]any{
		"format":     NodeFormat,
		"task":       task,
		"model":      manifest,
		"parameters": json.RawMessage(parameters),
		"items":      site.Items,
	}
	if len(canaries) > 0 {
		// Public examples of the model the node mixes with the items and
		// checks (never shown to the user, removed from the answers).
		node["canaries"] = canaries
	}
	request, err := json.Marshal(node)
	if err != nil {
		return "", err
	}
	summary := Summary{
		Task: task, Model: model, ItemCount: len(site.Items),
		Parameters: json.RawMessage(parameters), Source: site.Source, Previews: previews(site.Items),
	}
	encodedSummary, err := json.Marshal(summary)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(inputDir, 0o750); err != nil {
		return "", err
	}
	path := filepath.Join(inputDir, RequestName)
	if err := os.WriteFile(path, request, 0o640); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(inputDir, SummaryName), encodedSummary, 0o640); err != nil {
		_ = os.Remove(path)
		return "", err
	}
	return path, nil
}

// previews are the first three items shown as text: a string, or the
// question of an object; files are shown as "[fichier]".
func previews(items []json.RawMessage) []string {
	out := []string{}
	for _, item := range items {
		if len(out) == 3 {
			break
		}
		out = append(out, preview(item))
	}
	return out
}

func preview(item json.RawMessage) string {
	var text string
	if json.Unmarshal(item, &text) == nil {
		return shorten(text)
	}
	var object map[string]json.RawMessage
	if json.Unmarshal(item, &object) == nil {
		if _, ok := object["$bytes"]; ok {
			return "[fichier]"
		}
		for _, key := range []string{"question", "query", "source_sentence", "text"} {
			if json.Unmarshal(object[key], &text) == nil {
				return shorten(text)
			}
		}
	}
	return "[élément]"
}

func shorten(text string) string {
	text = strings.Join(strings.Fields(text), " ")
	if runes := []rune(text); len(runes) > 160 {
		return string(runes[:160]) + "…"
	}
	return text
}

// ReadSummary reads the summary next to the request at `requestPath`.
func ReadSummary(requestPath string) (Summary, error) {
	var summary Summary
	data, err := os.ReadFile(filepath.Join(filepath.Dir(requestPath), SummaryName))
	if err != nil {
		return summary, err
	}
	if err := json.Unmarshal(data, &summary); err != nil {
		return summary, errors.New("unreadable request summary")
	}
	return summary, nil
}

// Row is one answer: the item's id and the output of the model.
type Row struct {
	ID     int             `json:"id"`
	Output json.RawMessage `json:"output"`
}

// ReadAnswers reads `limit` answers from `offset` in the answers file
// (`answers.jsonl`), and how many there are.
func ReadAnswers(path string, offset, limit int) ([]Row, int, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, 0, err
	}
	rows := []Row{}
	total := 0
	for _, line := range bytes.Split(data, []byte("\n")) {
		if len(bytes.TrimSpace(line)) == 0 {
			continue
		}
		if total >= offset && len(rows) < limit {
			var row Row
			if err := json.Unmarshal(line, &row); err != nil {
				return nil, 0, fmt.Errorf("answer %d: %w", total, err)
			}
			rows = append(rows, row)
		}
		total++
	}
	return rows, total, nil
}
