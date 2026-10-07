// Document search ("Recherche dans mes documents"): the upload of the
// documents, the collection a job adds them to, the search over a
// collection, a document opened from a result, and the index export.
//
// A collection is the set of document-search jobs a user searches
// together: its first job, then every job that added documents to it
// (`collection_id` of the form). Searching a job searches its whole
// collection.

package handler

import (
	"context"
	"errors"
	"log"
	"mime"
	"mime/multipart"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/silicium/internal/documents"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

const documentSearchTitle = "Recherche dans mes documents"

// maxCollectionJobs bounds the jobs searched at once (the node's limit).
const maxCollectionJobs = 200

// searchTimeout bounds a search request (the node call itself is bounded
// to 30 s by the silicium package).
const searchTimeout = 35 * time.Second

// storeDocumentSearchInput stores the documents of a new document search.
// The user must have confirmed that the machines of the network read them.
// On failure it returns the HTTP status and the message for the user.
func storeDocumentSearchInput(r *http.Request, inputDir string) (string, int, string) {
	if !formFlag(r.FormValue("acknowledge_sharing")) {
		return "", http.StatusBadRequest, "Confirme que les documents peuvent être lus par les machines du réseau."
	}
	files := make([]*multipart.FileHeader, 0, len(r.MultipartForm.File["files"])+1)
	files = append(files, r.MultipartForm.File["files"]...)
	files = append(files, r.MultipartForm.File["file"]...)
	inputPath, err := documents.Store(inputDir, files)
	if err == nil {
		return inputPath, 0, ""
	}
	if message := documents.UserMessage(err); message != "" {
		return "", http.StatusBadRequest, message
	}
	log.Printf("store documents in %q: %v", inputDir, err)
	return "", http.StatusInternalServerError, "Les documents n'ont pas pu être enregistrés."
}

// collectionForNewJob is the collection a new document search joins: the
// requested one when it belongs to the user, else a new one named after the
// job. False when the requested collection is not the user's.
func (h *Handler) collectionForNewJob(userID uint, requested, jobID string) (string, bool) {
	requested = strings.TrimSpace(requested)
	if requested == "" {
		return jobID, true
	}
	var count int64
	h.DB.Model(&models.Job{}).
		Where("user_id = ? AND collection_id = ? AND workload = ?", userID, requested, silicium.DocumentSearchWorkload).
		Count(&count)
	return requested, count > 0
}

// collectionOf is the collection of a document-search job (jobs created
// before collections are their own).
func collectionOf(job models.Job) string {
	if strings.TrimSpace(job.CollectionID) != "" {
		return job.CollectionID
	}
	return job.SiliciumJobID
}

// searchableJobs are the finished jobs of `job`'s collection.
func (h *Handler) searchableJobs(job models.Job) []models.Job {
	var jobs []models.Job
	h.DB.Where("user_id = ? AND workload = ? AND status = ? AND (collection_id = ? OR silicium_job_id = ?)",
		job.UserID, silicium.DocumentSearchWorkload, "completed", collectionOf(job), collectionOf(job)).
		// Newest first: a collection over the limit loses its oldest jobs.
		Order("created_at desc, id desc").
		Limit(maxCollectionJobs).
		Find(&jobs)
	return jobs
}

// SearchJobDocuments answers GET /jobs/{id}/search?q=…&k=…: the passages of
// the job's collection closest to the query, best first.
func (h *Handler) SearchJobDocuments(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	if !silicium.IsDocumentSearch(job.Workload) {
		http.Error(w, "Not a document search", http.StatusNotFound)
		return
	}
	query := strings.TrimSpace(r.URL.Query().Get("q"))
	if query == "" || utf8.RuneCountInString(query) > silicium.MaxSearchQueryRunes {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_query", "message": "Pose une question de 1 à 1 000 caractères."})
		return
	}
	limit := boundedQueryInt(r, "k", 10, 1, 50)
	jobs := h.searchableJobs(job)
	jobIDs := make(map[string]uint, len(jobs))
	siliciumIDs := make([]string, 0, len(jobs))
	for _, candidate := range jobs {
		jobIDs[candidate.SiliciumJobID] = candidate.ID
		siliciumIDs = append(siliciumIDs, candidate.SiliciumJobID)
	}
	if len(siliciumIDs) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"query": query, "hits": []any{}, "searchedJobs": 0})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), searchTimeout)
	defer cancel()
	hits, err := silicium.SearchDocuments(ctx, silicium.ConfigFromEnv(), siliciumIDs, query, limit)
	if errors.Is(err, silicium.ErrModelPreparing) {
		w.Header().Set("Retry-After", "10")
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "model_preparing", "message": "Le moteur de recherche se prépare, réessaie dans quelques secondes."})
		return
	}
	if err != nil {
		log.Printf("document search for job %d: %v", job.ID, err)
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "search_unavailable", "message": "La recherche est momentanément indisponible."})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"query": query, "hits": searchResults(hits, jobIDs), "searchedJobs": len(siliciumIDs)})
}

// searchResults are the hits as the site shows them, with the site's job ids.
func searchResults(hits []silicium.DocumentHit, jobIDs map[string]uint) []map[string]any {
	results := make([]map[string]any, 0, len(hits))
	for _, hit := range hits {
		jobID, known := jobIDs[hit.JobID]
		if !known {
			continue
		}
		results = append(results, map[string]any{
			"jobId":     jobID,
			"passageId": hit.PassageID,
			"document":  hit.Document,
			"page":      hit.Page,
			"text":      hit.Text,
			"score":     hit.Score,
		})
	}
	return results
}

// GetJobDocument answers GET /jobs/{id}/documents?name=…: a document of the
// job, to open a search result. It is served to be read, never run.
func (h *Handler) GetJobDocument(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	if !silicium.IsDocumentSearch(job.Workload) {
		http.Error(w, "Not a document search", http.StatusNotFound)
		return
	}
	document, err := documents.Open(job.InputPath, r.URL.Query().Get("name"))
	if errors.Is(err, documents.ErrNotFound) {
		http.Error(w, "Document not found", http.StatusNotFound)
		return
	}
	if err != nil {
		log.Printf("open document of job %d: %v", job.ID, err)
		http.Error(w, "Document unavailable", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", document.ContentType)
	w.Header().Set("Content-Disposition", mime.FormatMediaType("inline", map[string]string{"filename": document.Name}))
	w.Header().Set("Content-Security-Policy", "sandbox")
	w.Header().Set("Cache-Control", "private, max-age=3600")
	w.Header().Set("Content-Length", strconv.Itoa(len(document.Content)))
	_, _ = w.Write(document.Content)
}

// writeDocumentIndexExport sends the finished index of a document search as
// a ZIP (the "Avancé" download of the site).
func writeDocumentIndexExport(w http.ResponseWriter, job models.Job) {
	indexDir := filepath.Dir(job.ResultPath)
	for _, name := range documents.IndexFiles {
		if !regularFile(filepath.Join(indexDir, name)) {
			http.Error(w, "Result is not ready", http.StatusNotFound)
			return
		}
	}
	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", mime.FormatMediaType("attachment", map[string]string{"filename": "index-" + strconv.Itoa(int(job.ID)) + ".zip"}))
	if err := documents.WriteIndexArchive(w, indexDir); err != nil {
		log.Printf("export index of job %d: %v", job.ID, err)
	}
}

// documentIndexSummary is what the site shows about a finished document
// search: the documents read and the files skipped with their reason (a
// scanned PDF has no text...). Nil for other jobs and unfinished ones.
func documentIndexSummary(job models.Job) map[string]any {
	if !silicium.IsDocumentSearch(job.Workload) || !regularFile(job.ResultPath) {
		return nil
	}
	index := readJSONMap(job.ResultPath)
	return map[string]any{
		"documents":    index["documents"],
		"skipped":      index["skipped"],
		"passageCount": index["passage_count"],
	}
}

func formFlag(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "on", "yes":
		return true
	default:
		return false
	}
}
