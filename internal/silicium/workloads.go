package silicium

// Workloads the Rust node can run, and where it writes their results.
//
// The node projects each job into `<workload storage>/<StorageDir>/<job id>/`
// (progress, summary, result). To accept a new workload, add it here once the
// node supports it (crates/p2p-node/src/workload/ in Network).

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)

// workloadSpec describes one workload for the runner.
type workloadSpec struct {
	// NodeID is the identifier sent to the node in the submission.
	NodeID string
	// StorageDir is the directory of its jobs under the workload storage root.
	StorageDir string
	// ResultFile is the job result, relative to the job directory.
	ResultFile string
	// ViewableFile, when set, is a copy of the result in a format browsers
	// display (the PNG of a render), written by the node with ResultFile.
	ViewableFile string
}

var raytracerSpec = workloadSpec{
	NodeID:       "raytracer",
	StorageDir:   "raytracer",
	ResultFile:   "reassembled/render.ppm",
	ViewableFile: "reassembled/render.png",
}

var sha256Spec = workloadSpec{
	NodeID:     "calcul/integrity/sha256",
	StorageDir: "sha256",
	ResultFile: "result/sha256.json",
}

// DocumentSearchWorkload is the workload of "Recherche dans mes documents":
// the node turns the submitted documents into passages, the network embeds
// them with a pinned model, and the site searches them by meaning.
const DocumentSearchWorkload = "ai/embedding/multilingual-e5-small"

var documentSearchSpec = workloadSpec{
	NodeID:     DocumentSearchWorkload,
	StorageDir: "embedding",
	ResultFile: "index/index.json",
}

// BatchAIWorkload is the workload of "Traitement par IA": the network
// applies one instruction to every item of a list with a pinned language
// model run by Ollama on the workers.
const BatchAIWorkload = "ai/llm/qwen2.5-1.5b-instruct"

var batchAISpec = workloadSpec{
	NodeID:     BatchAIWorkload,
	StorageDir: "llm",
	ResultFile: "answers/result.json",
}

// workloadSpecs lists the accepted workload names, aliases included.
var workloadSpecs = map[string]workloadSpec{
	"":                        raytracerSpec,
	"raytracer":               raytracerSpec,
	"calcul/integrity/sha256": sha256Spec,
	"calcul/hash/sha256":      sha256Spec,
	DocumentSearchWorkload:    documentSearchSpec,
	BatchAIWorkload:           batchAISpec,
}

// IsDocumentSearch reports whether `workload` is a document search.
func IsDocumentSearch(workload string) bool {
	spec, ok := workloadSpecFor(workload)
	return ok && spec.NodeID == DocumentSearchWorkload
}

// IsBatchAI reports whether `workload` is a batch AI job.
func IsBatchAI(workload string) bool {
	spec, ok := workloadSpecFor(workload)
	return ok && spec.NodeID == BatchAIWorkload
}

// HFPrefix starts the workloads of the AI catalogue: `ai/hf/<task>/<model
// key>`, one per model (Network, `workload/hf`).
const HFPrefix = "ai/hf/"

// IsHF reports whether `workload` is a job of the AI catalogue.
func IsHF(workload string) bool {
	_, _, ok := ParseHF(workload)
	return ok
}

// IsSHA256 reports whether a workload is the deterministic chunk-hash job
// supported by the Devnet escrow pilot.
func IsSHA256(workload string) bool {
	spec, ok := workloadSpecFor(workload)
	return ok && spec.NodeID == sha256Spec.NodeID
}

// ParseHF splits `ai/hf/<task>/<key>`; the task and the key are checked
// against the catalogue by the caller.
func ParseHF(workload string) (task, key string, ok bool) {
	rest, found := strings.CutPrefix(strings.TrimSpace(workload), HFPrefix)
	if !found {
		return "", "", false
	}
	task, key, found = strings.Cut(rest, "/")
	if !found || task == "" || len(key) < 14 || len(key) > 120 || strings.ContainsAny(key, "/\\") {
		return "", "", false
	}
	for _, c := range task + key {
		if !(c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == '-' || c == '.' || c == '_') {
			return "", "", false
		}
	}
	return task, key, true
}

// workloadSpecFor returns the spec of a workload name.
func workloadSpecFor(workload string) (workloadSpec, bool) {
	workload = strings.TrimSpace(workload)
	if IsHF(workload) {
		return workloadSpec{NodeID: workload, StorageDir: "hf", ResultFile: "answers/result.json"}, true
	}
	spec, ok := workloadSpecs[workload]
	return spec, ok
}

// ValidateWorkload refuses a workload the Rust node cannot run.
func ValidateWorkload(workload string) error {
	if _, ok := workloadSpecFor(workload); ok {
		return nil
	}
	return errors.New("unsupported workload")
}

// ViewableResultPath returns the browser-viewable copy of the result at
// `resultPath` (the PNG next to a render's PPM) when the node wrote one, else
// `resultPath` itself. Jobs saved with the PPM as their result keep working.
func ViewableResultPath(workload, resultPath string) string {
	spec, ok := workloadSpecFor(workload)
	if !ok || spec.ViewableFile == "" || resultPath == "" {
		return resultPath
	}
	suffix := filepath.FromSlash(spec.ResultFile)
	if !strings.HasSuffix(filepath.Clean(resultPath), suffix) {
		return resultPath
	}
	jobDir := strings.TrimSuffix(filepath.Clean(resultPath), suffix)
	viewable := filepath.Join(jobDir, filepath.FromSlash(spec.ViewableFile))
	if info, err := os.Stat(viewable); err == nil && info.Mode().IsRegular() {
		return viewable
	}
	return resultPath
}

// JobStorageDir returns the directory, under the workload storage root, where
// the Rust node projects the jobs of `workload` (progress, summary, result).
func JobStorageDir(workload string) (string, bool) {
	spec, ok := workloadSpecFor(workload)
	return spec.StorageDir, ok
}
