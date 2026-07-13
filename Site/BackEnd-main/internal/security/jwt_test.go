package security

import "testing"

func TestJWTKeyRequiresAConfiguredStrongSecret(t *testing.T) {
	t.Setenv("JWT_SECRET_KEY", "")
	if _, err := JWTKey(); err == nil {
		t.Fatal("JWTKey accepted an empty secret")
	}

	t.Setenv("JWT_SECRET_KEY", "too-short")
	if _, err := JWTKey(); err == nil {
		t.Fatal("JWTKey accepted a short secret")
	}

	t.Setenv("JWT_SECRET_KEY", "change-me-with-a-long-random-secret")
	if _, err := JWTKey(); err == nil {
		t.Fatal("JWTKey accepted the documented placeholder")
	}

	t.Setenv("JWT_SECRET_KEY", "GENERATE_A_RANDOM_SECRET_OF_AT_LEAST_32_CHARACTERS")
	if _, err := JWTKey(); err == nil {
		t.Fatal("JWTKey accepted the environment-file placeholder")
	}

	secret := "0123456789abcdef0123456789abcdef"
	t.Setenv("JWT_SECRET_KEY", secret)
	key, err := JWTKey()
	if err != nil {
		t.Fatalf("JWTKey rejected a valid secret: %v", err)
	}
	if string(key) != secret {
		t.Fatal("JWTKey returned a different secret")
	}
}
