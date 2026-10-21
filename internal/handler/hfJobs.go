// Jobs of the AI catalogue ("Catalogue IA", workloads `ai/hf/<task>/<key>`):
// the upload of the request, the quote (warm or cold model), what the job
// page shows, the answers and the download.

package handler

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"mime"
	"net/http"
	"path/filepath"
	"strconv"
	"sync"
	"time"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/aijobs"
	"github.com/silicium/internal/catalog"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
	"gorm.io/gorm"
)

const hfTitle = "Catalogue IA"

// admittedModel returns the catalogue row of `key` for `task` when it is
// admitted and the network runs the task.
func (h *Handler) admittedModel(task, key string) (catalog.Model, string) {
	if !catalog.NetworkReady(task) {
		return catalog.Model{}, "hf.task_unavailable"
	}
	row, err := h.catalogStore().Get(key)
	if errors.Is(err, gorm.ErrRecordNotFound) || (err == nil && (row.Task != task || row.Status != string(catalog.StatusAdmitted))) {
		return catalog.Model{}, "hf.model_unavailable"
	}
	if err != nil {
		return catalog.Model{}, "job.input_store_failed"
	}
	return row, ""
}

// storeHFInput stores the request of a new catalogue job (the `file` field,
// `silicium-hf-site-request/1`) with the catalogue's manifest of the model.
// The user must have confirmed that the machines of the network read the
// items.
func (h *Handler) storeHFInput(r *http.Request, inputDir, workload string) (string, int, string, []any) {
	task, key, _ := silicium.ParseHF(workload)
	row, refusal := h.admittedModel(task, key)
	if refusal != "" {
		return "", http.StatusBadRequest, refusal, nil
	}
	if !formFlag(r.FormValue("acknowledge_sharing")) {
		return "", http.StatusBadRequest, "hf.consent_required", nil
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		return "", http.StatusBadRequest, "job.input_required", nil
	}
	defer file.Close()
	if header.Size > aijobs.MaxSiteRequestByte {
		return "", http.StatusRequestEntityTooLarge, "hf.request_too_large", nil
	}
	data, err := io.ReadAll(io.LimitReader(file, aijobs.MaxSiteRequestByte+1))
	if err != nil {
		return "", http.StatusBadRequest, "job.form_invalid", nil
	}
	if len(data) > aijobs.MaxSiteRequestByte {
		return "", http.StatusRequestEntityTooLarge, "hf.request_too_large", nil
	}
	model := aijobs.Model{
		Key: row.Key, Repository: row.Repository, Revision: row.Revision,
		Licence: row.Licence, HardwareClass: row.HardwareClass,
	}
	path, err := aijobs.Store(inputDir, data, task, json.RawMessage(row.Manifest), model, row.CanaryItems())
	if err == nil {
		return path, 0, "", nil
	}
	var refused *aijobs.UserError
	if errors.As(err, &refused) {
		return "", http.StatusBadRequest, refused.Key, refused.Args
	}
	log.Printf("store catalogue request in %q: %v", inputDir, err)
	return "", http.StatusInternalServerError, "job.input_store_failed", nil
}

// hfDashboard is what the job page shows about a catalogue job: the
// request, and once done the number of answers. Nil for other jobs.
func hfDashboard(job models.Job) map[string]any {
	if !silicium.IsHF(job.Workload) {
		return nil
	}
	summary, err := aijobs.ReadSummary(job.InputPath)
	if err != nil {
		return map[string]any{"request": nil}
	}
	payload := map[string]any{"request": summary}
	if regularFile(job.ResultPath) {
		result := readJSONMap(job.ResultPath)
		payload["result"] = map[string]any{"model": result["model"], "itemCount": result["item_count"]}
	}
	return payload
}

// getHFAnswers answers GET /jobs/{id}/answers for a catalogue job, once it
// is done.
func (h *Handler) getHFAnswers(w http.ResponseWriter, r *http.Request, job models.Job) {
	job = h.refreshRaytracerArtifacts(job)
	offset := boundedQueryInt(r, "offset", 0, 0, aijobs.MaxItems)
	limit := boundedQueryInt(r, "limit", 50, 1, maxAnswersPage)
	total := 0
	if summary, err := aijobs.ReadSummary(job.InputPath); err == nil {
		total = summary.ItemCount
	}
	complete := regularFile(job.ResultPath)
	rows, available := []aijobs.Row{}, 0
	if complete {
		var err error
		rows, available, err = aijobs.ReadAnswers(filepath.Join(filepath.Dir(job.ResultPath), "answers.jsonl"), offset, limit)
		if err != nil {
			log.Printf("answers of job %d: %v", job.ID, err)
			http.Error(w, "Answers unavailable", http.StatusInternalServerError)
			return
		}
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, http.StatusOK, map[string]any{
		"total": total, "available": available, "complete": complete, "offset": offset, "items": rows,
	})
}

// writeHFResult sends the answers of a finished catalogue job (JSON Lines).
func writeHFResult(w http.ResponseWriter, r *http.Request, job models.Job) {
	path := filepath.Join(filepath.Dir(job.ResultPath), "answers.jsonl")
	if !regularFile(path) {
		http.Error(w, "Result is not ready", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/x-ndjson; charset=utf-8")
	w.Header().Set("Content-Disposition", mime.FormatMediaType("attachment", map[string]string{"filename": "reponses-" + strconv.Itoa(int(job.ID)) + ".jsonl"}))
	w.Header().Set("X-Content-Type-Options", "nosniff")
	http.ServeFile(w, r, path)
}

// peersCache keeps the node's peers for a few seconds: every quote of the
// site page would otherwise ask the node.
var peersCache struct {
	sync.Mutex
	at      time.Time
	payload map[string]any
}

// networkPeers is overridden by the tests.
var networkPeers = func(r *http.Request) (map[string]any, error) {
	peersCache.Lock()
	defer peersCache.Unlock()
	if peersCache.payload != nil && time.Since(peersCache.at) < 15*time.Second {
		return peersCache.payload, nil
	}
	payload, err := silicium.ListControlPeers(r.Context(), silicium.ConfigFromEnv())
	if err != nil {
		return nil, err
	}
	peersCache.at, peersCache.payload = time.Now(), payload
	return payload, nil
}

// GetCatalogQuote answers GET /catalog/models/{key}/quote?items=N: the
// estimated price of a job of N items, with how many workers have the model.
func (h *Handler) GetCatalogQuote(w http.ResponseWriter, r *http.Request) {
	row, err := h.catalogStore().Get(mux.Vars(r)["key"])
	if err != nil || row.Status != string(catalog.StatusAdmitted) {
		http.Error(w, "Model not found", http.StatusNotFound)
		return
	}
	items := boundedQueryInt(r, "items", 1, 1, aijobs.MaxItems)
	availability := catalog.Availability{}
	networkKnown := true
	if payload, err := networkPeers(r); err == nil {
		availability = catalog.AvailabilityFromPeers(payload, row.Key)
	} else {
		networkKnown = false
	}
	quote := catalog.QuoteFor(row, items, availability)
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, http.StatusOK, map[string]any{"quote": quote, "networkKnown": networkKnown})
}
