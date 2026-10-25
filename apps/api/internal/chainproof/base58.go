// Bitcoin-alphabet Base58, the text form of Solana keys, hashes and signatures.

package chainproof

import (
	"errors"
	"math/big"
)

const base58Alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

// Base58Encode encodes data; each leading zero byte becomes a leading '1'.
func Base58Encode(data []byte) string {
	number := new(big.Int).SetBytes(data)
	radix := big.NewInt(58)
	remainder := new(big.Int)
	var out []byte
	for number.Sign() > 0 {
		number.DivMod(number, radix, remainder)
		out = append(out, base58Alphabet[remainder.Int64()])
	}
	for _, value := range data {
		if value != 0 {
			break
		}
		out = append(out, '1')
	}
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return string(out)
}

// Base58Decode reverses Base58Encode.
func Base58Decode(text string) ([]byte, error) {
	if text == "" {
		return nil, errors.New("chainproof: empty base58 string")
	}
	number := new(big.Int)
	radix := big.NewInt(58)
	for _, char := range []byte(text) {
		index := -1
		for i := 0; i < len(base58Alphabet); i++ {
			if base58Alphabet[i] == char {
				index = i
				break
			}
		}
		if index < 0 {
			return nil, errors.New("chainproof: invalid base58 character")
		}
		number.Mul(number, radix)
		number.Add(number, big.NewInt(int64(index)))
	}
	decoded := number.Bytes()
	zeros := 0
	for zeros < len(text) && text[zeros] == '1' {
		zeros++
	}
	return append(make([]byte, zeros), decoded...), nil
}
