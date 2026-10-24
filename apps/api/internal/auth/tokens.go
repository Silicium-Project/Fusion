// Package auth signs and checks the session tokens of the API.
//
// A session has two tokens, both HS256 JWTs signed with JWT_SECRET_KEY:
//   - the access token (15 minutes), sent as `Authorization: Bearer` on
//     every request, with the audience AccessAudience;
//   - the refresh token (7 days), only accepted by POST /refresh, with the
//     audience RefreshAudience.
//
// The audience keeps the two apart: a stolen or leaked refresh token cannot
// be used as a 7-day access token, and an access token cannot renew itself
// forever.
package auth

import (
	"crypto/rand"
	"errors"
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const (
	// AccessAudience marks access tokens.
	AccessAudience = "silicium-api"
	// RefreshAudience marks refresh tokens.
	RefreshAudience = "silicium-refresh"
	// AccessLifetime is the lifetime of an access token.
	AccessLifetime = 15 * time.Minute
	// RefreshLifetime is the lifetime of a refresh token.
	RefreshLifetime = 7 * 24 * time.Hour

	// minKeyLength is the shortest secret accepted without a warning.
	minKeyLength = 32
	// placeholderKey is the value of deploy/env/backend.example.env.
	placeholderKey = "GENERATE_A_RANDOM_SECRET_OF_AT_LEAST_32_CHARACTERS"
)

// Claims are the claims of a session token: the user id is the subject.
type Claims struct {
	Role string `json:"role,omitempty"`
	jwt.RegisteredClaims
}

var (
	keyOnce sync.Once
	key     []byte
)

// signingKey is JWT_SECRET_KEY, or a random key for this process when it is
// missing (sessions then end when the API restarts, which is better than a
// key published in the source code). Production refuses to start without a
// key: see CheckKey.
func signingKey() []byte {
	keyOnce.Do(func() {
		configured := strings.TrimSpace(os.Getenv("JWT_SECRET_KEY"))
		if configured != "" && configured != placeholderKey {
			key = []byte(configured)
			return
		}
		log.Println("WARNING: JWT_SECRET_KEY is not set: using a random key, sessions end when the API restarts.")
		key = make([]byte, 64)
		if _, err := rand.Read(key); err != nil {
			panic("auth: no randomness for the session key: " + err.Error())
		}
	})
	return key
}

// CheckKey validates JWT_SECRET_KEY at startup: missing or left at the
// example value it is an error in production, and a warning elsewhere.
func CheckKey(channel string) error {
	configured := strings.TrimSpace(os.Getenv("JWT_SECRET_KEY"))
	production := strings.EqualFold(strings.TrimSpace(channel), "prod")
	switch {
	case configured == "" || configured == placeholderKey:
		if production {
			return errors.New("JWT_SECRET_KEY must be set to a random secret in production")
		}
	case len(configured) < minKeyLength:
		log.Printf("WARNING: JWT_SECRET_KEY is shorter than %d characters.", minKeyLength)
	}
	signingKey()
	return nil
}

// IssueAccess signs an access token for a user.
func IssueAccess(userID uint, role string, now time.Time) (string, error) {
	return sign(userID, role, AccessAudience, now.Add(AccessLifetime))
}

// IssueRefresh signs a refresh token for a user.
func IssueRefresh(userID uint, now time.Time) (string, error) {
	return sign(userID, "", RefreshAudience, now.Add(RefreshLifetime))
}

func sign(userID uint, role, audience string, expires time.Time) (string, error) {
	claims := Claims{Role: role, RegisteredClaims: jwt.RegisteredClaims{
		Subject:   strconv.FormatUint(uint64(userID), 10),
		Audience:  jwt.ClaimStrings{audience},
		ExpiresAt: jwt.NewNumericDate(expires),
		IssuedAt:  jwt.NewNumericDate(time.Now()),
	}}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(signingKey())
}

// ErrInvalidToken is returned for any token that is not a valid session
// token of the expected kind.
var ErrInvalidToken = errors.New("invalid session token")

// ParseAccess checks an access token and returns its user id.
func ParseAccess(token string) (string, error) { return parse(token, AccessAudience) }

// ParseRefresh checks a refresh token and returns its user id.
func ParseRefresh(token string) (string, error) { return parse(token, RefreshAudience) }

func parse(token, audience string) (string, error) {
	claims := &Claims{}
	parsed, err := jwt.ParseWithClaims(token, claims, func(*jwt.Token) (any, error) {
		return signingKey(), nil
	}, jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}), jwt.WithExpirationRequired(), jwt.WithAudience(audience))
	if err != nil || !parsed.Valid {
		return "", ErrInvalidToken
	}
	subject := strings.TrimSpace(claims.Subject)
	if id, err := strconv.ParseUint(subject, 10, 64); err != nil || id == 0 {
		return "", ErrInvalidToken
	}
	return subject, nil
}
