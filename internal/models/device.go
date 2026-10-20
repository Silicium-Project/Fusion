package models

import "time"

// UserDevice is an application installation paired to one account using the
// installation's persistent libp2p identity.
type UserDevice struct {
	ID        uint      `gorm:"primaryKey" json:"id"`
	UserID    uint      `gorm:"not null;index" json:"userId"`
	NodeID    string    `gorm:"size:64;not null;uniqueIndex" json:"nodeId"`
	PeerID    string    `gorm:"size:128;not null;uniqueIndex" json:"peerId"`
	LinkedAt  time.Time `json:"linkedAt"`
	CreatedAt time.Time `json:"createdAt"`
	UpdatedAt time.Time `json:"updatedAt"`
}

// DevicePairingCode is a single-use, short-lived account authorization. Only
// the SHA-256 digest of the code is stored.
type DevicePairingCode struct {
	ID         uint       `gorm:"primaryKey" json:"-"`
	UserID     uint       `gorm:"not null;index" json:"-"`
	CodeHash   string     `gorm:"size:64;not null;uniqueIndex" json:"-"`
	ExpiresAt  time.Time  `gorm:"not null;index" json:"-"`
	ConsumedAt *time.Time `json:"-"`
	CreatedAt  time.Time  `json:"-"`
}
