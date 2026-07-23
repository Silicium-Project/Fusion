package silicium

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"testing"

	"github.com/silicium/internal/models"
)

func TestParseRaytracerSummaryFallsBackToPPMWhenPNGIsUnavailable(t *testing.T) {
	dir := t.TempDir()
	summaryPath := filepath.Join(dir, "raytracer-summary.json")
	payload := `{
		"success": true,
		"reassembled_png": "",
		"result_png_path": "",
		"result_path": "",
		"reassembled_ppm": "/tmp/render.ppm"
	}`
	if err := os.WriteFile(summaryPath, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}

	result := parseRaytracerSummary(summaryPath)

	if result.Status != "completed" {
		t.Fatalf("expected completed status, got %q", result.Status)
	}
	if result.ResultPath != "/tmp/render.ppm" {
		t.Fatalf("expected PPM fallback, got %q", result.ResultPath)
	}
}

func TestRaytracerArgsForwardRequestedFragmentCount(t *testing.T) {
	args := raytracerArgs(
		models.Job{InputPath: "/tmp/scene.cfg", SiliciumJobID: "render-1", FragmentCount: 73},
		RunnerConfig{},
	)

	index := slices.Index(args, "--fragments")
	if index < 0 || index+1 >= len(args) || args[index+1] != "73" {
		t.Fatalf("expected --fragments 73, got %#v", args)
	}
}

func TestParseRaytracerSummaryReadsVerifiedBillingOnly(t *testing.T) {
	dir := t.TempDir()
	summaryPath := filepath.Join(dir, "raytracer-summary.json")
	payload := `{
		"success": true,
		"billing": {
			"schema": "silicium.verified-billing.v1",
			"billable_work_units": 12345,
			"receipt_set_hash": "receipt-set"
		}
	}`
	if err := os.WriteFile(summaryPath, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}

	result := parseRaytracerSummary(summaryPath)

	if result.BillableWorkUnits != 12345 {
		t.Fatalf("expected verified units, got %d", result.BillableWorkUnits)
	}
	if result.ComputeReceiptHash != "receipt-set" {
		t.Fatalf("expected receipt set hash, got %q", result.ComputeReceiptHash)
	}
}

func TestPublishTaskControlUsesSignedOrchestratorIdentity(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	privateDER, err := x509.MarshalPKCS8PrivateKey(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	publicDER, err := x509.MarshalPKIXPublicKey(publicKey)
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	privatePath := filepath.Join(dir, "peer_identity_ed25519.pem")
	publicPath := filepath.Join(dir, "peer_identity_ed25519.pub.pem")
	if err := os.WriteFile(privatePath, pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: privateDER}), 0o600); err != nil {
		t.Fatal(err)
	}
	publicPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: publicDER})
	if err := os.WriteFile(publicPath, publicPEM, 0o644); err != nil {
		t.Fatal(err)
	}

	var received map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		bodyHash := r.Header.Get("X-Silicium-Body-Hash")
		timestamp := r.Header.Get("X-Silicium-Timestamp")
		identityID := r.Header.Get("X-Silicium-Identity-Id")
		nodeID := r.Header.Get("X-Silicium-Node-Id")
		signature, err := hex.DecodeString(r.Header.Get("X-Silicium-Signature"))
		if err != nil {
			t.Fatal(err)
		}
		encodedPublic := r.Header.Get("X-Silicium-Public-Key")
		decodedPublic, err := base64.StdEncoding.DecodeString(encodedPublic)
		if err != nil || !bytes.Equal(decodedPublic, publicPEM) {
			t.Fatalf("unexpected public key: %v", err)
		}
		var raw json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(raw)
		if bodyHash != hex.EncodeToString(digest[:]) {
			t.Fatalf("unexpected body hash %q", bodyHash)
		}
		identityDigest := sha256.Sum256(publicPEM)
		if identityID != hex.EncodeToString(identityDigest[:])[:32] {
			t.Fatalf("unexpected identity id %q", identityID)
		}
		if _, err := strconv.ParseInt(timestamp, 10, 64); err != nil {
			t.Fatalf("unexpected timestamp %q", timestamp)
		}
		payload := strings.Join([]string{http.MethodPost, "/gossip/publish", timestamp, bodyHash, nodeID, identityID}, "\n")
		if !ed25519.Verify(publicKey, []byte(payload), signature) {
			t.Fatal("request signature did not verify")
		}
		if err := json.Unmarshal(raw, &received); err != nil {
			t.Fatal(err)
		}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	err = PublishTaskControl(context.Background(), RunnerConfig{
		ControlURL:         server.URL + "/gossip/publish",
		IdentityKeyPath:    privatePath,
		OrchestratorNodeID: "node-a",
	}, TaskControl{
		ControlID:  "control-1",
		RootJobID:  "job-1",
		Action:     "cancel",
		IssuerNode: "node-a",
	})
	if err != nil {
		t.Fatal(err)
	}
	if received["topic"] != "task_control" {
		t.Fatalf("unexpected topic %#v", received["topic"])
	}
}
