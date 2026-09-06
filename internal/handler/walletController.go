package handler

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/gagliardetto/solana-go"
)

const walletChallengeLifetime = 5 * time.Minute

var (
	errWalletChallengeInvalid = errors.New("wallet challenge is invalid or expired")
	errWalletSignatureInvalid = errors.New("wallet signature is invalid")
)

type walletChallenge struct {
	UserID    uint
	Address   string
	Nonce     string
	Message   string
	ExpiresAt time.Time
}

type walletChallengeStore struct {
	mu      sync.Mutex
	entries map[string]walletChallenge
}

func newWalletChallengeStore() *walletChallengeStore {
	return &walletChallengeStore{entries: make(map[string]walletChallenge)}
}

func (s *walletChallengeStore) issue(userID uint, address string, now time.Time) (walletChallenge, error) {
	nonce := make([]byte, 32)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return walletChallenge{}, err
	}
	challenge := walletChallenge{
		UserID:    userID,
		Address:   strings.TrimSpace(address),
		Nonce:     base64.RawURLEncoding.EncodeToString(nonce),
		ExpiresAt: now.UTC().Add(walletChallengeLifetime),
	}
	challenge.Message = fmt.Sprintf(
		"Silicium — vérification du portefeuille\n\nAdresse : %s\nChallenge : %s\nExpiration : %s\n\nCette signature ne déclenche aucune transaction.",
		challenge.Address,
		challenge.Nonce,
		challenge.ExpiresAt.Format(time.RFC3339),
	)

	s.mu.Lock()
	defer s.mu.Unlock()
	for key, entry := range s.entries {
		if !entry.ExpiresAt.After(now) || (entry.UserID == userID && entry.Address == challenge.Address) {
			delete(s.entries, key)
		}
	}
	s.entries[challenge.Nonce] = challenge
	return challenge, nil
}

func (s *walletChallengeStore) consume(userID uint, address, nonce string, now time.Time) (walletChallenge, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	entry, ok := s.entries[strings.TrimSpace(nonce)]
	if ok {
		delete(s.entries, entry.Nonce)
	}
	if !ok || entry.UserID != userID || entry.Address != strings.TrimSpace(address) || !entry.ExpiresAt.After(now) {
		return walletChallenge{}, errWalletChallengeInvalid
	}
	return entry, nil
}

func validateWalletAddress(address string) (solana.PublicKey, error) {
	publicKey, err := solana.PublicKeyFromBase58(strings.TrimSpace(address))
	if err != nil || publicKey == (solana.PublicKey{}) {
		return solana.PublicKey{}, errors.New("invalid Solana wallet address")
	}
	return publicKey, nil
}

func verifyWalletSignature(address, message, encodedSignature string) error {
	publicKey, err := validateWalletAddress(address)
	if err != nil {
		return err
	}
	signature, err := base64.StdEncoding.DecodeString(strings.TrimSpace(encodedSignature))
	if err != nil {
		signature, err = base64.RawStdEncoding.DecodeString(strings.TrimSpace(encodedSignature))
	}
	if err != nil || len(signature) != ed25519.SignatureSize || !ed25519.Verify(publicKey[:], []byte(message), signature) {
		return errWalletSignatureInvalid
	}
	return nil
}
