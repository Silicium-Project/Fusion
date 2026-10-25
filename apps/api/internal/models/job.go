package models

import "time"

type Job struct {
	ID                 uint       `gorm:"primaryKey" json:"id"`
	UserID             uint       `gorm:"not null;index" json:"userId"`
	Title              string     `gorm:"size:120;not null" json:"title"`
	Description        string     `gorm:"type:text" json:"description"`
	Workload           string     `gorm:"size:80;not null;default:'raytracer'" json:"workload"`
	Priority           string     `gorm:"size:20;not null;default:'high'" json:"priority"`
	FragmentCount      int        `gorm:"not null;default:0" json:"fragmentCount"`
	Status             string     `gorm:"size:32;not null;default:'queued';index" json:"status"`
	SiliciumJobID      string     `gorm:"size:128;uniqueIndex;not null" json:"siliciumJobId"`
	InputPath          string     `gorm:"type:text;not null" json:"-"`
	ResultPath         string     `gorm:"type:text" json:"resultPath,omitempty"`
	SummaryPath        string     `gorm:"type:text" json:"summaryPath,omitempty"`
	DevnetTracePath    string     `gorm:"type:text" json:"devnetTracePath,omitempty"`
	DevnetJob          string     `gorm:"size:128" json:"devnetJob,omitempty"`
	SolanaJob          string     `gorm:"size:64;uniqueIndex:idx_jobs_solana_job,where:solana_job <> ''" json:"solanaJob,omitempty"`
	SolanaExpected     int        `gorm:"not null;default:0" json:"solanaExpectedFragments,omitempty"`
	SolanaCreateTx     string     `gorm:"size:128" json:"solanaCreateSignature,omitempty"`
	SolanaRefundTx     string     `gorm:"size:128" json:"solanaRefundSignature,omitempty"`
	SolanaRefunded     bool       `gorm:"not null;default:false" json:"solanaRefunded,omitempty"`
	SolanaFinalizeTx   string     `gorm:"size:128" json:"solanaFinalizeSignature,omitempty"`
	SolanaFinalized    bool       `gorm:"not null;default:false" json:"solanaFinalized,omitempty"`
	ErrorMessage       string     `gorm:"type:text" json:"errorMessage,omitempty"`
	DeadlineAt         *time.Time `json:"deadlineAt,omitempty"`
	CancelRequestedAt  *time.Time `json:"cancelRequestedAt,omitempty"`
	CancelledAt        *time.Time `json:"cancelledAt,omitempty"`
	CancelReason       string     `gorm:"type:text" json:"cancelReason,omitempty"`
	BillableWorkUnits  uint64     `gorm:"not null;default:0" json:"billableWorkUnits"`
	ComputeReceiptHash string     `gorm:"size:64" json:"computeReceiptHash,omitempty"`
	// NetworkMetadata keeps the scheduler/RPC view attached to this same Job.
	NetworkMetadata map[string]any `gorm:"serializer:json;type:jsonb" json:"network,omitempty"`
	StartedAt       *time.Time     `json:"startedAt,omitempty"`
	CompletedAt     *time.Time     `json:"completedAt,omitempty"`
	CreatedAt       time.Time      `json:"createdAt"`
	UpdatedAt       time.Time      `json:"updatedAt"`

	// CollectionID groups the document-search jobs searched together: the
	// first job of a collection, then the jobs that add documents to it.
	CollectionID string `gorm:"size:128;index" json:"collectionId,omitempty"`
}
