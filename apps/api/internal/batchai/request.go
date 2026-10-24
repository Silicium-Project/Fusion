// Package batchai holds what the site does with a batch AI job ("Traitement
// par IA"): one instruction applied by the network to every item of a list,
// with a pinned language model run by Ollama on the workers.
//
// The site reads the user's file in the browser and sends a request
// (`silicium-llm-request/1`, JSON). This package checks it with the limits
// of the node (crate `silicium-llm` in Network, module `request`), so that
// the user gets a message in their language before a job is created; the
// node checks it again and cleans the texts. It also writes a short summary
// next to the request for the job page, and reads the answers back.
package batchai

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"
)

// Format of a request.
const Format = "silicium-llm-request/1"

// Limits of a request, those of the node.
const (
	MaxItems            = 20_000
	MaxItemChars        = 6_000
	MaxInstructionChars = 2_000
	MinLabels           = 2
	MaxLabels           = 50
	MaxLabelChars       = 80
	MaxFields           = 20
	MaxFieldChars       = 40
	MinMaxTokens        = 16
	MaxMaxTokens        = 1024
	DefaultMaxTokens    = 256
	// MaxRequestBytes bounds the request file (the job input limit).
	MaxRequestBytes = 16 << 20
)

// RequestName and SummaryName are the files of a job's input directory.
const (
	RequestName = "request.json"
	SummaryName = "request-summary.json"
)

var tasks = map[string]bool{"free": true, "summarize": true, "translate": true, "classify": true, "extract": true}

// UserError is a refusal for the user: Key is the message of the API
// catalog (package i18n) and Args its arguments.
type UserError struct {
	Key  string
	Args []any
}

func (e *UserError) Error() string { return fmt.Sprint(append([]any{e.Key, " "}, e.Args...)...) }

func refuse(key string, args ...any) error { return &UserError{Key: key, Args: args} }

// Output is what an answer is: free text, one of Labels, or Fields.
type Output struct {
	Kind   string   `json:"kind"`
	Labels []string `json:"labels,omitempty"`
	Fields []string `json:"fields,omitempty"`
}

// Source names the file and column the items come from.
type Source struct {
	Name   string `json:"name,omitempty"`
	Column string `json:"column,omitempty"`
}

// Summary is what the job page shows about a request (`request-summary.json`).
type Summary struct {
	Task        string `json:"task"`
	Instruction string `json:"instruction"`
	Output      Output `json:"output"`
	MaxTokens   int    `json:"maxTokens"`
	ItemCount   int    `json:"itemCount"`
	Source      Source `json:"source"`
}

type rawRequest struct {
	Format      string            `json:"format"`
	Task        string            `json:"task"`
	Instruction string            `json:"instruction"`
	Output      *Output           `json:"output"`
	MaxTokens   *int              `json:"max_tokens"`
	Source      *Source           `json:"source"`
	Items       []json.RawMessage `json:"items"`
}

// Check reads a request and returns its summary, or a *UserError.
func Check(data []byte) (Summary, error) {
	var raw rawRequest
	if err := json.Unmarshal(data, &raw); err != nil || raw.Format != Format || raw.Output == nil {
		return Summary{}, refuse("llm.request_invalid")
	}
	task := raw.Task
	if task == "" {
		task = "free"
	}
	if !tasks[task] {
		return Summary{}, refuse("llm.request_invalid")
	}
	instruction := strings.TrimSpace(raw.Instruction)
	if utf8.RuneCountInString(instruction) > MaxInstructionChars {
		return Summary{}, refuse("llm.instruction_too_long", MaxInstructionChars)
	}
	output, err := checkOutput(*raw.Output)
	if err != nil {
		return Summary{}, err
	}
	if instruction == "" && output.Kind != "text" {
		return Summary{}, refuse("llm.instruction_required")
	}
	maxTokens := DefaultMaxTokens
	if raw.MaxTokens != nil {
		maxTokens = *raw.MaxTokens
	}
	if maxTokens < MinMaxTokens || maxTokens > MaxMaxTokens {
		return Summary{}, refuse("llm.max_tokens_invalid", MinMaxTokens, MaxMaxTokens)
	}
	if err := checkItems(raw.Items); err != nil {
		return Summary{}, err
	}
	source := Source{}
	if raw.Source != nil {
		source = Source{Name: shorten(raw.Source.Name, 200), Column: shorten(raw.Source.Column, 200)}
	}
	return Summary{
		Task:        task,
		Instruction: instruction,
		Output:      output,
		MaxTokens:   maxTokens,
		ItemCount:   len(raw.Items),
		Source:      source,
	}, nil
}

func checkOutput(output Output) (Output, error) {
	switch output.Kind {
	case "text":
		return Output{Kind: "text"}, nil
	case "label":
		labels, err := checkNames(output.Labels, MaxLabelChars)
		if err != nil {
			return Output{}, err
		}
		if len(labels) < MinLabels || len(labels) > MaxLabels {
			return Output{}, refuse("llm.labels_count", MinLabels, MaxLabels)
		}
		return Output{Kind: "label", Labels: labels}, nil
	case "fields":
		fields, err := checkNames(output.Fields, MaxFieldChars)
		if err != nil {
			return Output{}, err
		}
		if len(fields) == 0 || len(fields) > MaxFields {
			return Output{}, refuse("llm.fields_count", MaxFields)
		}
		return Output{Kind: "fields", Fields: fields}, nil
	default:
		return Output{}, refuse("llm.request_invalid")
	}
}

// checkNames checks labels or field names: non-empty, short, unique
// (ignoring case).
func checkNames(names []string, maxChars int) ([]string, error) {
	seen := map[string]bool{}
	cleaned := make([]string, 0, len(names))
	for _, name := range names {
		name = strings.Join(strings.Fields(name), " ")
		if name == "" || utf8.RuneCountInString(name) > maxChars {
			return nil, refuse("llm.name_invalid", maxChars)
		}
		key := strings.ToLower(name)
		if seen[key] {
			return nil, refuse("llm.name_duplicate", name)
		}
		seen[key] = true
		cleaned = append(cleaned, name)
	}
	return cleaned, nil
}

func checkItems(items []json.RawMessage) error {
	if len(items) == 0 {
		return refuse("llm.no_items")
	}
	if len(items) > MaxItems {
		return refuse("llm.too_many_items", MaxItems)
	}
	for index, raw := range items {
		var text string
		if err := json.Unmarshal(raw, &text); err != nil {
			var number json.Number
			if json.Unmarshal(raw, &number) != nil {
				return refuse("llm.item_not_text", index+1)
			}
			text = number.String()
		}
		text = strings.TrimSpace(text)
		if text == "" {
			return refuse("llm.item_empty", index+1)
		}
		if utf8.RuneCountInString(text) > MaxItemChars {
			return refuse("llm.item_too_long", index+1, MaxItemChars)
		}
	}
	return nil
}

func shorten(text string, maxRunes int) string {
	text = strings.TrimSpace(text)
	runes := []rune(text)
	if len(runes) > maxRunes {
		return string(runes[:maxRunes])
	}
	return text
}

// Store checks `data` and writes it to `dir` with its summary; it returns
// the path of the request (the node's input).
func Store(dir string, data []byte) (string, error) {
	summary, err := Check(data)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	path := filepath.Join(dir, RequestName)
	if err := os.WriteFile(path, data, 0o644); err != nil {
		return "", err
	}
	encoded, err := json.Marshal(summary)
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(dir, SummaryName), encoded, 0o644); err != nil {
		_ = os.Remove(path)
		return "", err
	}
	return path, nil
}

// ReadSummary is the summary stored next to the request at `requestPath`.
func ReadSummary(requestPath string) (Summary, error) {
	data, err := os.ReadFile(filepath.Join(filepath.Dir(requestPath), SummaryName))
	if err != nil {
		return Summary{}, err
	}
	var summary Summary
	if err := json.Unmarshal(data, &summary); err != nil {
		return Summary{}, errors.New("unreadable request summary")
	}
	return summary, nil
}
