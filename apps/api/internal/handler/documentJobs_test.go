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
	"strconv"
	"strings"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/gorilla/mux"
	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/documents"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
	"gorm.io/gorm"
)

// documentTestHandler is a handler on a fresh in-memory database whose job
// runner does nothing.
func documentTestHandler(t *testing.T, name string) (Handler, *gorm.DB) {
	t.Helper()
	database, err := gorm.Open(sqlite.Open("file:"+name+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := database.AutoMigrate(&models.Job{}); err != nil {
		t.Fatal(err)
	}
	sqlDB, err := database.DB()
	if err != nil {
		t.Fatal(err)
	}
	sqlDB.SetMaxOpenConns(1)
	t.Cleanup(func() { _ = sqlDB.Close() })
	t.Setenv("SILICIUM_SITE_STORAGE_DIR", t.TempDir())
	h := New(database)
	h.jobRunner = func(uint) {}
	return h, database
}

// documentForm is a job creation request for a document search by `userID`.
func documentForm(t *testing.T, userID string, fields map[string]string, files map[string]string) *http.Request {
	t.Helper()
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	for key, value := range fields {
		if err := form.WriteField(key, value); err != nil {
			t.Fatal(err)
		}
	}
	for name, content := range files {
		part, err := form.CreateFormFile("files", name)
		if err != nil {
			t.Fatal(err)
		}
		_, _ = part.Write([]byte(content))
	}
	if err := form.Close(); err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/jobs", &body)
	request.Header.Set("Content-Type", form.FormDataContentType())
	return request.WithContext(context.WithValue(request.Context(), contextkeys.UserIDKey, userID))
}

// jobRequest is a request on /jobs/{id}/… by `userID`.
func jobRequest(target string, jobID uint, userID string) *http.Request {
	request := httptest.NewRequest(http.MethodGet, target, nil)
	request = mux.SetURLVars(request, map[string]string{"id": strconv.Itoa(int(jobID))})
	return request.WithContext(context.WithValue(request.Context(), contextkeys.UserIDKey, userID))
}

func createDocumentJob(t *testing.T, h Handler, userID string, fields map[string]string) (*httptest.ResponseRecorder, models.Job) {
	t.Helper()
	all := map[string]string{"workload": silicium.DocumentSearchWorkload, "acknowledge_sharing": "1"}
	for key, value := range fields {
		all[key] = value
	}
	response := httptest.NewRecorder()
	h.CreateJob(response, documentForm(t, userID, all, map[string]string{"contrat.pdf": "%PDF-1.4", "notes.txt": "notes"}))
	var job models.Job
	_ = json.Unmarshal(response.Body.Bytes(), &job)
	return response, job
}

func TestADocumentSearchBundlesItsDocumentsInANewCollection(t *testing.T) {
	h, database := documentTestHandler(t, "document-create")
	response, created := createDocumentJob(t, h, "7", nil)
	if response.Code != http.StatusAccepted {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var job models.Job
	database.First(&job, created.ID)
	if job.Title != documentSearchTitle || job.CollectionID != job.SiliciumJobID || filepath.Base(job.InputPath) != documents.BundleName {
		t.Fatalf("stored job = %#v", job)
	}
	if document, err := documents.Open(job.InputPath, "notes.txt"); err != nil || string(document.Content) != "notes" {
		t.Fatalf("bundled notes = %q, %v", document.Content, err)
	}
}

func TestADocumentSearchNeedsTheSharingConsent(t *testing.T) {
	h, _ := documentTestHandler(t, "document-consent")
	response, _ := createDocumentJob(t, h, "7", map[string]string{"acknowledge_sharing": "0"})
	if response.Code != http.StatusBadRequest || !strings.Contains(response.Body.String(), "machines du réseau") {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestDocumentsAreAddedOnlyToTheUsersOwnCollection(t *testing.T) {
	h, _ := documentTestHandler(t, "document-collection")
	_, first := createDocumentJob(t, h, "7", nil)
	response, added := createDocumentJob(t, h, "7", map[string]string{"collection_id": first.SiliciumJobID})
	if response.Code != http.StatusAccepted || added.CollectionID != first.SiliciumJobID {
		t.Fatalf("own collection: status = %d, collection = %q", response.Code, added.CollectionID)
	}
	response, _ = createDocumentJob(t, h, "8", map[string]string{"collection_id": first.SiliciumJobID})
	if response.Code != http.StatusNotFound {
		t.Fatalf("another user's collection: status = %d", response.Code)
	}
}

func TestASearchCoversTheFinishedJobsOfTheCollection(t *testing.T) {
	h, database := documentTestHandler(t, "document-search")
	jobs := []models.Job{
		{UserID: 7, Title: "a", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "site-a", CollectionID: "site-a", InputPath: "/a"},
		{UserID: 7, Title: "b", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "site-b", CollectionID: "site-a", InputPath: "/b"},
		{UserID: 7, Title: "c", Workload: silicium.DocumentSearchWorkload, Status: "running", SiliciumJobID: "site-c", CollectionID: "site-a", InputPath: "/c"},
		{UserID: 8, Title: "d", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "site-d", CollectionID: "site-a", InputPath: "/d"},
	}
	for index := range jobs {
		database.Create(&jobs[index])
	}
	var asked struct {
		Jobs []string `json:"jobs"`
	}
	node := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&asked)
		_, _ = w.Write([]byte(`{"model":"multilingual-e5-small","hits":[{"job_id":"site-b","passage_id":3,"document":"contrat.pdf","page":12,"text":"préavis","score":0.9}]}`))
	}))
	defer node.Close()
	t.Setenv("SILICIUM_NODE_API_URL", node.URL)

	response := httptest.NewRecorder()
	h.SearchJobDocuments(response, jobRequest("/jobs/1/search?q=r%C3%A9silier&k=5", jobs[0].ID, "7"))
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if strings.Join(asked.Jobs, ",") != "site-b,site-a" { // newest first
		t.Fatalf("jobs searched = %v", asked.Jobs)
	}
	var payload struct {
		Hits []map[string]any `json:"hits"`
	}
	_ = json.Unmarshal(response.Body.Bytes(), &payload)
	if len(payload.Hits) != 1 || payload.Hits[0]["jobId"] != float64(jobs[1].ID) || payload.Hits[0]["page"] != float64(12) {
		t.Fatalf("hits = %v", payload.Hits)
	}

	other := httptest.NewRecorder()
	h.SearchJobDocuments(other, jobRequest("/jobs/1/search?q=x", jobs[0].ID, "8"))
	if other.Code != http.StatusNotFound {
		t.Fatalf("another user's job: status = %d", other.Code)
	}
}

func TestASearchWhileTheModelLoadsAsksToRetry(t *testing.T) {
	h, database := documentTestHandler(t, "document-preparing")
	job := models.Job{UserID: 7, Title: "a", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "site-a", CollectionID: "site-a", InputPath: "/a"}
	database.Create(&job)
	node := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"error":"model_preparing"}`))
	}))
	defer node.Close()
	t.Setenv("SILICIUM_NODE_API_URL", node.URL)
	response := httptest.NewRecorder()
	h.SearchJobDocuments(response, jobRequest("/jobs/1/search?q=x", job.ID, "7"))
	if response.Code != http.StatusServiceUnavailable || response.Header().Get("Retry-After") != "10" {
		t.Fatalf("status = %d, headers = %v", response.Code, response.Header())
	}
	empty := httptest.NewRecorder()
	h.SearchJobDocuments(empty, jobRequest("/jobs/1/search?q=", job.ID, "7"))
	if empty.Code != http.StatusBadRequest {
		t.Fatalf("empty query: status = %d", empty.Code)
	}
}

func TestADocumentOfAResultIsServedToBeReadOnly(t *testing.T) {
	h, database := documentTestHandler(t, "document-open")
	_, created := createDocumentJob(t, h, "7", nil)
	var job models.Job
	database.First(&job, created.ID)
	response := httptest.NewRecorder()
	h.GetJobDocument(response, jobRequest("/jobs/1/documents?name=contrat.pdf", job.ID, "7"))
	if response.Code != http.StatusOK || response.Body.String() != "%PDF-1.4" {
		t.Fatalf("status = %d, body = %q", response.Code, response.Body.String())
	}
	if response.Header().Get("Content-Type") != "application/pdf" || response.Header().Get("Content-Security-Policy") != "sandbox" {
		t.Fatalf("headers = %v", response.Header())
	}
	missing := httptest.NewRecorder()
	h.GetJobDocument(missing, jobRequest("/jobs/1/documents?name=../../etc/passwd", job.ID, "7"))
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing document: status = %d", missing.Code)
	}
}

func TestAFinishedIndexIsSummarizedAndDownloadedAsAZip(t *testing.T) {
	h, database := documentTestHandler(t, "document-export")
	indexDir := filepath.Join(t.TempDir(), "index")
	_ = os.MkdirAll(indexDir, 0o755)
	for _, name := range documents.IndexFiles {
		_ = os.WriteFile(filepath.Join(indexDir, name), []byte(name), 0o600)
	}
	summary := filepath.Join(filepath.Dir(indexDir), "raytracer-summary.json")
	_ = os.WriteFile(summary, []byte(`{"success":true}`), 0o600)
	job := models.Job{UserID: 7, Title: "a", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "site-a", CollectionID: "site-a", InputPath: "/a", ResultPath: filepath.Join(indexDir, "index.json"), SummaryPath: summary}
	database.Create(&job)
	_ = os.WriteFile(job.ResultPath, []byte(`{"passage_count":3,"documents":[{"name":"a.pdf","pages":2,"passages":3}],"skipped":[{"name":"scan.pdf","reason":"no_text"}]}`), 0o600)
	dashboard := httptest.NewRecorder()
	h.GetJobDashboard(dashboard, jobRequest("/jobs/1/dashboard", job.ID, "7"))
	var payload struct {
		DocumentIndex struct {
			PassageCount float64          `json:"passageCount"`
			Skipped      []map[string]any `json:"skipped"`
		} `json:"documentIndex"`
	}
	_ = json.Unmarshal(dashboard.Body.Bytes(), &payload)
	if payload.DocumentIndex.PassageCount != 3 || len(payload.DocumentIndex.Skipped) != 1 {
		t.Fatalf("dashboard document index = %+v", payload.DocumentIndex)
	}
	response := httptest.NewRecorder()
	h.GetJobResult(response, jobRequest("/jobs/1/result", job.ID, "7"))
	if response.Code != http.StatusOK || response.Header().Get("Content-Type") != "application/zip" || !bytes.HasPrefix(response.Body.Bytes(), []byte("PK")) {
		t.Fatalf("status = %d, headers = %v", response.Code, response.Header())
	}
}

func TestTheDocumentsOfTheWholeCollectionAreListed(t *testing.T) {
	h, database := documentTestHandler(t, "document-collection-list")
	dir := t.TempDir()
	index := func(name string, documents string) string {
		path := filepath.Join(dir, name)
		_ = os.WriteFile(path, []byte(`{"documents":`+documents+`}`), 0o644)
		return path
	}
	jobs := []models.Job{
		{UserID: 7, Title: "a", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "list-a", CollectionID: "list-a", InputPath: "/a", ResultPath: index("a.json", `[{"name":"contrat.pdf","pages":12,"passages":40}]`)},
		{UserID: 7, Title: "b", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "list-b", CollectionID: "list-a", InputPath: "/b", ResultPath: index("b.json", `[{"name":"notes/avenant.md","pages":0,"passages":3}]`)},
		{UserID: 8, Title: "c", Workload: silicium.DocumentSearchWorkload, Status: "completed", SiliciumJobID: "list-c", CollectionID: "list-a", InputPath: "/c", ResultPath: index("c.json", `[{"name":"secret.pdf"}]`)},
	}
	for i := range jobs {
		database.Create(&jobs[i])
	}
	listed := h.collectionDocuments(jobs[0])
	if len(listed) != 2 || listed[0]["name"] != "notes/avenant.md" || listed[1]["name"] != "contrat.pdf" || listed[1]["jobId"] != jobs[0].ID {
		t.Fatalf("listed = %v", listed)
	}
}
