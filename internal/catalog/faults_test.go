package catalog

import (
	"reflect"
	"testing"
)

func peersReporting(faults map[string][]string) map[string]any {
	peers := []any{}
	for node, keys := range faults {
		list := []any{}
		for _, key := range keys {
			list = append(list, key)
		}
		peers = append(peers, map[string]any{"node_id": node, "capacity": map[string]any{"ai_model_faults": list}})
	}
	return map[string]any{"peers": peers}
}

func TestFaultReportsCountDifferentNodes(t *testing.T) {
	reports := FaultReports(peersReporting(map[string][]string{
		"node-a": {"m1", "m1", "m2"},
		"node-b": {"m1"},
	}))
	want := map[string][]string{"m1": {"node-a", "node-b"}, "m2": {"node-a"}}
	if !reflect.DeepEqual(reports, want) {
		t.Fatalf("reports = %v", reports)
	}
	if got := FaultReports(map[string]any{"peers": []any{map[string]any{"capacity": map[string]any{"ai_model_faults": []any{"m1"}}}}}); len(got) != 0 {
		t.Fatalf("a peer without id is ignored: %v", got)
	}
}

func TestTwoNodesQuarantineAModel(t *testing.T) {
	store := testStore(t)
	for _, key := range []string{"m1", "m2"} {
		if err := store.DB.Create(&Model{Key: key, Repository: "org/" + key, Revision: "r", Status: string(StatusAdmitted)}).Error; err != nil {
			t.Fatal(err)
		}
	}
	reports := FaultReports(peersReporting(map[string][]string{"a": {"m1", "m2"}, "b": {"m1"}}))
	quarantined, err := store.QuarantineReported(reports)
	if err != nil || !reflect.DeepEqual(quarantined, []string{"m1"}) {
		t.Fatalf("quarantined = %v, %v", quarantined, err)
	}
	m1, _ := store.Get("m1")
	m2, _ := store.Get("m2")
	if m1.Status != string(StatusQuarantined) || m2.Status != string(StatusAdmitted) {
		t.Fatalf("statuses = %s, %s", m1.Status, m2.Status)
	}
	if again, _ := store.QuarantineReported(reports); len(again) != 0 {
		t.Fatalf("quarantined twice: %v", again)
	}
}
