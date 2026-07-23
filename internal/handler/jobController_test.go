package handler

import (
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/silicium/internal/models"
)

func TestBoundedQueryInt(t *testing.T) {
	request := httptest.NewRequest("GET", "/jobs?page=900&page_size=0", nil)
	if page := boundedQueryInt(request, "page", 1, 1, 100); page != 100 {
		t.Fatalf("expected upper bound, got %d", page)
	}
	if pageSize := boundedQueryInt(request, "page_size", 20, 1, 100); pageSize != 1 {
		t.Fatalf("expected lower bound, got %d", pageSize)
	}
	if fallback := boundedQueryInt(request, "missing", 20, 1, 100); fallback != 20 {
		t.Fatalf("expected fallback, got %d", fallback)
	}
}

func TestVerifiedBillingForCancelledJobOnlyCountsCosignedFragments(t *testing.T) {
	progressPath := filepath.Join(t.TempDir(), "raytracer-progress.json")
	payload := `{"fragments":[
		{"compute_billable_work_units":100,"verify_billable_work_units":10,
		 "compute_receipt_hash":"compute-a","verify_receipt_hash":"verify-a",
		 "receipt_attestation":{"accepted":true}},
		{"compute_billable_work_units":999,"verify_billable_work_units":999,
		 "compute_receipt_hash":"forged","receipt_attestation":{"accepted":false}}
	]}`
	if err := os.WriteFile(progressPath, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}
	units, receiptHash := verifiedBillingForJob(models.Job{
		Workload:    "raytracer",
		SummaryPath: filepath.Join(filepath.Dir(progressPath), "summary.json"),
	})
	if units != 110 {
		t.Fatalf("expected 110 verified units, got %d", units)
	}
	if receiptHash == "" {
		t.Fatal("expected a receipt-set hash")
	}
}
