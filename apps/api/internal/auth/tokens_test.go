package auth

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestAccessAndRefreshTokensAreNotInterchangeable(t *testing.T) {
	access, err := IssueAccess(7, "user", time.Now())
	if err != nil {
		t.Fatal(err)
	}
	refresh, err := IssueRefresh(7, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if id, err := ParseAccess(access); err != nil || id != "7" {
		t.Fatalf("access token refused: %v", err)
	}
	if id, err := ParseRefresh(refresh); err != nil || id != "7" {
		t.Fatalf("refresh token refused: %v", err)
	}
	if _, err := ParseAccess(refresh); err == nil {
		t.Fatal("a refresh token was accepted as an access token")
	}
	if _, err := ParseRefresh(access); err == nil {
		t.Fatal("an access token was accepted as a refresh token")
	}
}

func TestTokensWithoutAudienceExpiryOrHS256AreRefused(t *testing.T) {
	expires := jwt.NewNumericDate(time.Now().Add(time.Minute))
	for name, token := range map[string]*jwt.Token{
		"no audience": jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{Subject: "7", ExpiresAt: expires}),
		"no expiry":   jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{Subject: "7", Audience: jwt.ClaimStrings{AccessAudience}}),
		"HS384":       jwt.NewWithClaims(jwt.SigningMethodHS384, jwt.RegisteredClaims{Subject: "7", Audience: jwt.ClaimStrings{AccessAudience}, ExpiresAt: expires}),
		"no subject":  jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{Audience: jwt.ClaimStrings{AccessAudience}, ExpiresAt: expires}),
		"bad subject": jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{Subject: "1 OR 1=1", Audience: jwt.ClaimStrings{AccessAudience}, ExpiresAt: expires}),
	} {
		signed, err := token.SignedString(signingKey())
		if err != nil {
			t.Fatal(err)
		}
		if _, err := ParseAccess(signed); err == nil {
			t.Fatalf("%s: token accepted", name)
		}
	}
}

func TestProductionRequiresASecretKey(t *testing.T) {
	t.Setenv("JWT_SECRET_KEY", "")
	if CheckKey("prod") == nil {
		t.Fatal("production started without JWT_SECRET_KEY")
	}
	t.Setenv("JWT_SECRET_KEY", placeholderKey)
	if CheckKey("prod") == nil {
		t.Fatal("production started with the example key")
	}
	if CheckKey("dev") != nil {
		t.Fatal("dev refused to start without a key")
	}
}
