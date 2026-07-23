package handler

import (
	"context"
	"sync"

	"gorm.io/gorm"
)

type Handler struct {
	DB   *gorm.DB
	runs *runRegistry
}

type runRegistry struct {
	mu      sync.Mutex
	cancels map[uint]context.CancelCauseFunc
}

func New(db *gorm.DB) Handler {
	return Handler{DB: db, runs: &runRegistry{cancels: make(map[uint]context.CancelCauseFunc)}}
}

func (h *Handler) registerRun(jobID uint, cancel context.CancelCauseFunc) {
	h.runs.mu.Lock()
	defer h.runs.mu.Unlock()
	h.runs.cancels[jobID] = cancel
}

func (h *Handler) unregisterRun(jobID uint) {
	h.runs.mu.Lock()
	defer h.runs.mu.Unlock()
	delete(h.runs.cancels, jobID)
}

func (h *Handler) cancelRun(jobID uint, cause error) bool {
	h.runs.mu.Lock()
	cancel := h.runs.cancels[jobID]
	h.runs.mu.Unlock()
	if cancel == nil {
		return false
	}
	cancel(cause)
	return true
}
