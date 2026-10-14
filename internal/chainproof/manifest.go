// Package chainproof anchors the trace of a finished job on Solana.
//
// The Rust orchestrator records every step of a task as an Ed25519-signed
// task-book event and copies, for each task, who computed it, who verified
// it and the hashes of those events into the job summary. This package turns
// that list into one Merkle tree (one leaf per task), writes the root, the
// job's final result hash and the task count in a single Memo transaction on
// Solana, and keeps next to the summary a `devnet-trace.json` file holding
// every leaf and its Merkle proof.
//
// A user can then open the transaction in a Solana explorer, read the root in
// the memo, and check that any task of the job hashes up to that root: the
// chain proves the trace existed at that time and was not changed afterwards.
// One transaction per job keeps the cost at one network fee whatever the
// number of tasks.
package chainproof

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
)

// ManifestSchema names the leaf format; it is written in the memo, so a
// change of leaf encoding must change it.
const ManifestSchema = "silicium.job-proof.v1"

// Verifier is one verifier of a task, as recorded by the task book.
type Verifier struct {
	Author            string `json:"author"`
	Verdict           *bool  `json:"verdict"`
	VerificationEvent string `json:"verification_event"`
	SelfVerification  bool   `json:"self_verification"`
}

// Task is one Merkle leaf: the signed task-book trace of one task.
//
// The field order is the canonical encoding (Go marshals struct fields in
// declaration order); do not reorder without changing ManifestSchema.
type Task struct {
	TaskID        string     `json:"task_id"`
	FragmentIndex int        `json:"fragment_index"`
	Status        string     `json:"status"`
	ResultSHA256  string     `json:"result_sha256"`
	Publisher     string     `json:"publisher"`
	ProposalEvent string     `json:"proposal_event"`
	SpecSHA256    string     `json:"spec_sha256"`
	Attempt       int        `json:"attempt"`
	Worker        string     `json:"worker"`
	ClaimEvent    string     `json:"claim_event"`
	ResultEvent   string     `json:"result_event"`
	Verifiers     []Verifier `json:"verifiers"`
}

// Manifest is everything one job anchors.
type Manifest struct {
	Schema         string `json:"schema"`
	JobID          string `json:"job_id"`
	Workload       string `json:"workload"`
	FinalSHA256    string `json:"final_sha256"`
	ReceiptSetHash string `json:"receipt_set_hash"`
	Tasks          []Task `json:"tasks"`
}

// ErrNoTasks means the summary lists no completed task to anchor.
var ErrNoTasks = errors.New("chainproof: the job summary has no completed task")

// ManifestFromSummary reads the tasks of a Rust-node job summary
// (`raytracer-summary.json`). Only completed tasks are anchored; they are
// sorted by fragment index so the tree does not depend on file order.
func ManifestFromSummary(summary map[string]any, finalSHA256 string) (Manifest, error) {
	manifest := Manifest{
		Schema:      ManifestSchema,
		JobID:       stringField(summary, "job_id"),
		Workload:    stringField(summary, "workload"),
		FinalSHA256: strings.ToLower(strings.TrimPrefix(finalSHA256, "sha256:")),
	}
	if billing, ok := summary["billing"].(map[string]any); ok {
		manifest.ReceiptSetHash = stringField(billing, "receipt_set_hash")
	}
	if manifest.JobID == "" {
		return Manifest{}, errors.New("chainproof: the job summary has no job_id")
	}
	fragments, _ := summary["fragments"].([]any)
	for _, raw := range fragments {
		fragment, ok := raw.(map[string]any)
		if !ok || stringField(fragment, "status") != "completed" {
			continue
		}
		manifest.Tasks = append(manifest.Tasks, taskFromFragment(fragment))
	}
	if len(manifest.Tasks) == 0 {
		return Manifest{}, ErrNoTasks
	}
	sort.SliceStable(manifest.Tasks, func(i, j int) bool {
		return manifest.Tasks[i].FragmentIndex < manifest.Tasks[j].FragmentIndex
	})
	return manifest, nil
}

// taskFromFragment maps one summary fragment row (and its `trace` block
// written by the Rust node) to a leaf.
func taskFromFragment(fragment map[string]any) Task {
	trace, _ := fragment["trace"].(map[string]any)
	task := Task{
		TaskID:        stringField(fragment, "task_id"),
		FragmentIndex: intField(fragment, "fragment_index"),
		Status:        stringField(fragment, "status"),
		ResultSHA256:  firstNonEmpty(stringField(trace, "result_sha256"), stringField(fragment, "result_hash")),
		Publisher:     stringField(trace, "publisher"),
		ProposalEvent: stringField(trace, "proposal_event"),
		SpecSHA256:    stringField(trace, "spec_sha256"),
		Attempt:       intField(trace, "attempt"),
		Worker:        firstNonEmpty(stringField(trace, "worker"), stringField(fragment, "worker")),
		ClaimEvent:    stringField(trace, "claim_event"),
		ResultEvent:   stringField(trace, "result_event"),
		Verifiers:     []Verifier{},
	}
	verifiers, _ := trace["verifiers"].([]any)
	for _, raw := range verifiers {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		verifier := Verifier{
			Author:            stringField(item, "author"),
			VerificationEvent: stringField(item, "verification_event"),
		}
		if verdict, ok := item["verdict"].(bool); ok {
			verifier.Verdict = &verdict
		}
		verifier.SelfVerification, _ = item["self_verification"].(bool)
		task.Verifiers = append(task.Verifiers, verifier)
	}
	return task
}

// LeafHash is the hex SHA-256 of 0x00 followed by the task's canonical JSON.
// The 0x00 / 0x01 prefixes keep a leaf from ever being taken for an inner
// node (RFC 6962 domain separation).
func LeafHash(task Task) (string, error) {
	encoded, err := json.Marshal(task)
	if err != nil {
		return "", fmt.Errorf("chainproof: encode task %s: %w", task.TaskID, err)
	}
	digest := sha256.Sum256(append([]byte{0x00}, encoded...))
	return hex.EncodeToString(digest[:]), nil
}

func stringField(values map[string]any, key string) string {
	if values == nil {
		return ""
	}
	value, _ := values[key].(string)
	return strings.TrimSpace(value)
}

func intField(values map[string]any, key string) int {
	if values == nil {
		return 0
	}
	value, _ := values[key].(float64)
	return int(value)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
