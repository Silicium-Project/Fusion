package security

import (
	"errors"
	"os"
	"strings"
)

// JWTKey returns the application signing key. There is deliberately no
// built-in fallback: a known development key would let anyone forge tokens on
// a misconfigured deployment.
func JWTKey() ([]byte, error) {
	key := strings.TrimSpace(os.Getenv("JWT_SECRET_KEY"))
	lowerKey := strings.ToLower(key)
	if len(key) < 32 || strings.HasPrefix(lowerKey, "change-me") || strings.HasPrefix(lowerKey, "your_jwt") || strings.HasPrefix(lowerKey, "generate_") {
		return nil, errors.New("JWT_SECRET_KEY must be a non-placeholder secret of at least 32 characters")
	}
	return []byte(key), nil
}
