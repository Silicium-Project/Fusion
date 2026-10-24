package batchai

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func request(t *testing.T, change func(map[string]any)) []byte {
	t.Helper()
	value := map[string]any{
		"format":      Format,
		"task":        "classify",
		"instruction": "Classe cet avis.",
		"output":      map[string]any{"kind": "label", "labels": []string{"positif", "négatif"}},
		"source":      map[string]any{"name": "avis.csv", "column": "avis"},
		"items":       []any{"Très bien.", "Nul.", 42},
	}
	if change != nil {
		change(value)
	}
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func refusal(t *testing.T, data []byte) *UserError {
	t.Helper()
	_, err := Check(data)
	var refused *UserError
	if !errors.As(err, &refused) {
		t.Fatalf("expected a refusal, got %v", err)
	}
	return refused
}

func TestARequestIsSummarized(t *testing.T) {
	summary, err := Check(request(t, nil))
	if err != nil {
		t.Fatal(err)
	}
	if summary.ItemCount != 3 || summary.MaxTokens != DefaultMaxTokens || summary.Output.Kind != "label" || summary.Source.Column != "avis" {
		t.Fatalf("summary = %#v", summary)
	}
}

func TestRequestsOverTheNodeLimitsAreRefused(t *testing.T) {
	cases := map[string]struct {
		change func(map[string]any)
		key    string
	}{
		"format":      {func(v map[string]any) { v["format"] = "x/1" }, "llm.request_invalid"},
		"task":        {func(v map[string]any) { v["task"] = "hack" }, "llm.request_invalid"},
		"kind":        {func(v map[string]any) { v["output"] = map[string]any{"kind": "poem"} }, "llm.request_invalid"},
		"no items":    {func(v map[string]any) { v["items"] = []any{} }, "llm.no_items"},
		"empty item":  {func(v map[string]any) { v["items"] = []any{"a", "  "} }, "llm.item_empty"},
		"object item": {func(v map[string]any) { v["items"] = []any{map[string]any{}} }, "llm.item_not_text"},
		"long item":   {func(v map[string]any) { v["items"] = []any{strings.Repeat("é", MaxItemChars+1)} }, "llm.item_too_long"},
		"one label":   {func(v map[string]any) { v["output"] = map[string]any{"kind": "label", "labels": []string{"a"}} }, "llm.labels_count"},
		"twice":       {func(v map[string]any) { v["output"] = map[string]any{"kind": "label", "labels": []string{"A", "a"}} }, "llm.name_duplicate"},
		"no field":    {func(v map[string]any) { v["output"] = map[string]any{"kind": "fields", "fields": []string{}} }, "llm.fields_count"},
		"instruction": {func(v map[string]any) { v["instruction"] = " " }, "llm.instruction_required"},
		"tokens":      {func(v map[string]any) { v["max_tokens"] = 5000 }, "llm.max_tokens_invalid"},
	}
	for name, test := range cases {
		if refused := refusal(t, request(t, test.change)); refused.Key != test.key {
			t.Errorf("%s: key = %s, want %s", name, refused.Key, test.key)
		}
	}
	if _, err := Check(request(t, func(v map[string]any) {
		v["instruction"] = ""
		v["output"] = map[string]any{"kind": "text"}
	})); err != nil {
		t.Errorf("items as prompts: %v", err)
	}
}

func TestARequestIsStoredWithItsSummary(t *testing.T) {
	dir := t.TempDir()
	path, err := Store(dir, request(t, nil))
	if err != nil || filepath.Base(path) != RequestName {
		t.Fatalf("Store = %q, %v", path, err)
	}
	summary, err := ReadSummary(path)
	if err != nil || summary.ItemCount != 3 {
		t.Fatalf("summary = %#v, %v", summary, err)
	}
	if _, err := Store(t.TempDir(), []byte("{")); err == nil {
		t.Fatal("an invalid request is stored")
	}
}

func TestAnswersArePaged(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "answers.jsonl")
	lines := `{"id":0,"input":"a","output":"x"}` + "\n" + `{"id":1,"input":"b","output":null}` + "\n" + `{"id":2,"input":"c","output":{"nom":"C"}}` + "\n"
	if err := os.WriteFile(path, []byte(lines), 0o644); err != nil {
		t.Fatal(err)
	}
	rows, total, err := ReadAnswers(path, 1, 1)
	if err != nil || total != 3 || len(rows) != 1 || rows[0].ID != 1 || string(rows[0].Output) != "null" {
		t.Fatalf("rows = %#v, total = %d, %v", rows, total, err)
	}
}

func TestPreviewsAreMergedInItemOrder(t *testing.T) {
	dir := t.TempDir()
	fragments := filepath.Join(dir, "fragments")
	_ = os.MkdirAll(fragments, 0o755)
	_ = os.WriteFile(filepath.Join(fragments, "fragment-001.jsonl"), []byte(`{"id":2,"input":"c","output":"z"}`+"\n"), 0o644)
	_ = os.WriteFile(filepath.Join(fragments, "fragment-000.jsonl"), []byte(`{"id":0,"input":"a","output":"x"}`+"\n"+`{"id":1,"input":"b","output":"y"}`+"\n"), 0o644)
	_ = os.WriteFile(filepath.Join(fragments, "fragment-000.png"), []byte("png"), 0o644)
	rows, available, err := ReadPreviews(dir, 1, 10)
	if err != nil || available != 3 || len(rows) != 2 || rows[0].ID != 1 || rows[1].ID != 2 {
		t.Fatalf("rows = %#v, available = %d, %v", rows, available, err)
	}
	rows, available, _ = ReadPreviews(t.TempDir(), 0, 10)
	if available != 0 || len(rows) != 0 {
		t.Fatalf("no fragment yet: %#v", rows)
	}
}
