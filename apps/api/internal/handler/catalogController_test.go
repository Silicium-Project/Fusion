package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/gorilla/mux"
	"github.com/silicium/internal/catalog"
	"gorm.io/gorm"
)

func catalogRouter(t *testing.T) (*mux.Router, catalog.Store) {
	t.Helper()
	database, err := gorm.Open(sqlite.Open("file:catalog-api?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := catalog.Migrate(database); err != nil {
		t.Fatal(err)
	}
	sqlDB, _ := database.DB()
	sqlDB.SetMaxOpenConns(1)
	t.Cleanup(func() { sqlDB.Close() })

	h := New(database)
	router := mux.NewRouter()
	router.HandleFunc("/catalog/tasks", h.ListCatalogTasks).Methods("GET")
	router.HandleFunc("/catalog/models", h.ListCatalogModels).Methods("GET")
	router.HandleFunc("/catalog/models/{key}", h.GetCatalogModel).Methods("GET")
	return router, catalog.Store{DB: database}
}

func get(t *testing.T, router http.Handler, target string) *httptest.ResponseRecorder {
	t.Helper()
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, target, nil))
	return recorder
}

func TestCatalogAPI(t *testing.T) {
	router, store := catalogRouter(t)
	manifest := `{"format":"silicium-model/1","key":"org--model-0123456789ab","repository":"org/model"}`
	for _, row := range []catalog.Model{
		{Key: "org--model-0123456789ab", Repository: "org/model", Revision: strings.Repeat("a", 40), Task: "image-classification",
			Status: "admitted", Reasons: "[]", Notes: "[]", Manifest: manifest, HardwareClass: "A", Downloads: 10, CheckedAt: time.Now()},
		{Key: "org--other-0123456789ab", Repository: "org/other", Revision: strings.Repeat("b", 40), Task: "image-classification",
			Status: "rejected", Reasons: `["licence.non_commercial"]`, Notes: "[]", HardwareClass: "A", CheckedAt: time.Now()},
	} {
		if err := store.Save(row); err != nil {
			t.Fatal(err)
		}
	}

	response := get(t, router, "/catalog/tasks")
	var tasks struct {
		Tasks []struct {
			ID           string `json:"id"`
			Models       int64  `json:"models"`
			NetworkReady bool   `json:"networkReady"`
		} `json:"tasks"`
		Sync struct {
			SucceededAt *time.Time `json:"succeededAt"`
		} `json:"sync"`
	}
	if err := json.NewDecoder(response.Body).Decode(&tasks); err != nil || response.Code != http.StatusOK {
		t.Fatalf("code %d err %v", response.Code, err)
	}
	if len(tasks.Tasks) != 52 || tasks.Sync.SucceededAt != nil {
		t.Fatalf("tasks %d sync %+v", len(tasks.Tasks), tasks.Sync)
	}
	for _, task := range tasks.Tasks {
		if task.ID == "image-classification" && task.Models != 1 {
			t.Fatalf("models %d", task.Models)
		}
	}

	response = get(t, router, "/catalog/models?task=image-classification")
	if response.Code != http.StatusOK || response.Header().Get("X-Total-Count") != "1" || !strings.Contains(response.Body.String(), `"org/model"`) {
		t.Fatalf("code %d body %s", response.Code, response.Body)
	}
	response = get(t, router, "/catalog/models?status=rejected")
	if !strings.Contains(response.Body.String(), "licence.non_commercial") {
		t.Fatalf("body %s", response.Body)
	}
	for _, target := range []string{"/catalog/models?task=nope", "/catalog/models?status=nope", "/catalog/models?class=Z"} {
		if code := get(t, router, target).Code; code != http.StatusBadRequest {
			t.Fatalf("%s: %d", target, code)
		}
	}

	response = get(t, router, "/catalog/models/org--model-0123456789ab")
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"manifest"`) {
		t.Fatalf("code %d body %s", response.Code, response.Body)
	}
	if code := get(t, router, "/catalog/models/missing").Code; code != http.StatusNotFound {
		t.Fatalf("missing model: %d", code)
	}
}
