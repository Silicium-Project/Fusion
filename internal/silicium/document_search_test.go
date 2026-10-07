package silicium

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/silicium/internal/models"
)

func TestSearchDocumentsAsksTheNodeWithTheControlToken(t *testing.T) {
	var received documentSearchRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/embedding/search" || r.Header.Get("Authorization") != "Bearer secret" {
			http.Error(w, "unexpected", http.StatusTeapot)
			return
		}
		_ = json.NewDecoder(r.Body).Decode(&received)
		_, _ = w.Write([]byte(`{"model":"multilingual-e5-small","hits":[{"job_id":"site-1","passage_id":4,"document":"contrat.pdf","page":12,"text":"préavis de trente jours","score":0.87}]}`))
	}))
	defer server.Close()
	cfg := RunnerConfig{NodeAPIURL: server.URL, NodeControlToken: "secret"}

	hits, err := SearchDocuments(context.Background(), cfg, []string{"site-1"}, "  résilier ?  ", 5)
	if err != nil {
		t.Fatal(err)
	}
	if received.Query != "résilier ?" || received.TopK != 5 || len(received.Jobs) != 1 {
		t.Fatalf("request = %+v", received)
	}
	if len(hits) != 1 || hits[0].Document != "contrat.pdf" || hits[0].Page == nil || *hits[0].Page != 12 {
		t.Fatalf("hits = %+v", hits)
	}
}

func TestSearchDocumentsReportsAModelBeingPrepared(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"error":"model_preparing"}`))
	}))
	defer server.Close()
	_, err := SearchDocuments(context.Background(), RunnerConfig{NodeAPIURL: server.URL}, []string{"site-1"}, "q", 5)
	if !errors.Is(err, ErrModelPreparing) {
		t.Fatalf("err = %v, want ErrModelPreparing", err)
	}
}

func TestAnEmptyQueryAsksNothing(t *testing.T) {
	hits, err := SearchDocuments(context.Background(), RunnerConfig{}, []string{"site-1"}, "  ", 5)
	if err != nil || hits != nil {
		t.Fatalf("hits = %v, err = %v", hits, err)
	}
}

func TestDocumentSearchIsAKnownWorkload(t *testing.T) {
	if !IsDocumentSearch(DocumentSearchWorkload) || IsDocumentSearch("raytracer") || IsDocumentSearch("nope") {
		t.Fatal("IsDocumentSearch")
	}
	if dir, ok := JobStorageDir(DocumentSearchWorkload); !ok || dir != "embedding" {
		t.Fatalf("storage dir = %q", dir)
	}
	if err := ValidateWorkload(DocumentSearchWorkload); err != nil {
		t.Fatal(err)
	}
}

func TestARefusedDocumentSubmissionFailsWithTheNodeMessage(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":"Aucun texte n'a pu être lu : les PDF envoyés sont probablement des images scannées."}`))
	}))
	defer server.Close()
	root := t.TempDir()
	cfg := RunnerConfig{NetworkRoot: root, WorkloadStorageDir: root, NodeAPIURL: server.URL}
	job := models.Job{SiliciumJobID: "site-docs", Workload: DocumentSearchWorkload, InputPath: "/tmp/documents.zip"}
	result := RunJob(context.Background(), job, cfg)
	if result.Status != "failed" || result.ErrorMessage != "Aucun texte n'a pu être lu : les PDF envoyés sont probablement des images scannées." {
		t.Fatalf("result = %+v", result)
	}
}
