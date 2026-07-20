package handler

import (
	"io"
	"net/http"
	"os"
)

func (h *Handler) GetNetworkPeers(w http.ResponseWriter, r *http.Request) {
	peersFilePath := "/var/lib/silicium/network/orchestrator/export/node.orchestrator-1.peers.json"
	file, err := os.Open(peersFilePath)
	if err != nil {
		http.Error(w, "Could not open peers registry: "+err.Error(), http.StatusInternalServerError)
		return
	}
	defer file.Close()

	w.Header().Set("Content-Type", "application/json")
	if _, err := io.Copy(w, file); err != nil {
		http.Error(w, "Could not read peers registry", http.StatusInternalServerError)
	}
}
