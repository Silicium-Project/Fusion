// The AI catalogue ("Catalogue IA"): the tasks of the Hugging Face Hub and
// the models admitted for each one. Read only and public: the catalogue
// holds no user data.

package handler

import (
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/catalog"
	"gorm.io/gorm"
)

// catalogTask is a task as the catalogue API returns it.
type catalogTask struct {
	catalog.Task
	// Models admitted for the task.
	Models int64 `json:"models"`
	// NetworkReady: the network runs the task now (false until the workers
	// have the AI runtime).
	NetworkReady bool `json:"networkReady"`
}

type catalogSync struct {
	SucceededAt *time.Time `json:"succeededAt"`
	FinishedAt  *time.Time `json:"finishedAt"`
	// Failed: the last sync could not read the Hub entirely; the catalogue
	// is the last copy.
	Failed bool `json:"failed"`
}

func (h *Handler) catalogStore() catalog.Store {
	return catalog.Store{DB: h.DB}
}

func timePointer(t time.Time) *time.Time {
	if t.IsZero() {
		return nil
	}
	return &t
}

// ListCatalogTasks answers GET /catalog/tasks.
func (h *Handler) ListCatalogTasks(w http.ResponseWriter, r *http.Request) {
	store := h.catalogStore()
	counts, err := store.AdmittedCounts()
	if err != nil {
		http.Error(w, "Catalog unavailable", http.StatusInternalServerError)
		return
	}
	tasks := catalog.WithHubLibraries(store.HubLibraries())
	out := make([]catalogTask, 0, len(tasks))
	for _, task := range tasks {
		out = append(out, catalogTask{Task: task, Models: counts[task.ID], NetworkReady: catalog.NetworkReady(task.ID)})
	}
	state := store.State()
	w.Header().Set("Cache-Control", "public, max-age=60")
	writeJSON(w, http.StatusOK, map[string]any{
		"tasks": out,
		"sync": catalogSync{
			SucceededAt: timePointer(state.SucceededAt),
			FinishedAt:  timePointer(state.FinishedAt),
			Failed:      state.LastError != "",
		},
	})
}

var catalogStatuses = map[string]bool{
	"": true, "all": true, "admitted": true, "review": true,
	"unsupported": true, "rejected": true, "quarantined": true,
}

// ListCatalogModels answers GET /catalog/models?task=&status=&q=&class=&limit=&offset=.
func (h *Handler) ListCatalogModels(w http.ResponseWriter, r *http.Request) {
	values := r.URL.Query()
	query := catalog.ListQuery{
		Task:   strings.TrimSpace(values.Get("task")),
		Status: strings.TrimSpace(values.Get("status")),
		Search: strings.TrimSpace(values.Get("q")),
		Class:  strings.ToUpper(strings.TrimSpace(values.Get("class"))),
	}
	if query.Task != "" {
		if _, ok := catalog.FindTask(query.Task); !ok {
			http.Error(w, "Unknown task", http.StatusBadRequest)
			return
		}
	}
	if !catalogStatuses[query.Status] {
		http.Error(w, "Unknown status", http.StatusBadRequest)
		return
	}
	if query.Class != "" && query.Class != "A" && query.Class != "B" && query.Class != "C" {
		http.Error(w, "Unknown hardware class", http.StatusBadRequest)
		return
	}
	if len(query.Search) > 100 {
		query.Search = query.Search[:100]
	}
	query.Limit, _ = strconv.Atoi(values.Get("limit"))
	query.Offset, _ = strconv.Atoi(values.Get("offset"))

	rows, total, err := h.catalogStore().List(query)
	if err != nil {
		http.Error(w, "Catalog unavailable", http.StatusInternalServerError)
		return
	}
	models := make([]catalog.ModelView, 0, len(rows))
	for _, row := range rows {
		models = append(models, row.View(false))
	}
	w.Header().Set("X-Total-Count", strconv.FormatInt(total, 10))
	writeJSON(w, http.StatusOK, map[string]any{"models": models, "total": total})
}

// GetCatalogModel answers GET /catalog/models/{key}: the model with its
// manifest and its examples.
func (h *Handler) GetCatalogModel(w http.ResponseWriter, r *http.Request) {
	key := mux.Vars(r)["key"]
	if key == "" || len(key) > 120 {
		http.Error(w, "Model not found", http.StatusNotFound)
		return
	}
	row, err := h.catalogStore().Get(key)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		http.Error(w, "Model not found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, "Catalog unavailable", http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, row.View(true))
}
