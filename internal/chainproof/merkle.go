// Merkle tree over the task leaves, and the per-task inclusion proofs.

package chainproof

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
)

// ProofStep is one sibling on the path from a leaf to the root.
type ProofStep struct {
	// Sibling is the hex hash combined with the current one.
	Sibling string `json:"sibling"`
	// Left is true when Sibling goes on the left: hash(0x01 || sibling || current).
	Left bool `json:"left"`
}

// MerkleRoot returns the root of the tree over hex leaf hashes.
//
// Inner nodes are SHA-256(0x01 || left || right). A level with an odd count
// promotes its last node unchanged (no duplication, so two different leaf
// lists cannot share a root).
func MerkleRoot(leaves []string) (string, error) {
	level, err := decodeLevel(leaves)
	if err != nil {
		return "", err
	}
	for len(level) > 1 {
		level = nextLevel(level)
	}
	return hex.EncodeToString(level[0]), nil
}

// MerkleProof returns the path proving that leaves[index] is in the tree.
func MerkleProof(leaves []string, index int) ([]ProofStep, error) {
	level, err := decodeLevel(leaves)
	if err != nil {
		return nil, err
	}
	if index < 0 || index >= len(level) {
		return nil, errors.New("chainproof: leaf index out of range")
	}
	proof := []ProofStep{}
	for len(level) > 1 {
		sibling := index ^ 1
		if sibling < len(level) {
			proof = append(proof, ProofStep{Sibling: hex.EncodeToString(level[sibling]), Left: sibling < index})
		}
		level = nextLevel(level)
		index /= 2
	}
	return proof, nil
}

// VerifyProof reports whether leaf, combined along proof, gives root.
func VerifyProof(leaf string, proof []ProofStep, root string) bool {
	current, err := hex.DecodeString(leaf)
	if err != nil || len(current) != sha256.Size {
		return false
	}
	for _, step := range proof {
		sibling, err := hex.DecodeString(step.Sibling)
		if err != nil || len(sibling) != sha256.Size {
			return false
		}
		if step.Left {
			current = innerHash(sibling, current)
		} else {
			current = innerHash(current, sibling)
		}
	}
	return hex.EncodeToString(current) == root
}

func decodeLevel(leaves []string) ([][]byte, error) {
	if len(leaves) == 0 {
		return nil, errors.New("chainproof: no leaf")
	}
	level := make([][]byte, len(leaves))
	for i, leaf := range leaves {
		decoded, err := hex.DecodeString(leaf)
		if err != nil || len(decoded) != sha256.Size {
			return nil, errors.New("chainproof: a leaf is not a hex SHA-256")
		}
		level[i] = decoded
	}
	return level, nil
}

func nextLevel(level [][]byte) [][]byte {
	next := make([][]byte, 0, (len(level)+1)/2)
	for i := 0; i < len(level); i += 2 {
		if i+1 == len(level) {
			next = append(next, level[i])
			continue
		}
		next = append(next, innerHash(level[i], level[i+1]))
	}
	return next
}

func innerHash(left, right []byte) []byte {
	buffer := make([]byte, 0, 1+len(left)+len(right))
	buffer = append(buffer, 0x01)
	buffer = append(buffer, left...)
	buffer = append(buffer, right...)
	digest := sha256.Sum256(buffer)
	return digest[:]
}
