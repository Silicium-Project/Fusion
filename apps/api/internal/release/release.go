package release

import (
	"fmt"
	"os"
	"strings"
)

const (
	Dev  = "dev"
	Prod = "prod"
)

type Metadata struct {
	Channel        string `json:"release_channel"`
	Version        string `json:"release_version"`
	Build          string `json:"release_build"`
	ID             string `json:"release_id,omitempty"`
	ManifestDigest string `json:"manifest_digest,omitempty"`
}

func Validate(channel string) error {
	switch strings.ToLower(strings.TrimSpace(channel)) {
	case "", Dev, Prod:
		return nil
	default:
		return fmt.Errorf("unsupported release channel %q (expected dev or prod)", channel)
	}
}

func Current() Metadata {
	channel := strings.ToLower(strings.TrimSpace(os.Getenv("SILICIUM_RELEASE_CHANNEL")))
	if channel != Dev && channel != Prod {
		channel = Dev
	}
	version := strings.TrimSpace(os.Getenv("SILICIUM_RELEASE_VERSION"))
	if version == "" {
		version = strings.TrimSpace(os.Getenv("SILICIUM_APP_VERSION"))
	}
	if version == "" {
		version = "unknown"
	}
	build := strings.TrimSpace(os.Getenv("SILICIUM_RELEASE_BUILD"))
	if build == "" {
		build = "local"
	}
	return Metadata{Channel: channel, Version: version, Build: build, ID: strings.TrimSpace(os.Getenv("SILICIUM_RELEASE_ID")), ManifestDigest: strings.TrimSpace(os.Getenv("SILICIUM_MANIFEST_DIGEST"))}
}
