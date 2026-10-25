package handler

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"testing"
	"time"

	"github.com/gagliardetto/solana-go"
)

func TestWalletChallengeIsBoundAndSingleUse(t *testing.T) {
	store := newWalletChallengeStore()
	now := time.Date(2026, 9, 6, 12, 0, 0, 0, time.UTC)
	challenge, err := store.issue(7, "wallet-a", now)
	if err != nil {
		t.Fatal(err)
	}
	if challenge.Nonce == "" || challenge.Message == "" || !challenge.ExpiresAt.Equal(now.Add(walletChallengeLifetime)) {
		t.Fatalf("unexpected challenge: %#v", challenge)
	}
	if _, err := store.consume(8, "wallet-a", challenge.Nonce, now); !errors.Is(err, errWalletChallengeInvalid) {
		t.Fatalf("challenge accepted for another user: %v", err)
	}
	if _, err := store.consume(7, "wallet-a", challenge.Nonce, now); !errors.Is(err, errWalletChallengeInvalid) {
		t.Fatal("a rejected challenge must not remain reusable")
	}

	challenge, err = store.issue(7, "wallet-a", now)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.consume(7, "wallet-a", challenge.Nonce, challenge.ExpiresAt); !errors.Is(err, errWalletChallengeInvalid) {
		t.Fatal("expired challenge accepted")
	}
}

func TestVerifyWalletSignature(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	var wallet solana.PublicKey
	copy(wallet[:], publicKey)
	message := "Silicium wallet ownership"
	signature := base64.StdEncoding.EncodeToString(ed25519.Sign(privateKey, []byte(message)))
	if err := verifyWalletSignature(wallet.String(), message, signature); err != nil {
		t.Fatalf("valid signature rejected: %v", err)
	}
	if err := verifyWalletSignature(wallet.String(), message+" modified", signature); !errors.Is(err, errWalletSignatureInvalid) {
		t.Fatalf("modified message accepted: %v", err)
	}
	if err := verifyWalletSignature("not-a-wallet", message, signature); err == nil {
		t.Fatal("invalid wallet accepted")
	}
}
