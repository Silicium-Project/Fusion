// The Hub client: read-only calls to the public Hugging Face API. No token
// is needed for public models; `SILICIUM_HF_TOKEN` raises the rate limit.

package catalog

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// DefaultHubEndpoint is the public Hub.
const DefaultHubEndpoint = "https://huggingface.co"

// maxHubResponseBytes bounds one response of the Hub (a tree of a large
// repository is a few MB).
const maxHubResponseBytes = 32 << 20

// ErrHubUnavailable wraps every failure to reach the Hub or to read its
// answer: the caller keeps the last catalogue.
var ErrHubUnavailable = errors.New("hub unavailable")

// Hub reads models from the Hugging Face API.
type Hub struct {
	Endpoint string
	Token    string
	Client   *http.Client
}

// NewHub returns a client of `endpoint` (DefaultHubEndpoint when empty).
func NewHub(endpoint, token string) *Hub {
	endpoint = strings.TrimRight(strings.TrimSpace(endpoint), "/")
	if endpoint == "" {
		endpoint = DefaultHubEndpoint
	}
	return &Hub{
		Endpoint: endpoint,
		Token:    strings.TrimSpace(token),
		Client:   &http.Client{Timeout: 60 * time.Second},
	}
}

// Gated is the `gated` field of a model: false, or "auto" / "manual".
type Gated bool

func (g *Gated) UnmarshalJSON(data []byte) error {
	var asBool bool
	if err := json.Unmarshal(data, &asBool); err == nil {
		*g = Gated(asBool)
		return nil
	}
	var asString string
	if err := json.Unmarshal(data, &asString); err == nil {
		*g = Gated(asString != "" && asString != "false")
		return nil
	}
	*g = true // Unknown shape: assume restricted.
	return nil
}

// Licences is `cardData.license`: one identifier or a list.
type Licences []string

func (l *Licences) UnmarshalJSON(data []byte) error {
	var one string
	if err := json.Unmarshal(data, &one); err == nil {
		*l = Licences{one}
		return nil
	}
	var many []string
	if err := json.Unmarshal(data, &many); err != nil {
		*l = nil
		return nil
	}
	*l = many
	return nil
}

// CardData is the part of the model card the catalogue reads.
type CardData struct {
	License     Licences `json:"license"`
	LicenseName string   `json:"license_name"`
}

// ModelConfig is the part of `config.json` the Hub exposes.
type ModelConfig struct {
	Architectures []string        `json:"architectures"`
	ModelType     string          `json:"model_type"`
	AutoMap       json.RawMessage `json:"auto_map"`
	Diffusers     *struct {
		ClassName string `json:"_class_name"`
	} `json:"diffusers"`
}

// TransformersInfo is how `transformers` loads the model.
type TransformersInfo struct {
	AutoModel   string `json:"auto_model"`
	PipelineTag string `json:"pipeline_tag"`
	Processor   string `json:"processor"`
}

// SafetensorsInfo counts the parameters by dtype.
type SafetensorsInfo struct {
	Parameters map[string]int64 `json:"parameters"`
	Total      int64            `json:"total"`
}

// Sibling is a file of the repository at the listed commit.
type Sibling struct {
	Name string `json:"rfilename"`
}

// ModelInfo is what the Hub says about a model.
type ModelInfo struct {
	ID               string            `json:"id"`
	SHA              string            `json:"sha"`
	PipelineTag      string            `json:"pipeline_tag"`
	LibraryName      string            `json:"library_name"`
	Tags             []string          `json:"tags"`
	Private          bool              `json:"private"`
	Disabled         bool              `json:"disabled"`
	Gated            Gated             `json:"gated"`
	Downloads        int64             `json:"downloads"`
	Likes            int64             `json:"likes"`
	LastModified     string            `json:"lastModified"`
	CardData         *CardData         `json:"cardData"`
	Config           *ModelConfig      `json:"config"`
	TransformersInfo *TransformersInfo `json:"transformersInfo"`
	Safetensors      *SafetensorsInfo  `json:"safetensors"`
	Siblings         []Sibling         `json:"siblings"`
	WidgetData       []json.RawMessage `json:"widgetData"`
}

// HasTag reports whether the model has `tag`.
func (m ModelInfo) HasTag(tag string) bool {
	for _, t := range m.Tags {
		if t == tag {
			return true
		}
	}
	return false
}

// TreeEntry is a file of the repository tree at a commit. `OID` is the git
// blob hash (SHA-1); `LFS.OID` is the SHA-256 of a large file's content.
type TreeEntry struct {
	Type string `json:"type"`
	Path string `json:"path"`
	Size int64  `json:"size"`
	OID  string `json:"oid"`
	LFS  *struct {
		OID  string `json:"oid"`
		Size int64  `json:"size"`
	} `json:"lfs"`
}

// repoID is an `owner/name` or a bare `name` of the Hub.
var repoID = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,95}(/[A-Za-z0-9][A-Za-z0-9._-]{0,95})?$`)

// commitSHA is a full git commit hash.
var commitSHA = regexp.MustCompile(`^[0-9a-f]{40}$`)

// Tasks returns the libraries of each task (`/api/tasks`).
func (h *Hub) Tasks(ctx context.Context) (map[string][]string, error) {
	var raw map[string]struct {
		Libraries []string `json:"libraries"`
	}
	if _, err := h.get(ctx, h.Endpoint+"/api/tasks", &raw); err != nil {
		return nil, err
	}
	out := make(map[string][]string, len(raw))
	for id, task := range raw {
		out[id] = task.Libraries
	}
	return out, nil
}

// ListModels returns the `limit` most downloaded models of `task`. A listing
// gives the commit, the tags and the files but not the whole description
// (no card, no `transformersInfo`, an empty `config`): read Model for that.
func (h *Hub) ListModels(ctx context.Context, task string, limit int) ([]ModelInfo, error) {
	if limit <= 0 {
		return nil, nil
	}
	query := url.Values{}
	query.Set("pipeline_tag", task)
	query.Set("sort", "downloads")
	query.Set("direction", "-1")
	query.Set("limit", strconv.Itoa(min(limit, 100)))
	query.Set("full", "true")
	next := h.Endpoint + "/api/models?" + query.Encode()
	var models []ModelInfo
	for next != "" && len(models) < limit {
		var page []ModelInfo
		link, err := h.get(ctx, next, &page)
		if err != nil {
			return nil, err
		}
		models = append(models, page...)
		next = h.nextLink(link)
		if len(page) == 0 {
			break
		}
	}
	if len(models) > limit {
		models = models[:limit]
	}
	return models, nil
}

// Model returns the whole description of `id` at its current commit
// (card, config, `transformersInfo`, parameters, widget examples).
func (h *Hub) Model(ctx context.Context, id string) (ModelInfo, error) {
	if !repoID.MatchString(id) {
		return ModelInfo{}, fmt.Errorf("invalid model id %q", id)
	}
	var model ModelInfo
	_, err := h.get(ctx, h.Endpoint+"/api/models/"+id, &model)
	return model, err
}

// Tree returns every file of `id` at `commit`, with their hashes.
func (h *Hub) Tree(ctx context.Context, id, commit string) ([]TreeEntry, error) {
	if !repoID.MatchString(id) {
		return nil, fmt.Errorf("invalid model id %q", id)
	}
	if !commitSHA.MatchString(commit) {
		return nil, fmt.Errorf("invalid commit %q", commit)
	}
	next := h.Endpoint + "/api/models/" + id + "/tree/" + commit + "?recursive=true"
	var entries []TreeEntry
	for pages := 0; next != "" && pages < 50; pages++ {
		var page []TreeEntry
		link, err := h.get(ctx, next, &page)
		if err != nil {
			return nil, err
		}
		entries = append(entries, page...)
		next = h.nextLink(link)
	}
	return entries, nil
}

// get decodes the JSON answer of `target` into `into` and returns the
// `Link` header (pagination).
func (h *Hub) get(ctx context.Context, target string, into any) (string, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return "", err
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("User-Agent", "silicium-catalog/1")
	if h.Token != "" {
		request.Header.Set("Authorization", "Bearer "+h.Token)
	}
	client := h.Client
	if client == nil {
		client = http.DefaultClient
	}
	response, err := client.Do(request)
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrHubUnavailable, err)
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusNotFound {
		return "", fmt.Errorf("%w: %s not found", ErrNotOnHub, target)
	}
	if response.StatusCode != http.StatusOK {
		return "", fmt.Errorf("%w: %s answered %d", ErrHubUnavailable, target, response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maxHubResponseBytes+1))
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrHubUnavailable, err)
	}
	if len(body) > maxHubResponseBytes {
		return "", fmt.Errorf("%w: answer of %s too large", ErrHubUnavailable, target)
	}
	if err := json.Unmarshal(body, into); err != nil {
		return "", fmt.Errorf("%w: unreadable answer of %s: %v", ErrHubUnavailable, target, err)
	}
	return response.Header.Get("Link"), nil
}

// ErrNotOnHub: the model or commit no longer exists on the Hub.
var ErrNotOnHub = errors.New("not on the hub")

var nextLinkPattern = regexp.MustCompile(`<([^>]+)>;\s*rel="next"`)

// nextLink is the next page named by a `Link` header, only when it stays on
// the Hub's endpoint.
func (h *Hub) nextLink(header string) string {
	match := nextLinkPattern.FindStringSubmatch(header)
	if match == nil || !strings.HasPrefix(match[1], h.Endpoint+"/") {
		return ""
	}
	return match[1]
}
