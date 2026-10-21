package catalog

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func examples(t *testing.T, values ...string) []json.RawMessage {
	t.Helper()
	out := []json.RawMessage{}
	for _, value := range values {
		out = append(out, json.RawMessage(value))
	}
	return out
}

func TestWidgetExamplesBecomeItemsOfTheTask(t *testing.T) {
	text := CanaryItems("text-classification", examples(t, `{"text":"I like you"}`, `{"text":"  "}`, `"bad"`), nil)
	if len(text) != 1 || string(text[0]) != `"I like you"` {
		t.Fatalf("text = %s", text)
	}
	qa := CanaryItems("question-answering", examples(t, `{"text":"Who?","context":"Marie."}`, `{"text":"Who?"}`), nil)
	if len(qa) != 1 || string(qa[0]) != `{"context":"Marie.","question":"Who?"}` {
		t.Fatalf("qa = %s", qa)
	}
	similar := CanaryItems("sentence-similarity", examples(t, `{"source_sentence":"a","sentences":["b","c"]}`), nil)
	if len(similar) != 1 || !strings.Contains(string(similar[0]), `"sentences":["b","c"]`) {
		t.Fatalf("similarity = %s", similar)
	}
	asked := []string{}
	download := func(source string) ([]byte, error) {
		asked = append(asked, source)
		if strings.Contains(source, "missing") {
			return nil, errors.New("gone")
		}
		return []byte("hi"), nil
	}
	images := CanaryItems("image-classification", examples(t, `{"src":"https://hf.co/a.jpg"}`, `{"src":"https://hf.co/missing.jpg"}`), download)
	if len(images) != 1 || string(images[0]) != `{"$bytes":"aGk="}` || len(asked) != 2 {
		t.Fatalf("images = %s, asked %v", images, asked)
	}
	many := CanaryItems("fill-mask", examples(t, `{"text":"a"}`, `{"text":"b"}`, `{"text":"c"}`, `{"text":"d"}`, `{"text":"e"}`), nil)
	if len(many) != MaxCanaries {
		t.Fatalf("kept %d", len(many))
	}
	if CanaryItems("text-to-image", examples(t, `{"text":"a cat"}`), nil) != nil {
		t.Fatal("a task the network does not run has no canaries")
	}
}

func TestExamplesAreOnlyDownloadedFromTheHub(t *testing.T) {
	hub := NewHub("", "")
	for source, trusted := range map[string]bool{
		"https://huggingface.co/datasets/x/a.jpg":   true,
		"https://cdn-media.huggingface.co/a.flac":   true,
		"https://hf.co/a.jpg":                       true,
		"http://huggingface.co/a.jpg":               false,
		"https://evil.example/huggingface.co/a.jpg": false,
		"https://huggingface.co.evil.example/a.jpg": false,
		"https://user@huggingface.co/a.jpg":         false,
		"file:///etc/passwd":                        false,
	} {
		if hub.trustedExample(source) != trusted {
			t.Errorf("%s: trusted = %v", source, !trusted)
		}
	}
}
