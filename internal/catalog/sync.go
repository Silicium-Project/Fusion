// The sync: reads the Hub, admits the new commits of the most downloaded
// models of each task, and checks again the files of admitted models.
//
// When the Hub is down, the sync stops and the catalogue keeps serving its
// last copy (the API says when it was refreshed). When the Hub contradicts
// an admitted model (a pinned file has another hash at the same commit), the
// model is quarantined: the network no longer runs it until someone looks.

package catalog

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"time"
)

// Syncer refreshes the catalogue from the Hub.
type Syncer struct {
	Hub    *Hub
	Store  Store
	Policy Policy
	// PerTask: models read per task (the most downloaded).
	PerTask int
	// Tasks to read; empty = every task.
	Tasks []string
	// Pace between two calls to the Hub (its rate limit).
	Pace time.Duration
	Now  func() time.Time
}

// Report counts what a sync did.
type Report struct {
	Read        int      `json:"read"`
	New         int      `json:"new"`
	Admitted    int      `json:"admitted"`
	Rechecked   int      `json:"rechecked"`
	Quarantined int      `json:"quarantined"`
	Errors      []string `json:"errors"`
}

// SyncFromEnv returns a syncer configured by the environment, or nil when
// `SILICIUM_CATALOG_SYNC` is not `1`:
//
//   - SILICIUM_HF_ENDPOINT, SILICIUM_HF_TOKEN: the Hub;
//   - SILICIUM_CATALOG_MODELS_PER_TASK (default 20);
//   - SILICIUM_CATALOG_TASKS: comma-separated task ids (default all);
//   - SILICIUM_CATALOG_MAX_MODEL_GB (default 24);
//   - SILICIUM_CATALOG_EXTRA_LICENCES: licences added to the default list.
func SyncFromEnv(store Store) *Syncer {
	if strings.TrimSpace(os.Getenv("SILICIUM_CATALOG_SYNC")) != "1" {
		return nil
	}
	policy := DefaultPolicy()
	if gigabytes, err := strconv.ParseFloat(strings.TrimSpace(os.Getenv("SILICIUM_CATALOG_MAX_MODEL_GB")), 64); err == nil && gigabytes > 0 {
		policy.MaxModelBytes = int64(gigabytes * float64(gib))
	}
	for _, licence := range splitList(os.Getenv("SILICIUM_CATALOG_EXTRA_LICENCES")) {
		policy.Licences[strings.ToLower(licence)] = true
	}
	perTask := 20
	if value, err := strconv.Atoi(strings.TrimSpace(os.Getenv("SILICIUM_CATALOG_MODELS_PER_TASK"))); err == nil && value > 0 {
		perTask = min(value, 500)
	}
	return &Syncer{
		Hub:     NewHub(os.Getenv("SILICIUM_HF_ENDPOINT"), os.Getenv("SILICIUM_HF_TOKEN")),
		Store:   store,
		Policy:  policy,
		PerTask: perTask,
		Tasks:   splitList(os.Getenv("SILICIUM_CATALOG_TASKS")),
		Pace:    300 * time.Millisecond,
	}
}

// SyncInterval is `SILICIUM_CATALOG_SYNC_INTERVAL` (a Go duration, default 24h, at least 10 min).
func SyncInterval() time.Duration {
	interval, err := time.ParseDuration(strings.TrimSpace(os.Getenv("SILICIUM_CATALOG_SYNC_INTERVAL")))
	if err != nil || interval <= 0 {
		return 24 * time.Hour
	}
	return max(interval, 10*time.Minute)
}

func splitList(value string) []string {
	var out []string
	for _, part := range strings.Split(value, ",") {
		if part = strings.TrimSpace(part); part != "" {
			out = append(out, part)
		}
	}
	return out
}

func (s *Syncer) now() time.Time {
	if s.Now != nil {
		return s.Now()
	}
	return time.Now().UTC()
}

func (s *Syncer) pause(ctx context.Context) error {
	if s.Pace <= 0 {
		return ctx.Err()
	}
	timer := time.NewTimer(s.Pace)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

// Loop syncs now, then every `interval`, until `ctx` ends.
func (s *Syncer) Loop(ctx context.Context, interval time.Duration) {
	for {
		report, err := s.Run(ctx)
		if err != nil {
			log.Printf("Catalog sync stopped: %v", err)
		} else {
			log.Printf("Catalog sync: %d read, %d new, %d admitted, %d quarantined, %d errors",
				report.Read, report.New, report.Admitted, report.Quarantined, len(report.Errors))
		}
		timer := time.NewTimer(interval)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
		}
	}
}

// Run syncs once. It returns an error only when the Hub cannot be read at
// all (the catalogue is then unchanged); the failures of single tasks or
// models are in the report.
func (s *Syncer) Run(ctx context.Context) (Report, error) {
	report := Report{Errors: []string{}}
	state := s.Store.State()
	state.StartedAt = s.now()

	libraries, err := s.Hub.Tasks(ctx)
	if err != nil {
		state.FinishedAt = s.now()
		state.LastError = err.Error()
		_ = s.Store.SaveState(state)
		return report, err
	}
	state.Tasks = encode(libraries)

	taskIDs := s.Tasks
	if len(taskIDs) == 0 {
		for _, task := range tasks {
			taskIDs = append(taskIDs, task.ID)
		}
	}
	for _, taskID := range taskIDs {
		if ctx.Err() != nil {
			break
		}
		if _, ok := FindTask(taskID); !ok {
			report.Errors = append(report.Errors, fmt.Sprintf("%s: unknown task", taskID))
			continue
		}
		if err := s.pause(ctx); err != nil {
			break
		}
		models, err := s.Hub.ListModels(ctx, taskID, s.PerTask)
		if err != nil {
			report.Errors = append(report.Errors, fmt.Sprintf("%s: %v", taskID, err))
			continue
		}
		for _, info := range models {
			if ctx.Err() != nil {
				break
			}
			report.Read++
			if err := s.syncModel(ctx, info, &report); err != nil {
				report.Errors = append(report.Errors, fmt.Sprintf("%s: %v", info.ID, err))
			}
		}
	}

	state.FinishedAt = s.now()
	state.Models = report.Read
	if len(report.Errors) == 0 && ctx.Err() == nil {
		state.SucceededAt = state.FinishedAt
		state.LastError = ""
	} else if len(report.Errors) > 0 {
		state.LastError = strings.Join(report.Errors[:min(len(report.Errors), 20)], "\n")
	} else {
		state.LastError = ctx.Err().Error()
	}
	if err := s.Store.SaveState(state); err != nil {
		return report, err
	}
	return report, nil
}

// syncModel handles one model of a listing (`listed`: commit and counts
// only). A commit already in the catalogue is rechecked when admitted; a
// new one is described in full, then admitted or refused.
func (s *Syncer) syncModel(ctx context.Context, listed ModelInfo, report *Report) error {
	if !repoID.MatchString(listed.ID) {
		return fmt.Errorf("invalid model id")
	}
	if commitSHA.MatchString(listed.SHA) {
		if row, known := s.Store.Known(listed.ID, listed.SHA); known {
			if err := s.Store.DB.Model(&Model{}).Where("key = ?", row.Key).
				Updates(map[string]any{"downloads": listed.Downloads, "likes": listed.Likes}).Error; err != nil {
				return err
			}
			if row.Status == string(StatusAdmitted) {
				return s.recheck(ctx, row, report)
			}
			return nil
		}
	}

	if err := s.pause(ctx); err != nil {
		return err
	}
	info, err := s.Hub.Model(ctx, listed.ID)
	if err != nil {
		return err
	}
	if info.ID != listed.ID {
		return fmt.Errorf("the Hub described %q instead", info.ID)
	}
	if !commitSHA.MatchString(info.SHA) {
		return s.Store.Save(rowFor(info, Admit(info, nil, s.Policy), s.now()))
	}
	if _, known := s.Store.Known(info.ID, info.SHA); known {
		// The listing was older than the description; next sync rechecks.
		return nil
	}
	if err := s.pause(ctx); err != nil {
		return err
	}
	tree, err := s.Hub.Tree(ctx, info.ID, info.SHA)
	if err != nil {
		return err
	}
	decision := Admit(info, tree, s.Policy)
	row := rowFor(info, decision, s.now())
	if err := s.Store.Save(row); err != nil {
		return err
	}
	report.New++
	if decision.Status == StatusAdmitted {
		report.Admitted++
	}
	return s.Store.MarkSuperseded(info.ID, info.SHA)
}

// recheck reads the tree of an admitted model at its pinned commit again:
// a pinned file with another hash or size quarantines the model. A commit
// the Hub no longer has does not: the nodes holding the files still serve
// them, hash checked.
func (s *Syncer) recheck(ctx context.Context, row Model, report *Report) error {
	manifest, err := row.ParsedManifest()
	if err != nil {
		return err
	}
	if err := s.pause(ctx); err != nil {
		return err
	}
	tree, err := s.Hub.Tree(ctx, manifest.Repository, manifest.Revision)
	if errors.Is(err, ErrNotOnHub) {
		return s.Store.DB.Model(&Model{}).Where("key = ?", row.Key).
			Updates(map[string]any{"notes": encode(append(decodeCodes(row.Notes), "hub.revision_gone")), "checked_at": s.now()}).Error
	}
	if err != nil {
		return err
	}
	report.Rechecked++
	if reason := contradiction(*manifest, tree); reason != "" {
		report.Quarantined++
		log.Printf("Catalog: model %s quarantined (%s)", row.Key, reason)
		return s.Store.Quarantine(row.Key, reason)
	}
	return s.Store.DB.Model(&Model{}).Where("key = ?", row.Key).Update("checked_at", s.now()).Error
}

// contradiction returns why `tree` contradicts the pinned files, or "".
func contradiction(manifest Manifest, tree []TreeEntry) string {
	byPath := make(map[string]TreeEntry, len(tree))
	for _, entry := range tree {
		byPath[entry.Path] = entry
	}
	for _, file := range manifest.Files {
		entry, ok := byPath[file.Path]
		if !ok {
			return "hub.pinned_file_missing"
		}
		switch {
		case file.SHA256 != "":
			if entry.LFS == nil || entry.LFS.OID != file.SHA256 || (entry.LFS.Size > 0 && entry.LFS.Size != file.Size) {
				return "hub.pinned_file_changed"
			}
		case file.GitOID != "":
			if entry.OID != file.GitOID {
				return "hub.pinned_file_changed"
			}
		}
	}
	return ""
}
