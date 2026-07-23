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
	InputPath          string     `gorm:"type:text;not null" json:"inputPath"`
	ResultPath         string     `gorm:"type:text" json:"resultPath,omitempty"`
	SummaryPath        string     `gorm:"type:text" json:"summaryPath,omitempty"`
	DevnetTracePath    string     `gorm:"type:text" json:"devnetTracePath,omitempty"`
	DevnetJob          string     `gorm:"size:128" json:"devnetJob,omitempty"`
	DashboardURL       string     `gorm:"type:text" json:"dashboardUrl,omitempty"`
	ErrorMessage       string     `gorm:"type:text" json:"errorMessage,omitempty"`
	DeadlineAt         *time.Time `json:"deadlineAt,omitempty"`
	CancelRequestedAt  *time.Time `json:"cancelRequestedAt,omitempty"`
	CancelledAt        *time.Time `json:"cancelledAt,omitempty"`
	CancelReason       string     `gorm:"type:text" json:"cancelReason,omitempty"`
	BillableWorkUnits  uint64     `gorm:"not null;default:0" json:"billableWorkUnits"`
	ComputeReceiptHash string     `gorm:"size:64" json:"computeReceiptHash,omitempty"`
	StartedAt          *time.Time `json:"startedAt,omitempty"`
	CompletedAt        *time.Time `json:"completedAt,omitempty"`
	CreatedAt          time.Time  `json:"createdAt"`
	UpdatedAt          time.Time  `json:"updatedAt"`
}
