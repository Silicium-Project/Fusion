// Batch AI processing ("Traitement par IA"): the upload of the request,
// what the job page shows about it, the answers (verified fragments while
// the job runs, every answer once it is done) and the downloads.

package handler

import (
	"errors"
	"io"
	"log"
	"mime"
	"net/http"
	"path/filepath"
	"strconv"

	"github.com/silicium/internal/batchai"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

const batchAITitle = "Traitement par IA"

// maxAnswersPage bounds the answers sent at once.
const maxAnswersPage = 200

// storeBatchAIInput stores the request of a new batch AI job (the `file`
// field, `silicium-llm-request/1`). The user must have confirmed that the
// machines of the network read the items. On failure it returns the HTTP
// status and the i18n key of the message with its arguments.
func storeBatchAIInput(r *http.Request, inputDir string) (string, int, string, []any) {
	if !formFlag(r.FormValue("acknowledge_sharing")) {
		return "", http.StatusBadRequest, "llm.consent_required", nil
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		return "", http.StatusBadRequest, "job.input_required", nil
	}
	defer file.Close()
	if header.Size > batchai.MaxRequestBytes {
		return "", http.StatusRequestEntityTooLarge, "job.input_too_large", nil
	}
	data, err := io.ReadAll(io.LimitReader(file, batchai.MaxRequestBytes+1))
	if err != nil {
		return "", http.StatusBadRequest, "job.form_invalid", nil
	}
	if len(data) > batchai.MaxRequestBytes {
		return "", http.StatusRequestEntityTooLarge, "job.input_too_large", nil
	}
	path, err := batchai.Store(inputDir, data)
	if err == nil {
		return path, 0, "", nil
	}
	var refused *batchai.UserError
	if errors.As(err, &refused) {
		return "", http.StatusBadRequest, refused.Key, refused.Args
	}
	log.Printf("store batch AI request in %q: %v", inputDir, err)
	return "", http.StatusInternalServerError, "job.input_store_failed", nil
}

// batchAIDashboard is what the job page shows about a batch AI job: the
// request, and once done the model and the number of answers. Nil for
// other jobs.
func batchAIDashboard(job models.Job) map[string]any {
	if !silicium.IsBatchAI(job.Workload) {
		return nil
	}
	summary, err := batchai.ReadSummary(job.InputPath)
	if err != nil {
		return map[string]any{"request": nil}
	}
	payload := map[string]any{"request": summary}
	if regularFile(job.ResultPath) {
		result := readJSONMap(job.ResultPath)
		payload["result"] = map[string]any{
			"model":     result["model"],
			"itemCount": result["item_count"],
			"answered":  result["answered"],
		}
	}
	return payload
}

// GetJobAnswers answers GET /jobs/{id}/answers?offset=…&limit=…: answered
// items of a batch AI job, in order. While the job runs, only the items of
// verified fragments are there.
func (h *Handler) GetJobAnswers(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	if silicium.IsHF(job.Workload) {
		h.getHFAnswers(w, r, job)
		return
	}
	if !silicium.IsBatchAI(job.Workload) {
		http.Error(w, "Not a batch AI job", http.StatusNotFound)
		return
	}
	job = h.refreshRaytracerArtifacts(job)
	offset := boundedQueryInt(r, "offset", 0, 0, batchai.MaxItems)
	limit := boundedQueryInt(r, "limit", 50, 1, maxAnswersPage)
	total := 0
	if summary, err := batchai.ReadSummary(job.InputPath); err == nil {
		total = summary.ItemCount
	}
	complete := regularFile(job.ResultPath)
	var (
		rows      []batchai.Row
		available int
		err       error
	)
	if complete {
		rows, available, err = batchai.ReadAnswers(filepath.Join(filepath.Dir(job.ResultPath), "answers.jsonl"), offset, limit)
	} else {
		rows, available, err = []batchai.Row{}, 0, nil
		for _, jobDir := range raytracerJobDirectories(job) {
			rows, available, err = batchai.ReadPreviews(jobDir, offset, limit)
			if err != nil || available > 0 {
				break
			}
		}
	}
	if err != nil {
		log.Printf("answers of job %d: %v", job.ID, err)
		http.Error(w, "Answers unavailable", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, http.StatusOK, map[string]any{
		"total":     total,
		"available": available,
		"complete":  complete,
		"offset":    offset,
		"items":     rows,
	})
}

// writeBatchAIResult sends the answers of a finished batch AI job: the CSV
// table, or the JSON Lines file with `?format=jsonl`.
func writeBatchAIResult(w http.ResponseWriter, r *http.Request, job models.Job) {
	name, contentType, extension := "answers.csv", "text/csv; charset=utf-8", "csv"
	if r.URL.Query().Get("format") == "jsonl" {
		name, contentType, extension = "answers.jsonl", "application/x-ndjson; charset=utf-8", "jsonl"
	}
	path := filepath.Join(filepath.Dir(job.ResultPath), name)
	if !regularFile(path) {
		http.Error(w, "Result is not ready", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Content-Disposition", mime.FormatMediaType("attachment", map[string]string{"filename": "reponses-" + strconv.Itoa(int(job.ID)) + "." + extension}))
	w.Header().Set("X-Content-Type-Options", "nosniff")
	http.ServeFile(w, r, path)
}
