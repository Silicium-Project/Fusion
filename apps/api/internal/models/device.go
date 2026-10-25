package models

import "time"

// UserDevice is an application installation paired to one account using the
// installation's persistent libp2p identity.
type UserDevice struct {
	ID                         uint      `gorm:"primaryKey" json:"id"`
	UserID                     uint      `gorm:"not null;index" json:"userId"`
	NodeID                     string    `gorm:"size:64;not null;uniqueIndex" json:"nodeId"`
	PeerID                     string    `gorm:"size:128;not null;uniqueIndex" json:"peerId"`
	SolanaWallet               *string   `gorm:"size:44;uniqueIndex" json:"solanaWallet,omitempty"`
	PayoutWallet               *string   `gorm:"size:44;index" json:"payoutWallet,omitempty"`
	WorkerPayoutProofMessage   string    `gorm:"type:text" json:"-"`
	WorkerPayoutProofSignature string    `gorm:"size:128" json:"-"`
	LinkedAt                   time.Time `json:"linkedAt"`
	CreatedAt                  time.Time `json:"createdAt"`
	UpdatedAt                  time.Time `json:"updatedAt"`
}

// DevicePairingCode is a single-use, short-lived account authorization. Only
// the SHA-256 digest of the code is stored.
type DevicePairingCode struct {
	ID           uint       `gorm:"primaryKey" json:"-"`
	UserID       uint       `gorm:"not null;index" json:"-"`
	NodeID       string     `gorm:"size:64;index" json:"-"`
	PayoutWallet *string    `gorm:"size:44" json:"-"`
	CodeHash     string     `gorm:"size:64;not null;uniqueIndex" json:"-"`
	ExpiresAt    time.Time  `gorm:"not null;index" json:"-"`
	ConsumedAt   *time.Time `json:"-"`
	CreatedAt    time.Time  `json:"-"`
}
