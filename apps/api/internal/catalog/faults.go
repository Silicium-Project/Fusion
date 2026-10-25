package catalog

// Quarantine on the network's word: a node that downloads a pinned file of
// a model and gets other bytes from the Hub (another size or hash at the
// pinned commit) never keeps it, and lists the model's key in
// `capacity.ai_model_faults` of its heartbeat. Once `MinFaultReports`
// different nodes report the same model, it is quarantined: the site stops
// offering it and the BackEnd stops sending jobs for it, until someone
// looks (the sync's own check of the Hub tree may also have caught it).

import (
	"context"
	"log"
	"sort"
	"time"
)

// MinFaultReports is the number of different nodes that must report a model
// before it is quarantined (one node may have a broken disk or proxy).
const MinFaultReports = 2

// FaultReports reads the node's `/v1/peers` payload: for each model key, the
// nodes (by node id) that report a wrong file from the Hub.
func FaultReports(payload map[string]any) map[string][]string {
	reporters := map[string]map[string]bool{}
	peers, _ := payload["peers"].([]any)
	for _, item := range peers {
		peer, ok := item.(map[string]any)
		if !ok {
			continue
		}
		node, _ := peer["node_id"].(string)
		if node == "" {
			node, _ = peer["peer_id"].(string)
		}
		capacity, _ := peer["capacity"].(map[string]any)
		faults, _ := capacity["ai_model_faults"].([]any)
		if node == "" {
			continue
		}
		for _, value := range faults {
			key, ok := value.(string)
			if !ok || key == "" {
				continue
			}
			if reporters[key] == nil {
				reporters[key] = map[string]bool{}
			}
			reporters[key][node] = true
		}
	}
	out := make(map[string][]string, len(reporters))
	for key, nodes := range reporters {
		list := make([]string, 0, len(nodes))
		for node := range nodes {
			list = append(list, node)
		}
		sort.Strings(list)
		out[key] = list
	}
	return out
}

// QuarantineReported quarantines the models reported by at least
// MinFaultReports nodes and not quarantined yet; it returns their keys.
func (s Store) QuarantineReported(reports map[string][]string) ([]string, error) {
	keys := make([]string, 0, len(reports))
	for key, nodes := range reports {
		if len(nodes) >= MinFaultReports {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	quarantined := []string{}
	for _, key := range keys {
		row, err := s.Get(key)
		if err != nil || row.Status == string(StatusQuarantined) {
			continue
		}
		if err := s.Quarantine(key, "network.hub_file_mismatch"); err != nil {
			return quarantined, err
		}
		log.Printf("Catalog: model %s quarantined (%d nodes got other files from the Hub)", key, len(reports[key]))
		quarantined = append(quarantined, key)
	}
	return quarantined, nil
}

// WatchFaults reads the peers every `interval` and quarantines the models
// they report (see the package documentation of this file).
func (s Store) WatchFaults(ctx context.Context, interval time.Duration, peers func(context.Context) (map[string]any, error)) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if payload, err := peers(ctx); err == nil {
			if _, err := s.QuarantineReported(FaultReports(payload)); err != nil {
				log.Printf("Catalog: reported models not quarantined: %v", err)
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
