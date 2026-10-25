//! Hex and SHA-256 helpers used to encode keys, signatures and hashes of the
//! task book.
//!
//! Kept local (no `hex` crate) so the textual format stays exactly the one
//! already persisted: lowercase on output, case-insensitive on input.

use sha2::{Digest, Sha256};

/// Lowercase hex SHA-256 digest of `bytes`.
pub(super) fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    hex_encode(&digest)
}

/// Lowercase hex encoding of `bytes`.
pub(super) fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

/// Decodes exactly `N` bytes from a `2 * N`-character hex string; `None` on a
/// wrong length or a non-hex character.
pub(super) fn decode_fixed<const N: usize>(value: &str) -> Option<[u8; N]> {
    if value.len() != N * 2 {
        return None;
    }
    let bytes = value.as_bytes();
    let mut output = [0u8; N];
    for index in 0..N {
        output[index] = (hex_digit(bytes[index * 2])? << 4) | hex_digit(bytes[index * 2 + 1])?;
    }
    Some(output)
}

/// Value of one hex digit (upper or lower case).
fn hex_digit(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}
