// Minimal Solana client: one Memo transaction signed by the site wallet.
//
// Only the standard library is used: a memo transaction is a fixed, small
// binary message (one signer, one instruction), and avoiding the full SDK
// keeps this path testable without network access to its dependencies.

package chainproof

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// MemoProgramID is the SPL Memo program (v2), deployed on every cluster.
const MemoProgramID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

// maxMemoBytes keeps the memo well under the transaction size limit.
const maxMemoBytes = 500

// LoadKeypair reads a Solana CLI keypair file (JSON array of 64 bytes:
// the Ed25519 seed followed by the public key, Go's PrivateKey layout).
func LoadKeypair(path string) (ed25519.PrivateKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, errors.New("chainproof: the wallet file cannot be read")
	}
	var values []int
	if err := json.Unmarshal(data, &values); err != nil || len(values) != ed25519.PrivateKeySize {
		return nil, errors.New("chainproof: the wallet file is not a Solana keypair")
	}
	key := make([]byte, ed25519.PrivateKeySize)
	for i, value := range values {
		if value < 0 || value > 255 {
			return nil, errors.New("chainproof: the wallet file is not a Solana keypair")
		}
		key[i] = byte(value)
	}
	private := ed25519.PrivateKey(key)
	// The stored public key must match the seed, or every signature fails.
	derived := ed25519.NewKeyFromSeed(private.Seed())
	if !bytes.Equal(derived[32:], key[32:]) {
		return nil, errors.New("chainproof: the wallet public key does not match its seed")
	}
	return private, nil
}

// MemoTransaction builds and signs a legacy transaction carrying memo,
// paid and signed by key, and returns its wire bytes and signature.
func MemoTransaction(key ed25519.PrivateKey, recentBlockhash, memo string) ([]byte, string, error) {
	if len(memo) == 0 || len(memo) > maxMemoBytes {
		return nil, "", errors.New("chainproof: memo is empty or too long")
	}
	blockhash, err := Base58Decode(recentBlockhash)
	if err != nil || len(blockhash) != 32 {
		return nil, "", errors.New("chainproof: invalid recent blockhash")
	}
	program, err := Base58Decode(MemoProgramID)
	if err != nil {
		return nil, "", err
	}
	payer := key.Public().(ed25519.PublicKey)

	var message bytes.Buffer
	// Header: 1 required signature, 0 read-only signed, 1 read-only unsigned
	// account (the Memo program).
	message.Write([]byte{1, 0, 1})
	writeCompactU16(&message, 2)
	message.Write(payer)
	message.Write(program)
	message.Write(blockhash)
	writeCompactU16(&message, 1) // one instruction
	message.WriteByte(1)         // program id index: the Memo program
	writeCompactU16(&message, 1) // one account: the payer, so the memo names its signer
	message.WriteByte(0)
	writeCompactU16(&message, len(memo))
	message.WriteString(memo)

	signature := ed25519.Sign(key, message.Bytes())
	var wire bytes.Buffer
	writeCompactU16(&wire, 1)
	wire.Write(signature)
	wire.Write(message.Bytes())
	return wire.Bytes(), Base58Encode(signature), nil
}

// writeCompactU16 writes Solana's "shortvec" length: 7 bits per byte,
// high bit set while more bytes follow.
func writeCompactU16(buffer *bytes.Buffer, value int) {
	for {
		part := byte(value & 0x7f)
		value >>= 7
		if value == 0 {
			buffer.WriteByte(part)
			return
		}
		buffer.WriteByte(part | 0x80)
	}
}

// RPC is a JSON-RPC client of one Solana endpoint.
type RPC struct {
	URL    string
	Client *http.Client
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// call sends one JSON-RPC request and decodes its result into out.
func (r RPC) call(ctx context.Context, method string, params []any, out any) error {
	body, err := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, r.URL, bytes.NewReader(body))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	client := r.Client
	if client == nil {
		client = &http.Client{Timeout: 20 * time.Second}
	}
	response, err := client.Do(request)
	if err != nil {
		// A *url.Error repeats the endpoint, which may carry an API key.
		var urlErr *url.Error
		if errors.As(err, &urlErr) {
			err = urlErr.Err
		}
		return fmt.Errorf("chainproof: %s: %w", method, err)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return err
	}
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("chainproof: %s: HTTP %d", method, response.StatusCode)
	}
	var envelope struct {
		Result json.RawMessage `json:"result"`
		Error  *rpcError       `json:"error"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return fmt.Errorf("chainproof: %s: invalid response", method)
	}
	if envelope.Error != nil {
		return fmt.Errorf("chainproof: %s: %s", method, envelope.Error.Message)
	}
	return json.Unmarshal(envelope.Result, out)
}

// LatestBlockhash returns a recent blockhash to sign against.
func (r RPC) LatestBlockhash(ctx context.Context) (string, error) {
	var result struct {
		Value struct {
			Blockhash string `json:"blockhash"`
		} `json:"value"`
	}
	if err := r.call(ctx, "getLatestBlockhash", []any{map[string]any{"commitment": "confirmed"}}, &result); err != nil {
		return "", err
	}
	if result.Value.Blockhash == "" {
		return "", errors.New("chainproof: empty blockhash")
	}
	return result.Value.Blockhash, nil
}

// SendTransaction submits signed wire bytes and returns the signature.
func (r RPC) SendTransaction(ctx context.Context, wire []byte) (string, error) {
	var signature string
	options := map[string]any{"encoding": "base64", "preflightCommitment": "confirmed"}
	err := r.call(ctx, "sendTransaction", []any{base64.StdEncoding.EncodeToString(wire), options}, &signature)
	return signature, err
}

// WaitConfirmed polls until signature is confirmed, failed, or ctx ends.
func (r RPC) WaitConfirmed(ctx context.Context, signature string, every time.Duration) error {
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		var result struct {
			Value []*struct {
				ConfirmationStatus string          `json:"confirmationStatus"`
				Err                json.RawMessage `json:"err"`
			} `json:"value"`
		}
		options := map[string]any{"searchTransactionHistory": true}
		if err := r.call(ctx, "getSignatureStatuses", []any{[]string{signature}, options}, &result); err == nil &&
			len(result.Value) == 1 && result.Value[0] != nil {
			status := result.Value[0]
			if len(status.Err) > 0 && string(status.Err) != "null" {
				return fmt.Errorf("chainproof: transaction failed: %s", status.Err)
			}
			if status.ConfirmationStatus == "confirmed" || status.ConfirmationStatus == "finalized" {
				return nil
			}
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("chainproof: confirmation of %s: %w", signature, ctx.Err())
		case <-ticker.C:
		}
	}
}

// Cluster names the Solana cluster of an RPC URL, for explorer links.
func Cluster(rpcURL string) string {
	lower := strings.ToLower(rpcURL)
	switch {
	case strings.Contains(lower, "devnet"):
		return "devnet"
	case strings.Contains(lower, "testnet"):
		return "testnet"
	case strings.Contains(lower, "mainnet"):
		return "mainnet-beta"
	case strings.Contains(lower, "localhost"), strings.Contains(lower, "127.0.0.1"):
		return "custom"
	default:
		return "devnet"
	}
}

// ExplorerURL links a transaction in the Solana explorer.
func ExplorerURL(signature, cluster string) string {
	link := "https://explorer.solana.com/tx/" + signature
	if cluster != "" && cluster != "mainnet-beta" {
		link += "?cluster=" + cluster
	}
	return link
}
