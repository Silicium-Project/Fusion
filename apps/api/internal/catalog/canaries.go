package catalog

// Canaries ("exercices corrigés"): inputs whose answer the network learns
// once and then checks. They come from the Hub's widget examples of a model
// (public inputs, never a user's data), converted at admission into the
// item format of the task (`silicium-hf-request/1`): a text, an object of
// fields, or a file as `{"$bytes": "<base64>"}` downloaded from the Hub.
//
// The BackEnd adds them to each request of the model (`canaries`); the
// publisher node mixes them with the user's items, so a worker cannot tell
// them apart, checks them before a result is accepted, and removes them
// from the answers (see the node's `workload/hf/canary.rs`).

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

// MaxCanaries is the number of canaries kept per model.
const MaxCanaries = 4

// maxExampleBytes bounds a file downloaded for a canary.
const maxExampleBytes = 2 << 20

// canaryKinds tells how a widget example becomes an item, by task.
var canaryKinds = map[string]string{
	"text-classification":            "text",
	"token-classification":           "text",
	"zero-shot-classification":       "text",
	"translation":                    "text",
	"summarization":                  "text",
	"feature-extraction":             "text",
	"text-generation":                "text",
	"fill-mask":                      "text",
	"question-answering":             "question",
	"table-question-answering":       "table",
	"sentence-similarity":            "sentences",
	"text-ranking":                   "ranking",
	"image-classification":           "file",
	"zero-shot-image-classification": "file",
	"object-detection":               "file",
	"image-to-text":                  "file",
	"image-feature-extraction":       "file",
	"automatic-speech-recognition":   "file",
	"audio-classification":           "file",
}

// CanaryItems converts the widget examples of a model of `task` into
// items (at most MaxCanaries); `download` gets a file named by an example.
// Examples it cannot convert are skipped.
func CanaryItems(task string, examples []json.RawMessage, download func(string) ([]byte, error)) []json.RawMessage {
	kind, ok := canaryKinds[task]
	if !ok {
		return nil
	}
	items := []json.RawMessage{}
	for _, raw := range examples {
		if len(items) == MaxCanaries {
			break
		}
		var example map[string]json.RawMessage
		if json.Unmarshal(raw, &example) != nil {
			continue
		}
		if item := canaryItem(kind, example, download); item != nil {
			items = append(items, item)
		}
	}
	return items
}

func canaryItem(kind string, example map[string]json.RawMessage, download func(string) ([]byte, error)) json.RawMessage {
	text := func(key string) string {
		var value string
		_ = json.Unmarshal(example[key], &value)
		return strings.TrimSpace(value)
	}
	texts := func(key string) []string {
		var values []string
		if json.Unmarshal(example[key], &values) != nil {
			return nil
		}
		out := values[:0]
		for _, value := range values {
			if value = strings.TrimSpace(value); value != "" {
				out = append(out, value)
			}
		}
		return out
	}
	marshal := func(value any) json.RawMessage {
		encoded, err := json.Marshal(value)
		if err != nil || len(encoded) > maxExampleBytes*2 {
			return nil
		}
		return encoded
	}
	switch kind {
	case "text":
		if value := text("text"); value != "" {
			return marshal(value)
		}
	case "question":
		if question, context := text("text"), text("context"); question != "" && context != "" {
			return marshal(map[string]string{"question": question, "context": context})
		}
	case "table":
		var table map[string][]string
		if query := text("text"); query != "" && json.Unmarshal(example["table"], &table) == nil && len(table) > 0 {
			return marshal(map[string]any{"query": query, "table": table})
		}
	case "sentences":
		if source, sentences := text("source_sentence"), texts("sentences"); source != "" && len(sentences) > 0 {
			return marshal(map[string]any{"source_sentence": source, "sentences": sentences})
		}
	case "ranking":
		query, documents := text("query"), texts("texts")
		if query == "" {
			query, documents = text("source_sentence"), texts("sentences")
		}
		if query != "" && len(documents) > 1 {
			return marshal(map[string]any{"query": query, "texts": documents})
		}
	case "file":
		if source := text("src"); source != "" && download != nil {
			if data, err := download(source); err == nil && len(data) > 0 {
				return marshal(map[string]string{"$bytes": base64.StdEncoding.EncodeToString(data)})
			}
		}
	}
	return nil
}

// Example downloads the file of a widget example, only from the Hub (its
// endpoint, or a `huggingface.co` / `hf.co` host over HTTPS), at most
// maxExampleBytes.
func (h *Hub) Example(ctx context.Context, source string) ([]byte, error) {
	if !h.trustedExample(source) {
		return nil, fmt.Errorf("example %q is not on the Hub", source)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, source, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("User-Agent", "silicium-catalog/1")
	client := h.Client
	if client == nil {
		client = http.DefaultClient
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrHubUnavailable, err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("example %s answered %d", source, response.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, maxExampleBytes+1))
	if err != nil {
		return nil, err
	}
	if len(data) > maxExampleBytes {
		return nil, fmt.Errorf("example %s is larger than %d bytes", source, maxExampleBytes)
	}
	return data, nil
}

func (h *Hub) trustedExample(source string) bool {
	parsed, err := url.Parse(source)
	if err != nil || parsed.User != nil {
		return false
	}
	if endpoint, err := url.Parse(h.Endpoint); err == nil && parsed.Scheme == endpoint.Scheme && parsed.Host == endpoint.Host {
		return true
	}
	host := strings.ToLower(parsed.Hostname())
	onHub := host == "huggingface.co" || strings.HasSuffix(host, ".huggingface.co") ||
		host == "hf.co" || strings.HasSuffix(host, ".hf.co")
	return parsed.Scheme == "https" && onHub
}
