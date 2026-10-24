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

	"github.com/silicium/internal/batchai"
	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

const batchAIRequest = `{"format":"silicium-llm-request/1","task":"summarize","instruction":"Résume.","output":{"kind":"text"},"items":["Un long texte.","Un autre."]}`

// batchAIForm is a job creation request for a batch AI job by `userID`.
func batchAIForm(t *testing.T, userID, request string, consent bool) *http.Request {
	t.Helper()
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	_ = form.WriteField("workload", silicium.BatchAIWorkload)
	if consent {
		_ = form.WriteField("acknowledge_sharing", "1")
	}
	part, err := form.CreateFormFile("file", "request.json")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = part.Write([]byte(request))
	if err := form.Close(); err != nil {
		t.Fatal(err)
	}
	httpRequest := httptest.NewRequest(http.MethodPost, "/jobs", &body)
	httpRequest.Header.Set("Content-Type", form.FormDataContentType())
	httpRequest.Header.Set("Accept-Language", "fr")
	return httpRequest.WithContext(context.WithValue(httpRequest.Context(), contextkeys.UserIDKey, userID))
}

func TestABatchAIJobStoresItsRequestAndSummary(t *testing.T) {
	h, database := documentTestHandler(t, "llm-create")
	response := httptest.NewRecorder()
	h.CreateJob(response, batchAIForm(t, "7", batchAIRequest, true))
	if response.Code != http.StatusAccepted {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var created models.Job
	_ = json.Unmarshal(response.Body.Bytes(), &created)
	var job models.Job
	database.First(&job, created.ID)
	if job.Title != batchAITitle || filepath.Base(job.InputPath) != batchai.RequestName {
		t.Fatalf("stored job = %#v", job)
	}
	summary, err := batchai.ReadSummary(job.InputPath)
	if err != nil || summary.ItemCount != 2 || summary.Instruction != "Résume." {
		t.Fatalf("summary = %#v, %v", summary, err)
	}
}

func TestABatchAIJobNeedsConsentAndAValidRequest(t *testing.T) {
	h, _ := documentTestHandler(t, "llm-refused")
	response := httptest.NewRecorder()
	h.CreateJob(response, batchAIForm(t, "7", batchAIRequest, false))
	if response.Code != http.StatusBadRequest || !strings.Contains(response.Body.String(), "machines du réseau") {
		t.Fatalf("consent: status = %d, body = %s", response.Code, response.Body.String())
	}
	response = httptest.NewRecorder()
	h.CreateJob(response, batchAIForm(t, "7", strings.Replace(batchAIRequest, `"Un autre."`, `"  "`, 1), true))
	if response.Code != http.StatusBadRequest || !strings.Contains(response.Body.String(), "L’élément n° 2 est vide.") {
		t.Fatalf("empty item: status = %d, body = %s", response.Code, response.Body.String())
	}
}

// batchAIJobOnDisk is a batch AI job of user 7 whose node files are in a
// temporary workload storage.
func batchAIJobOnDisk(t *testing.T, name string) (Handler, models.Job, string) {
	t.Helper()
	h, database := documentTestHandler(t, name)
	workloadRoot := t.TempDir()
	t.Setenv("SILICIUM_NETWORK_ROOT", t.TempDir())
	t.Setenv("SILICIUM_WORKLOAD_STORAGE_DIR", workloadRoot)
	inputPath, err := batchai.Store(t.TempDir(), []byte(batchAIRequest))
	if err != nil {
		t.Fatal(err)
	}
	job := models.Job{UserID: 7, Title: "t", Workload: silicium.BatchAIWorkload, Status: "running", SiliciumJobID: "site-llm-" + name, InputPath: inputPath}
	database.Create(&job)
	return h, job, filepath.Join(workloadRoot, "llm", job.SiliciumJobID)
}

func answersOf(t *testing.T, h Handler, job models.Job, query string) map[string]any {
	t.Helper()
	response := httptest.NewRecorder()
	h.GetJobAnswers(response, jobRequest("/jobs/1/answers"+query, job.ID, "7"))
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var payload map[string]any
	_ = json.Unmarshal(response.Body.Bytes(), &payload)
	return payload
}

func TestAnswersAreShownAsFragmentsAreVerifiedThenDownloaded(t *testing.T) {
	h, job, jobDir := batchAIJobOnDisk(t, "llm-answers")
	payload := answersOf(t, h, job, "")
	if payload["total"] != 2.0 || payload["available"] != 0.0 || payload["complete"] != false {
		t.Fatalf("nothing yet: %#v", payload)
	}

	_ = os.MkdirAll(filepath.Join(jobDir, "fragments"), 0o755)
	_ = os.WriteFile(filepath.Join(jobDir, "fragments", "fragment-001.jsonl"), []byte(`{"id":1,"input":"Un autre.","output":"Bref."}`+"\n"), 0o644)
	payload = answersOf(t, h, job, "")
	items := payload["items"].([]any)
	if payload["available"] != 1.0 || len(items) != 1 || items[0].(map[string]any)["output"] != "Bref." {
		t.Fatalf("one verified fragment: %#v", payload)
	}

	answersDir := filepath.Join(jobDir, "answers")
	_ = os.MkdirAll(answersDir, 0o755)
	_ = os.WriteFile(filepath.Join(answersDir, "answers.jsonl"), []byte(`{"id":0,"input":"Un long texte.","output":"Long."}`+"\n"+`{"id":1,"input":"Un autre.","output":"Bref."}`+"\n"), 0o644)
	_ = os.WriteFile(filepath.Join(answersDir, "answers.csv"), []byte("\ufeff\"id\",\"input\",\"output\"\r\n"), 0o644)
	_ = os.WriteFile(filepath.Join(answersDir, "result.json"), []byte(`{"format":"silicium-llm-result/1","item_count":2,"answered":2,"model":{"id":"qwen2.5-1.5b-instruct"}}`), 0o644)
	_ = os.WriteFile(filepath.Join(jobDir, "raytracer-summary.json"), []byte(`{"success":true,"result_path":"`+filepath.ToSlash(filepath.Join(answersDir, "result.json"))+`"}`), 0o644)
	payload = answersOf(t, h, job, "?offset=1&limit=5")
	items = payload["items"].([]any)
	if payload["complete"] != true || payload["available"] != 2.0 || len(items) != 1 || items[0].(map[string]any)["id"] != 1.0 {
		t.Fatalf("finished: %#v", payload)
	}

	response := httptest.NewRecorder()
	h.GetJobResult(response, jobRequest("/jobs/1/result", job.ID, "7"))
	if response.Code != http.StatusOK || !strings.HasPrefix(response.Header().Get("Content-Type"), "text/csv") || !strings.Contains(response.Header().Get("Content-Disposition"), ".csv") {
		t.Fatalf("csv: status = %d, headers = %v", response.Code, response.Header())
	}
	response = httptest.NewRecorder()
	h.GetJobResult(response, jobRequest("/jobs/1/result?format=jsonl", job.ID, "7"))
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"Long."`) {
		t.Fatalf("jsonl: status = %d, body = %s", response.Code, response.Body.String())
	}

	response = httptest.NewRecorder()
	h.GetJobDashboard(response, jobRequest("/jobs/1/dashboard", job.ID, "7"))
	var dashboard map[string]any
	_ = json.Unmarshal(response.Body.Bytes(), &dashboard)
	batchAI, _ := dashboard["batchAI"].(map[string]any)
	if batchAI == nil || batchAI["request"].(map[string]any)["itemCount"] != 2.0 || batchAI["result"].(map[string]any)["answered"] != 2.0 {
		t.Fatalf("dashboard = %#v", dashboard["batchAI"])
	}
}

func TestAnswersAreOnlyForTheOwnersBatchAIJobs(t *testing.T) {
	h, job, _ := batchAIJobOnDisk(t, "llm-owner")
	response := httptest.NewRecorder()
	h.GetJobAnswers(response, jobRequest("/jobs/1/answers", job.ID, "8"))
	if response.Code != http.StatusNotFound {
		t.Fatalf("another user: status = %d", response.Code)
	}
	h.DB.Model(&job).Update("workload", "raytracer")
	response = httptest.NewRecorder()
	h.GetJobAnswers(response, jobRequest("/jobs/1/answers", job.ID, "7"))
	if response.Code != http.StatusNotFound {
		t.Fatalf("not a batch AI job: status = %d", response.Code)
	}
}
