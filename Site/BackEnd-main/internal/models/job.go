package models

import "time"

type Job struct {
	ID              uint       `gorm:"primaryKey" json:"id"`
	UserID          uint       `gorm:"not null;index" json:"userId"`
	Title           string     `gorm:"size:120;not null" json:"title"`
	Description     string     `gorm:"type:text" json:"description"`
	Workload        string     `gorm:"size:80;not null;default:'raytracer'" json:"workload"`
	Priority        string     `gorm:"size:20;not null;default:'high'" json:"priority"`
	Status          string     `gorm:"size:32;not null;default:'queued';index" json:"status"`
	SiliciumJobID   string     `gorm:"size:128;uniqueIndex;not null" json:"siliciumJobId"`
	InputPath       string     `gorm:"type:text;not null" json:"-"`
	ResultPath      string     `gorm:"type:text" json:"-"`
	SummaryPath     string     `gorm:"type:text" json:"-"`
	DevnetTracePath string     `gorm:"type:text" json:"-"`
	DevnetJob       string     `gorm:"size:128" json:"devnetJob,omitempty"`
	DashboardURL    string     `gorm:"type:text" json:"dashboardUrl,omitempty"`
	ErrorMessage    string     `gorm:"type:text" json:"errorMessage,omitempty"`
	StartedAt       *time.Time `json:"startedAt,omitempty"`
	CompletedAt     *time.Time `json:"completedAt,omitempty"`
	CreatedAt       time.Time  `json:"createdAt"`
	UpdatedAt       time.Time  `json:"updatedAt"`
}
