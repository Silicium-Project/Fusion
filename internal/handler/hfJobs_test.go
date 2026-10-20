package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/aijobs"
	"github.com/silicium/internal/catalog"
	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

const hfKey = "org--classifier-0123456789ab"
const hfWorkload = "ai/hf/text-classification/" + hfKey
const hfManifest = `{"format":"silicium-model/1","key":"org--classifier-0123456789ab","task":"text-classification","total_bytes":1073741824}`

func hfTestHandler(t *testing.T, name string, status string) Handler {
	t.Helper()
	h, database := documentTestHandler(t, name)
	if err := catalog.Migrate(database); err != nil {
		t.Fatal(err)
	}
	err := catalog.Store{DB: database}.Save(catalog.Model{
		Key: hfKey, Repository: "org/classifier", Revision: strings.Repeat("a", 40), Task: "text-classification",
		Status: status, Reasons: "[]", Notes: "[]", Manifest: hfManifest, HardwareClass: "A",
		TotalBytes: 1 << 30, Licence: "apache-2.0", CheckedAt: time.Now(),
	})
	if err != nil {
		t.Fatal(err)
	}
	return h
}

func hfForm(t *testing.T, workload, request string, consent bool) *http.Request {
	t.Helper()
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	_ = form.WriteField("workload", workload)
	if consent {
		_ = form.WriteField("acknowledge_sharing", "1")
	}
	part, _ := form.CreateFormFile("file", "request.json")
	_, _ = part.Write([]byte(request))
	_ = form.Close()
	request2 := httptest.NewRequest(http.MethodPost, "/jobs", &body)
	request2.Header.Set("Content-Type", form.FormDataContentType())
	request2.Header.Set("Accept-Language", "fr")
	return request2.WithContext(context.WithValue(request2.Context(), contextkeys.UserIDKey, "7"))
}

const hfSiteRequest = `{"format":"silicium-hf-site-request/1","task":"text-classification","parameters":{"top_k":2},"items":["Très bon produit.","Livraison lente."],"source":{"name":"avis.csv"}}`

func TestACatalogueJobStoresTheCatalogueManifest(t *testing.T) {
	h := hfTestHandler(t, "hf-create", "admitted")
	response := httptest.NewRecorder()
	h.CreateJob(response, hfForm(t, hfWorkload, hfSiteRequest, true))
	if response.Code != http.StatusAccepted {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
	var created, job models.Job
	_ = json.Unmarshal(response.Body.Bytes(), &created)
	h.DB.First(&job, created.ID)
	if job.Title != hfTitle || job.Workload != hfWorkload {
		t.Fatalf("job %#v", job)
	}
	var request map[string]json.RawMessage
	data, _ := os.ReadFile(job.InputPath)
	_ = json.Unmarshal(data, &request)
	if string(request["model"]) != hfManifest || string(request["format"]) != `"silicium-hf-request/1"` {
		t.Fatalf("request %s", data)
	}
	summary, err := aijobs.ReadSummary(job.InputPath)
	if err != nil || summary.ItemCount != 2 || summary.Model.Repository != "org/classifier" || summary.Previews[0] != "Très bon produit." {
		t.Fatalf("summary %#v %v", summary, err)
	}
	if spec, ok := silicium.JobStorageDir(hfWorkload); !ok || spec != "hf" {
		t.Fatal("the node writes catalogue jobs under hf/")
	}
}

func TestACatalogueJobIsRefusedWithAMessage(t *testing.T) {
	cases := []struct {
		name, status, workload, request string
		consent                         bool
		message                         string
	}{
		{"no consent", "admitted", hfWorkload, hfSiteRequest, false, "machines du réseau"},
		{"model not admitted", "review", hfWorkload, hfSiteRequest, true, "pas (ou plus) admis"},
		{"unknown model", "admitted", "ai/hf/text-classification/org--other-0123456789ab", hfSiteRequest, true, "pas (ou plus) admis"},
		{"task not run yet", "admitted", "ai/hf/text-to-video/" + hfKey, hfSiteRequest, true, "pas encore"},
		{"other task", "admitted", hfWorkload, strings.Replace(hfSiteRequest, `"task":"text-classification"`, `"task":"translation"`, 1), true, "ne correspond pas"},
		{"blank item", "admitted", hfWorkload, strings.Replace(hfSiteRequest, `"Livraison lente."`, `"  "`, 1), true, "n° 2 est vide"},
		{"bad parameters", "admitted", hfWorkload, strings.Replace(hfSiteRequest, `{"top_k":2}`, `[2]`, 1), true, "paramètres"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			h := hfTestHandler(t, "hf-refused-"+strings.ReplaceAll(c.name, " ", "-"), c.status)
			response := httptest.NewRecorder()
			h.CreateJob(response, hfForm(t, c.workload, c.request, c.consent))
			if response.Code != http.StatusBadRequest || !strings.Contains(response.Body.String(), c.message) {
				t.Fatalf("status %d body %s", response.Code, response.Body)
			}
		})
	}
}

func TestTheQuoteIsLowerWhenWorkersHaveTheModel(t *testing.T) {
	h := hfTestHandler(t, "hf-quote", "admitted")
	peers := map[string]any{"peers": []any{
		map[string]any{"online": true, "self": true, "roles": []any{"compute"}, "capacity": map[string]any{"ai_models": []any{hfKey}}},
		map[string]any{"online": true, "roles": []any{"compute", "verify"}, "capacity": map[string]any{"ai_models": []any{hfKey}}},
		map[string]any{"online": true, "roles": []any{"compute", "verify"}, "capacity": map[string]any{"ai_models": []any{}}},
		map[string]any{"online": false, "roles": []any{"compute"}, "capacity": map[string]any{"ai_models": []any{hfKey}}},
	}}
	previous := networkPeers
	networkPeers = func(*http.Request) (map[string]any, error) { return peers, nil }
	t.Cleanup(func() { networkPeers = previous })

	quote := func(items string) catalog.Quote {
		router := mux.NewRouter()
		router.HandleFunc("/catalog/models/{key}/quote", h.GetCatalogQuote)
		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/catalog/models/"+hfKey+"/quote?items="+items, nil))
		var body struct {
			Quote catalog.Quote `json:"quote"`
		}
		if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil || response.Code != http.StatusOK {
			t.Fatalf("status %d body %s", response.Code, response.Body)
		}
		return body.Quote
	}
	small := quote("10")
	if !small.Warm || small.InstallCredits != 0 || small.WarmWorkers != 1 || small.OnlineWorkers != 2 {
		t.Fatalf("one fragment, one warm worker: %+v", small)
	}
	large := quote("100")
	if large.Warm || large.WorkersNeeded != 4 || large.InstallCredits != 6 || large.TotalCredits != 131 {
		t.Fatalf("seven fragments, three workers to install: %+v", large)
	}
}

func TestCatalogueAnswersAreReadOnceDone(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "answers.jsonl")
	_ = os.WriteFile(path, []byte("{\"id\":0,\"output\":[{\"label\":\"pos\"}]}\n{\"id\":1,\"output\":[{\"label\":\"neg\"}]}\n"), 0o600)
	rows, total, err := aijobs.ReadAnswers(path, 1, 10)
	if err != nil || total != 2 || len(rows) != 1 || rows[0].ID != 1 || string(rows[0].Output) != `[{"label":"neg"}]` {
		t.Fatalf("rows %#v total %d err %v", rows, total, err)
	}
	for _, bad := range []string{"ai/hf/", "ai/hf/text-classification", "ai/hf/Text/key-0123456789ab", "ai/hf/text-classification/../x-0123456789ab"} {
		if silicium.IsHF(bad) {
			t.Fatalf("%q accepted", bad)
		}
	}
}
