package chainproof

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"
)

const (
	DevnetSILMint                  = "F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP"
	DefaultProgramID               = "64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG"
	splTokenProgramID              = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
	silDecimals             uint64 = 1_000_000
	paidVerifierQuorum             = 2
	maxPaidInitialFragments        = 256
)

// PaymentsEnabled reports whether this deployment accepts SIL escrow jobs.
func PaymentsEnabled() bool {
	value := strings.ToLower(strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_PAYMENTS_ENABLED")))
	return value == "1" || value == "true" || value == "yes" || value == "on"
}

func maxAdaptiveLeafFragments(initial uint32) uint32 {
	if initial == 0 || initial > maxPaidInitialFragments {
		return 0
	}
	const maxFragmentNodes uint32 = 1000
	childSlotsPerRoot := (maxFragmentNodes - initial) / initial
	maximum := initial * (1 + childSlotsPerRoot/2)
	if multiplier := initial * 16; maximum > multiplier {
		maximum = multiplier
	}
	if maximum > maxFragmentNodes {
		maximum = maxFragmentNodes
	}
	return maximum
}

// VerifySILProgramInstruction binds a confirmed wallet signature to the
// expected Silicium instruction and exact job account.
func VerifySILProgramInstruction(ctx context.Context, rpcURL, programID, signature, clientAddress, jobAddress, instruction string) error {
	if !strings.Contains(strings.ToLower(rpcURL), "devnet") {
		return errors.New("chainproof: SIL payments are restricted to Solana Devnet")
	}
	if decoded, err := Base58Decode(signature); err != nil || len(decoded) != 64 {
		return errors.New("chainproof: invalid Solana transaction signature")
	}
	if programID == "" {
		programID = DefaultProgramID
	}
	digest := sha256.Sum256([]byte("global:" + instruction))
	var result *struct {
		Transaction struct {
			Signatures []string `json:"signatures"`
			Message    struct {
				AccountKeys  []string `json:"accountKeys"`
				Instructions []struct {
					ProgramIDIndex int    `json:"programIdIndex"`
					Accounts       []int  `json:"accounts"`
					Data           string `json:"data"`
				} `json:"instructions"`
			} `json:"message"`
		} `json:"transaction"`
		Meta *struct {
			Err json.RawMessage `json:"err"`
		} `json:"meta"`
	}
	client := RPC{URL: rpcURL}
	params := []any{signature, map[string]any{"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}}
	if err := client.call(ctx, "getTransaction", params, &result); err != nil {
		return fmt.Errorf("chainproof: read transaction: %w", err)
	}
	if result == nil || result.Meta == nil || string(result.Meta.Err) != "null" {
		return errors.New("chainproof: Solana transaction is missing or failed")
	}
	keys := result.Transaction.Message.AccountKeys
	if len(keys) == 0 || len(result.Transaction.Signatures) == 0 || result.Transaction.Signatures[0] != signature || keys[0] != clientAddress {
		return errors.New("chainproof: transaction payer does not match the verified account wallet")
	}
	for _, ix := range result.Transaction.Message.Instructions {
		if ix.ProgramIDIndex < 0 || ix.ProgramIDIndex >= len(keys) || keys[ix.ProgramIDIndex] != programID || len(ix.Accounts) < 3 {
			continue
		}
		data, err := Base58Decode(ix.Data)
		if err != nil || len(data) < 8 || string(data[:8]) != string(digest[:8]) {
			continue
		}
		accountAt := func(position int) string {
			if position >= len(ix.Accounts) {
				return ""
			}
			index := ix.Accounts[position]
			if index < 0 || index >= len(keys) {
				return ""
			}
			return keys[index]
		}
		if instruction == "create_job" && accountAt(0) == clientAddress && accountAt(2) == jobAddress {
			return nil
		}
		if (instruction == "cancel_job" || instruction == "finalize_job") && accountAt(0) == clientAddress && accountAt(1) == jobAddress {
			return nil
		}
	}
	return fmt.Errorf("chainproof: transaction does not contain the expected %s for this job", instruction)
}

// VerifyOpenSILEscrow checks a freshly created Devnet job before the backend
// accepts it. The owner, mint, fragment count, reward schedule, open status,
// and actual SPL escrow balance must all match the signed quote.
func VerifyOpenSILEscrow(ctx context.Context, rpcURL, programID, jobAddress, clientAddress, mintAddress, createSignature string, expectedFragments uint32) error {
	if expectedFragments == 0 || expectedFragments > 256 {
		return errors.New("chainproof: invalid paid fragment count")
	}
	if !strings.Contains(strings.ToLower(rpcURL), "devnet") {
		return errors.New("chainproof: SIL payments are restricted to Solana Devnet")
	}
	if mintAddress != DevnetSILMint {
		return errors.New("chainproof: unexpected Devnet SIL mint")
	}
	if programID == "" {
		programID = DefaultProgramID
	}
	if _, err := Base58Decode(programID); err != nil {
		return errors.New("chainproof: invalid Solana program id")
	}
	client, err := Base58Decode(clientAddress)
	if err != nil || len(client) != 32 {
		return errors.New("chainproof: invalid verified client wallet")
	}
	if address, err := Base58Decode(jobAddress); err != nil || len(address) != 32 {
		return errors.New("chainproof: invalid Solana job address")
	}
	if err := VerifySILProgramInstruction(ctx, rpcURL, programID, createSignature, clientAddress, jobAddress, "create_job"); err != nil {
		return err
	}

	clientRPC := RPC{URL: rpcURL}
	jobOwner, jobData, err := accountData(ctx, clientRPC, jobAddress)
	if err != nil {
		return fmt.Errorf("chainproof: read escrow job: %w", err)
	}
	if jobOwner != programID || len(jobData) < 246 {
		return errors.New("chainproof: Solana job is not a valid Silicium program account")
	}
	discriminator := sha256.Sum256([]byte("account:Job"))
	if string(jobData[:8]) != string(discriminator[:8]) {
		return errors.New("chainproof: unexpected Solana job account layout")
	}
	if string(jobData[16:48]) != string(client) {
		return errors.New("chainproof: escrow belongs to another wallet")
	}
	mint, _ := Base58Decode(mintAddress)
	if string(jobData[48:80]) != string(mint) {
		return errors.New("chainproof: escrow uses a different token mint")
	}
	maxFragmentNodes := uint32(1000)
	maxFragments := maxAdaptiveLeafFragments(expectedFragments)
	currentFragments := binary.LittleEndian.Uint32(jobData[112:116])
	totalFragmentsCreated := binary.LittleEndian.Uint32(jobData[206:210])
	if uint64(currentFragments)*2 < uint64(totalFragmentsCreated) || uint64(currentFragments)*2-uint64(totalFragmentsCreated) != uint64(expectedFragments) {
		return errors.New("chainproof: escrow initial fragment count is invalid")
	}
	if binary.LittleEndian.Uint32(jobData[112:116]) != expectedFragments ||
		binary.LittleEndian.Uint32(jobData[116:120]) != 0 ||
		binary.LittleEndian.Uint32(jobData[202:206]) != maxFragmentNodes ||
		binary.LittleEndian.Uint64(jobData[120:128]) != silDecimals ||
		binary.LittleEndian.Uint64(jobData[128:136]) != silDecimals {
		return errors.New("chainproof: escrow quote does not match the fragment schedule")
	}
	verifierBudget := uint64(maxFragments) * paidVerifierQuorum * silDecimals
	deposit := uint64(maxFragments) * (1 + paidVerifierQuorum) * silDecimals
	if binary.LittleEndian.Uint64(jobData[136:144]) != verifierBudget ||
		binary.LittleEndian.Uint64(jobData[144:152]) != deposit ||
		jobData[243] != 0 {
		return errors.New("chainproof: escrow amount or job status is invalid")
	}
	if binary.LittleEndian.Uint64(jobData[184:192]) <= uint64(time.Now().Unix()) {
		return errors.New("chainproof: escrow deadline has passed")
	}
	escrowAddress := Base58Encode(jobData[80:112])
	escrowOwner, escrowData, err := accountData(ctx, clientRPC, escrowAddress)
	if err != nil {
		return fmt.Errorf("chainproof: read token escrow: %w", err)
	}
	if escrowOwner != splTokenProgramID || len(escrowData) < 72 || string(escrowData[:32]) != string(mint) {
		return errors.New("chainproof: invalid SPL escrow account")
	}
	if binary.LittleEndian.Uint64(escrowData[64:72]) != deposit {
		return errors.New("chainproof: escrow token balance does not match the quote")
	}
	return nil
}

// VerifyClosedSILEscrow accepts only the expected terminal status for the
// linked wallet and exact escrow schedule. An omitted signature is valid only
// for idempotent retries after the program has already closed the escrow.
func VerifyClosedSILEscrow(ctx context.Context, rpcURL, programID, jobAddress, clientAddress, mintAddress string, expectedFragments uint32, signature, instruction string, expectedStatus byte) error {
	if expectedFragments == 0 || expectedFragments > 256 || expectedStatus < 1 || expectedStatus > 2 {
		return errors.New("chainproof: invalid terminal escrow parameters")
	}
	if !strings.Contains(strings.ToLower(rpcURL), "devnet") || mintAddress != DevnetSILMint {
		return errors.New("chainproof: SIL payments are restricted to the configured Devnet mint")
	}
	if programID == "" {
		programID = DefaultProgramID
	}
	jobOwner, jobData, err := accountData(ctx, RPC{URL: rpcURL}, jobAddress)
	if err != nil {
		return fmt.Errorf("chainproof: read closed escrow job: %w", err)
	}
	discriminator := sha256.Sum256([]byte("account:Job"))
	client, clientErr := Base58Decode(clientAddress)
	if clientErr != nil || len(client) != 32 || jobOwner != programID || len(jobData) < 246 || string(jobData[:8]) != string(discriminator[:8]) {
		return errors.New("chainproof: terminal Solana job account is invalid")
	}
	mint, _ := Base58Decode(mintAddress)
	maxFragmentNodes := uint32(1000)
	maxFragments := maxAdaptiveLeafFragments(expectedFragments)
	currentFragments := binary.LittleEndian.Uint32(jobData[112:116])
	totalFragmentsCreated := binary.LittleEndian.Uint32(jobData[206:210])
	if uint64(currentFragments)*2 < uint64(totalFragmentsCreated) || uint64(currentFragments)*2-uint64(totalFragmentsCreated) != uint64(expectedFragments) {
		return errors.New("chainproof: terminal escrow initial fragment count is invalid")
	}
	if string(jobData[16:48]) != string(client) || string(jobData[48:80]) != string(mint) ||
		currentFragments < expectedFragments || currentFragments > maxFragments ||
		binary.LittleEndian.Uint32(jobData[202:206]) != maxFragmentNodes ||
		(expectedStatus == 1 && binary.LittleEndian.Uint32(jobData[116:120]) != currentFragments) ||
		binary.LittleEndian.Uint64(jobData[120:128]) != silDecimals ||
		binary.LittleEndian.Uint64(jobData[128:136]) != silDecimals ||
		binary.LittleEndian.Uint64(jobData[136:144]) != uint64(maxFragments)*paidVerifierQuorum*silDecimals ||
		binary.LittleEndian.Uint64(jobData[144:152]) != uint64(maxFragments)*3*silDecimals || jobData[243] != expectedStatus {
		return errors.New("chainproof: terminal escrow state does not match this account and quote")
	}
	if signature != "" {
		if err := VerifySILProgramInstruction(ctx, rpcURL, programID, signature, clientAddress, jobAddress, instruction); err != nil {
			return err
		}
	}
	return nil
}

func accountData(ctx context.Context, client RPC, address string) (string, []byte, error) {
	var result struct {
		Value *struct {
			Owner string   `json:"owner"`
			Data  []string `json:"data"`
		} `json:"value"`
	}
	if err := client.call(ctx, "getAccountInfo", []any{address, map[string]any{"encoding": "base64", "commitment": "confirmed"}}, &result); err != nil {
		return "", nil, err
	}
	if result.Value == nil || len(result.Value.Data) < 1 {
		return "", nil, errors.New("account is not present on Devnet")
	}
	data, err := base64.StdEncoding.DecodeString(result.Value.Data[0])
	if err != nil {
		return "", nil, errors.New("account data is invalid")
	}
	return result.Value.Owner, data, nil
}
