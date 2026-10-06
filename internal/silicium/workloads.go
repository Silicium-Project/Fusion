package silicium

// Workloads the Rust node can run, and where it writes their results.
//
// The node projects each job into `<workload storage>/<StorageDir>/<job id>/`
// (progress, summary, result). To accept a new workload, add it here once the
// node supports it (crates/p2p-node/src/workload/ in Network).

import (
	"errors"
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
}

var raytracerSpec = workloadSpec{
	NodeID:     "raytracer",
	StorageDir: "raytracer",
	ResultFile: "reassembled/render.ppm",
}

var sha256Spec = workloadSpec{
	NodeID:     "calcul/integrity/sha256",
	StorageDir: "sha256",
	ResultFile: "result/sha256.json",
}

// workloadSpecs lists the accepted workload names, aliases included.
var workloadSpecs = map[string]workloadSpec{
	"":                        raytracerSpec,
	"raytracer":               raytracerSpec,
	"calcul/integrity/sha256": sha256Spec,
	"calcul/hash/sha256":      sha256Spec,
}

// workloadSpecFor returns the spec of a workload name.
func workloadSpecFor(workload string) (workloadSpec, bool) {
	spec, ok := workloadSpecs[strings.TrimSpace(workload)]
	return spec, ok
}

// ValidateWorkload refuses a workload the Rust node cannot run.
func ValidateWorkload(workload string) error {
	if _, ok := workloadSpecFor(workload); ok {
		return nil
	}
	return errors.New("unsupported workload")
}

// JobStorageDir returns the directory, under the workload storage root, where
// the Rust node projects the jobs of `workload` (progress, summary, result).
func JobStorageDir(workload string) (string, bool) {
	spec, ok := workloadSpecFor(workload)
	return spec.StorageDir, ok
}
