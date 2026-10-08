package silicium

// Search over finished document-search jobs, answered by the Rust node
// that published them (POST /v1/embedding/search): it embeds the query with
// the jobs' pinned model and returns the closest passages.

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"
)

// ErrModelPreparing: the node is still downloading or loading the model;
// the search can be retried in a few seconds.
var ErrModelPreparing = errors.New("model_preparing")

// documentSearchTimeout leaves the node time to load a large index on the
// first search of a collection.
const documentSearchTimeout = 30 * time.Second

// MaxSearchQueryRunes bounds a query, as the node does.
const MaxSearchQueryRunes = 1000

// DocumentHit is one passage found by a search.
type DocumentHit struct {
	// JobID is the Silicium id of the job holding the passage.
	JobID     string `json:"job_id"`
	PassageID uint64 `json:"passage_id"`
	Document  string `json:"document"`
	Page      *int   `json:"page"`
	// Section is the heading path of the passage ("Bail › Article 6"),
	// empty when the document has no headings there.
	Section string  `json:"section,omitempty"`
	Text    string  `json:"text"`
	Score   float64 `json:"score"`
}

type documentSearchRequest struct {
	Jobs  []string `json:"jobs"`
	Query string   `json:"query"`
	TopK  int      `json:"top_k"`
}

type documentSearchResponse struct {
	Model string        `json:"model"`
	Hits  []DocumentHit `json:"hits"`
}

// SearchDocuments returns the `topK` passages of the jobs `siliciumJobIDs`
// closest to `query`, best first.
func SearchDocuments(ctx context.Context, cfg RunnerConfig, siliciumJobIDs []string, query string, topK int) ([]DocumentHit, error) {
	query = strings.TrimSpace(query)
	if query == "" || len(siliciumJobIDs) == 0 {
		return nil, nil
	}
	request := documentSearchRequest{Jobs: siliciumJobIDs, Query: query, TopK: topK}
	var response documentSearchResponse
	err := nodeControlRequestWithin(ctx, cfg, documentSearchTimeout, http.MethodPost, "/v1/embedding/search", request, &response)
	var failure *ControlError
	if errors.As(err, &failure) && failure.Status == http.StatusServiceUnavailable {
		return nil, ErrModelPreparing
	}
	if err != nil {
		return nil, err
	}
	return response.Hits, nil
}
