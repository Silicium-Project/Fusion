// The catalogue in the database: one row per pinned model (repository at
// one commit), and one row with the state of the last sync.

package catalog

import (
	"encoding/json"
	"errors"
	"strings"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// Model is a model of the catalogue: a repository at one commit, with the
// admission decision and the manifest.
type Model struct {
	Key           string `gorm:"primaryKey;size:120"`
	Repository    string `gorm:"index;size:200"`
	Revision      string `gorm:"size:40"`
	Task          string `gorm:"index;size:64"`
	Library       string `gorm:"size:64"`
	Runtime       string `gorm:"size:16"`
	Status        string `gorm:"index;size:16"`
	Reasons       string `gorm:"type:text"` // JSON array of codes.
	Notes         string `gorm:"type:text"` // JSON array of codes.
	Manifest      string `gorm:"type:text"` // JSON manifest.
	HardwareClass string `gorm:"size:1"`
	TotalBytes    int64
	Parameters    int64
	Licence       string `gorm:"size:80"`
	Downloads     int64  `gorm:"index"`
	Likes         int64
	// Examples are the Hub's widget examples (JSON), the inputs of the
	// admission test and of the canary tasks.
	Examples string `gorm:"type:text"`
	// Superseded: the Hub has a newer commit of the repository in the
	// catalogue (kept: jobs may still name this one).
	Superseded bool
	CheckedAt  time.Time
	CreatedAt  time.Time
	UpdatedAt  time.Time
}

// TableName keeps the catalogue tables together.
func (Model) TableName() string { return "catalog_models" }

// SyncState is the single row recording the last sync.
type SyncState struct {
	ID uint `gorm:"primaryKey"`
	// Tasks are the libraries by task last read from the Hub (JSON).
	Tasks       string `gorm:"type:text"`
	StartedAt   time.Time
	FinishedAt  time.Time
	SucceededAt time.Time
	LastError   string `gorm:"type:text"`
	Models      int
	UpdatedAt   time.Time
}

func (SyncState) TableName() string { return "catalog_sync" }

// Migrate creates or updates the catalogue tables.
func Migrate(db *gorm.DB) error {
	return db.AutoMigrate(&Model{}, &SyncState{})
}

// Store reads and writes the catalogue.
type Store struct {
	DB *gorm.DB
}

// ModelView is a model as the API returns it.
type ModelView struct {
	Key           string          `json:"key"`
	Repository    string          `json:"repository"`
	Revision      string          `json:"revision"`
	Task          string          `json:"task"`
	Library       string          `json:"library"`
	Runtime       string          `json:"runtime"`
	Status        string          `json:"status"`
	Reasons       []string        `json:"reasons"`
	Notes         []string        `json:"notes"`
	HardwareClass string          `json:"hardwareClass"`
	TotalBytes    int64           `json:"totalBytes"`
	Parameters    int64           `json:"parameters"`
	Licence       string          `json:"licence"`
	Downloads     int64           `json:"downloads"`
	Likes         int64           `json:"likes"`
	Superseded    bool            `json:"superseded"`
	CheckedAt     time.Time       `json:"checkedAt"`
	HubURL        string          `json:"hubUrl"`
	Manifest      *Manifest       `json:"manifest,omitempty"`
	Examples      json.RawMessage `json:"examples,omitempty"`
}

// View converts a row; `full` adds the manifest and the examples.
func (m Model) View(full bool) ModelView {
	view := ModelView{
		Key: m.Key, Repository: m.Repository, Revision: m.Revision, Task: m.Task,
		Library: m.Library, Runtime: m.Runtime, Status: m.Status,
		Reasons: decodeCodes(m.Reasons), Notes: decodeCodes(m.Notes),
		HardwareClass: m.HardwareClass, TotalBytes: m.TotalBytes, Parameters: m.Parameters,
		Licence: m.Licence, Downloads: m.Downloads, Likes: m.Likes, Superseded: m.Superseded,
		CheckedAt: m.CheckedAt, HubURL: DefaultHubEndpoint + "/" + m.Repository,
	}
	if full {
		if manifest, err := m.ParsedManifest(); err == nil {
			view.Manifest = manifest
		}
		if strings.TrimSpace(m.Examples) != "" {
			view.Examples = json.RawMessage(m.Examples)
		}
	}
	return view
}

// ParsedManifest decodes the stored manifest.
func (m Model) ParsedManifest() (*Manifest, error) {
	if strings.TrimSpace(m.Manifest) == "" {
		return nil, errors.New("no manifest")
	}
	var manifest Manifest
	if err := json.Unmarshal([]byte(m.Manifest), &manifest); err != nil {
		return nil, err
	}
	return &manifest, nil
}

func decodeCodes(raw string) []string {
	codes := []string{}
	if strings.TrimSpace(raw) != "" {
		_ = json.Unmarshal([]byte(raw), &codes)
	}
	return codes
}

func encode(value any) string {
	encoded, _ := json.Marshal(value)
	return string(encoded)
}

// rowFor builds the row of a decision about `info`.
func rowFor(info ModelInfo, decision Decision, now time.Time) Model {
	row := Model{
		Repository: info.ID, Revision: info.SHA, Task: info.PipelineTag,
		Status: string(decision.Status), Reasons: encode(decision.Reasons), Notes: encode(decision.Notes),
		Downloads: info.Downloads, Likes: info.Likes, CheckedAt: now,
	}
	if len(info.WidgetData) > 0 {
		row.Examples = encode(info.WidgetData)
	}
	if manifest := decision.Manifest; manifest != nil {
		row.Key = manifest.Key
		row.Library = manifest.Library
		row.Runtime = string(manifest.Runtime)
		row.Manifest = encode(manifest)
		row.HardwareClass = string(manifest.HardwareClass)
		row.TotalBytes = manifest.TotalBytes
		row.Parameters = manifest.Parameters
		row.Licence = manifest.Licence
	} else {
		// No file selection: the key still names the repository and commit.
		row.Key = slug(info.ID) + "-" + shortRevision(info.SHA)
		row.Library = info.LibraryName
	}
	return row
}

func shortRevision(revision string) string {
	if len(revision) >= 12 {
		return revision[:12]
	}
	if revision == "" {
		return "unknown"
	}
	return revision
}

// Save inserts or updates a row. A quarantined row keeps its status.
func (s Store) Save(row Model) error {
	var existing Model
	found := s.DB.Where("key = ?", row.Key).Limit(1).Find(&existing)
	if found.Error == nil && found.RowsAffected == 1 && existing.Status == string(StatusQuarantined) {
		row.Status = existing.Status
		row.Reasons = existing.Reasons
	}
	return s.DB.Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "key"}},
		DoUpdates: clause.AssignmentColumns([]string{
			"status", "reasons", "notes", "manifest", "hardware_class", "total_bytes",
			"parameters", "licence", "downloads", "likes", "examples", "library", "runtime",
			"superseded", "checked_at", "updated_at",
		}),
	}).Create(&row).Error
}

// Known reports whether the repository at this commit is already stored,
// and returns its row.
func (s Store) Known(repository, revision string) (Model, bool) {
	var row Model
	// Find, not First: a model not stored yet is the usual case during a
	// sync, and First would log it as an error.
	found := s.DB.Where("repository = ? AND revision = ?", repository, revision).Order("checked_at desc").Limit(1).Find(&row)
	return row, found.Error == nil && found.RowsAffected == 1
}

// MarkSuperseded flags the other commits of `repository`.
func (s Store) MarkSuperseded(repository, current string) error {
	return s.DB.Model(&Model{}).
		Where("repository = ? AND revision <> ?", repository, current).
		Update("superseded", true).Error
}

// Quarantine sets a model aside with a reason.
func (s Store) Quarantine(key, reason string) error {
	return s.DB.Model(&Model{}).Where("key = ?", key).Updates(map[string]any{
		"status":  string(StatusQuarantined),
		"reasons": encode([]string{reason}),
	}).Error
}

// ListQuery filters the models.
type ListQuery struct {
	Task   string
	Status string // "" = admitted; "all" = every status.
	Search string
	Class  string
	Limit  int
	Offset int
}

// List returns the models of a query and their total count. Superseded
// commits are left out.
func (s Store) List(query ListQuery) ([]Model, int64, error) {
	db := s.DB.Model(&Model{}).Where("superseded = ?", false)
	if query.Task != "" {
		db = db.Where("task = ?", query.Task)
	}
	switch query.Status {
	case "":
		db = db.Where("status = ?", string(StatusAdmitted))
	case "all":
	default:
		db = db.Where("status = ?", query.Status)
	}
	if query.Search != "" {
		db = db.Where("LOWER(repository) LIKE ?", "%"+strings.ToLower(query.Search)+"%")
	}
	if query.Class != "" {
		db = db.Where("hardware_class = ?", query.Class)
	}
	var total int64
	if err := db.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	limit := query.Limit
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	var rows []Model
	err := db.Order("downloads desc, key asc").Limit(limit).Offset(max(query.Offset, 0)).Find(&rows).Error
	return rows, total, err
}

// Get returns the model `key`.
func (s Store) Get(key string) (Model, error) {
	var row Model
	err := s.DB.Where("key = ?", key).First(&row).Error
	return row, err
}

// AdmittedCounts counts admitted, current models by task.
func (s Store) AdmittedCounts() (map[string]int64, error) {
	var counts []struct {
		Task  string
		Count int64
	}
	err := s.DB.Model(&Model{}).Select("task, COUNT(*) AS count").
		Where("status = ? AND superseded = ?", string(StatusAdmitted), false).
		Group("task").Scan(&counts).Error
	out := make(map[string]int64, len(counts))
	for _, c := range counts {
		out[c.Task] = c.Count
	}
	return out, err
}

// State returns the sync state (zero when never synced).
func (s Store) State() SyncState {
	var state SyncState
	_ = s.DB.Where("id = ?", 1).Limit(1).Find(&state).Error
	return state
}

// SaveState writes the sync state.
func (s Store) SaveState(state SyncState) error {
	state.ID = 1
	return s.DB.Save(&state).Error
}

// HubLibraries returns the libraries by task of the last sync.
func (s Store) HubLibraries() map[string][]string {
	state := s.State()
	libraries := map[string][]string{}
	if strings.TrimSpace(state.Tasks) != "" {
		_ = json.Unmarshal([]byte(state.Tasks), &libraries)
	}
	return libraries
}
