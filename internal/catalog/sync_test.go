package catalog

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func testStore(t *testing.T) Store {
	t.Helper()
	database, err := gorm.Open(sqlite.Open("file:"+strings.ReplaceAll(t.Name(), "/", "_")+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := Migrate(database); err != nil {
		t.Fatal(err)
	}
	sqlDB, _ := database.DB()
	sqlDB.SetMaxOpenConns(1)
	t.Cleanup(func() { sqlDB.Close() })
	return Store{DB: database}
}

// fakeHub serves one image classifier; the test changes its commit or its
// files between syncs.
type fakeHub struct {
	mu     sync.Mutex
	info   ModelInfo
	tree   []TreeEntry
	down   bool
	calls  []string
	server *httptest.Server
}

func newFakeHub(t *testing.T) *fakeHub {
	hub := &fakeHub{}
	var info ModelInfo
	_ = json.Unmarshal([]byte(vitInfo), &info)
	hub.info, hub.tree = info, vitTree()
	hub.server = httptest.NewServer(http.HandlerFunc(hub.serve))
	t.Cleanup(hub.server.Close)
	return hub
}

func (h *fakeHub) serve(w http.ResponseWriter, r *http.Request) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.calls = append(h.calls, r.URL.Path)
	if h.down {
		http.Error(w, "down", http.StatusServiceUnavailable)
		return
	}
	switch {
	case r.URL.Path == "/api/tasks":
		_, _ = w.Write([]byte(`{"image-classification": {"libraries": ["timm", "transformers"]}}`))
	case r.URL.Path == "/api/models":
		if r.URL.Query().Get("pipeline_tag") != "image-classification" || r.URL.Query().Get("full") != "true" {
			_, _ = w.Write([]byte(`[]`))
			return
		}
		// A next page on another host must not be followed.
		w.Header().Set("Link", `<https://elsewhere.example/api/models?page=2>; rel="next"`)
		// A listing is partial, as on the Hub: no card, empty config.
		listed := ModelInfo{ID: h.info.ID, SHA: h.info.SHA, PipelineTag: h.info.PipelineTag,
			LibraryName: h.info.LibraryName, Tags: h.info.Tags, Downloads: h.info.Downloads, Config: &ModelConfig{}}
		_ = json.NewEncoder(w).Encode([]ModelInfo{listed})
	case r.URL.Path == "/api/models/"+h.info.ID:
		_ = json.NewEncoder(w).Encode(h.info)
	case r.URL.Path == "/api/models/"+h.info.ID+"/tree/"+h.info.SHA:
		_ = json.NewEncoder(w).Encode(h.tree)
	default:
		http.NotFound(w, r)
	}
}

func (h *fakeHub) syncer(store Store) *Syncer {
	return &Syncer{
		Hub:     NewHub(h.server.URL, ""),
		Store:   store,
		Policy:  DefaultPolicy(),
		PerTask: 5,
		Tasks:   []string{"image-classification"},
	}
}

func TestSyncAdmitsServesAndQuarantines(t *testing.T) {
	store, hub := testStore(t), newFakeHub(t)
	syncer := hub.syncer(store)

	report, err := syncer.Run(context.Background())
	if err != nil || report.New != 1 || report.Admitted != 1 || len(report.Errors) != 0 {
		t.Fatalf("report %+v err %v", report, err)
	}
	rows, total, err := store.List(ListQuery{Task: "image-classification"})
	if err != nil || total != 1 || rows[0].Repository != "google/vit-base-patch16-224" {
		t.Fatalf("rows %+v total %d err %v", rows, total, err)
	}
	key := rows[0].Key
	if libraries := store.HubLibraries()["image-classification"]; strings.Join(libraries, ",") != "timm,transformers" {
		t.Fatalf("libraries %v", libraries)
	}
	if view := rows[0].View(true); view.Manifest == nil || !view.Manifest.Verify() || len(view.Examples) == 0 {
		t.Fatalf("view %+v", view)
	}

	// Second sync, nothing changed: rechecked, still admitted.
	report, err = syncer.Run(context.Background())
	if err != nil || report.New != 0 || report.Rechecked != 1 || report.Quarantined != 0 {
		t.Fatalf("report %+v err %v", report, err)
	}

	// The Hub goes down: the sync fails, the catalogue still answers.
	hub.mu.Lock()
	hub.down = true
	hub.mu.Unlock()
	if _, err := syncer.Run(context.Background()); !errors.Is(err, ErrHubUnavailable) {
		t.Fatalf("err %v", err)
	}
	if _, total, _ := store.List(ListQuery{}); total != 1 {
		t.Fatalf("catalogue lost while the Hub is down: %d", total)
	}
	if state := store.State(); state.LastError == "" || state.SucceededAt.IsZero() {
		t.Fatalf("state %+v", state)
	}

	// The Hub is back but serves another file at the pinned commit.
	hub.mu.Lock()
	hub.down = false
	hub.tree[4] = lfs("model.safetensors", 346_293_852, sha("f"))
	hub.mu.Unlock()
	report, err = syncer.Run(context.Background())
	if err != nil || report.Quarantined != 1 {
		t.Fatalf("report %+v err %v", report, err)
	}
	row, err := store.Get(key)
	if err != nil || row.Status != string(StatusQuarantined) || !strings.Contains(row.Reasons, "hub.pinned_file_changed") {
		t.Fatalf("row %+v err %v", row, err)
	}
	if _, total, _ := store.List(ListQuery{}); total != 0 {
		t.Fatal("a quarantined model must leave the admitted list")
	}
	// A later sync does not lift the quarantine.
	if _, err := syncer.Run(context.Background()); err != nil {
		t.Fatal(err)
	}
	if row, _ := store.Get(key); row.Status != string(StatusQuarantined) {
		t.Fatalf("status %s", row.Status)
	}
	for _, call := range hub.calls {
		if strings.Contains(call, "elsewhere") {
			t.Fatal("followed a link off the Hub")
		}
	}
}

func TestNewCommitSupersedesTheOldOne(t *testing.T) {
	store, hub := testStore(t), newFakeHub(t)
	syncer := hub.syncer(store)
	if _, err := syncer.Run(context.Background()); err != nil {
		t.Fatal(err)
	}
	hub.mu.Lock()
	hub.info.SHA = strings.Repeat("e", 40)
	hub.mu.Unlock()
	report, err := syncer.Run(context.Background())
	if err != nil || report.New != 1 {
		t.Fatalf("report %+v err %v", report, err)
	}
	rows, total, _ := store.List(ListQuery{})
	if total != 1 || rows[0].Revision != strings.Repeat("e", 40) {
		t.Fatalf("rows %+v", rows)
	}
	var all []Model
	store.DB.Find(&all)
	if len(all) != 2 {
		t.Fatalf("%d rows: the old commit must be kept for the jobs naming it", len(all))
	}
	counts, _ := store.AdmittedCounts()
	if counts["image-classification"] != 1 {
		t.Fatalf("counts %v", counts)
	}
}

func TestRefusedModelsAreKeptWithTheirReasons(t *testing.T) {
	store, hub := testStore(t), newFakeHub(t)
	hub.info.CardData.License = Licences{"cc-by-nc-4.0"}
	if _, err := hub.syncer(store).Run(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, total, _ := store.List(ListQuery{}); total != 0 {
		t.Fatal("a rejected model is not admitted")
	}
	rows, total, _ := store.List(ListQuery{Status: "rejected"})
	if total != 1 || !strings.Contains(rows[0].Reasons, "licence.non_commercial") {
		t.Fatalf("rows %+v", rows)
	}
}

func TestHubClientRefusesBadIdentifiers(t *testing.T) {
	hub := NewHub("", "")
	if hub.Endpoint != DefaultHubEndpoint {
		t.Fatal(hub.Endpoint)
	}
	for _, id := range []string{"../etc", "a/b/c", "a b"} {
		if _, err := hub.Tree(context.Background(), id, strings.Repeat("a", 40)); err == nil {
			t.Fatalf("id %q accepted", id)
		}
	}
	if _, err := hub.Tree(context.Background(), "a/b", "main"); err == nil {
		t.Fatal("non-commit revision accepted")
	}
	if got := hub.nextLink(fmt.Sprintf(`<%s/api/models?cursor=x>; rel="next"`, DefaultHubEndpoint)); got == "" {
		t.Fatal("next page on the Hub ignored")
	}
}
