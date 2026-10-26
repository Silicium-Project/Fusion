"""Solana wallet of a channel, used by the BackEnd to anchor job traces.

The BackEnd (`internal/chainproof`) signs one Memo transaction per finished
job with this keypair. The file uses the Solana CLI format: a JSON array of
64 bytes, the Ed25519 seed followed by the public key.

Usage:
    solana_wallet.py ensure <path>   create the keypair if missing, print its address
    solana_wallet.py address <path>  print the address of an existing keypair

The keypair is generated with `openssl` (the Python standard library has no
Ed25519), so no Solana tooling is needed on the VPS.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58(data: bytes) -> str:
    """Bitcoin-alphabet Base58, the text form of Solana addresses."""
    number = int.from_bytes(data, "big")
    out = ""
    while number:
        number, remainder = divmod(number, 58)
        out = BASE58_ALPHABET[remainder] + out
    leading_zeros = len(data) - len(data.lstrip(b"\0"))
    return "1" * leading_zeros + out


def generate_keypair() -> bytes:
    """64 bytes: a fresh Ed25519 seed followed by its public key."""
    with tempfile.TemporaryDirectory() as directory:
        private_der = Path(directory) / "key.der"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ed25519", "-outform", "DER", "-out", str(private_der)],
            check=True,
            capture_output=True,
        )
        public_der = subprocess.run(
            ["openssl", "pkey", "-inform", "DER", "-in", str(private_der), "-pubout", "-outform", "DER"],
            check=True,
            capture_output=True,
        ).stdout
        # PKCS#8 and SubjectPublicKeyInfo of Ed25519 end with the raw 32 bytes.
        seed = private_der.read_bytes()[-32:]
    return seed + public_der[-32:]


def read_keypair(path: Path) -> bytes:
    """The 64 key bytes of a Solana CLI keypair file."""
    values = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(values, list) or len(values) != 64:
        raise ValueError(f"{path} is not a Solana keypair")
    return bytes(values)


def write_keypair(path: Path, keypair: bytes) -> None:
    """Writes the keypair readable by its owner only, atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(list(keypair), file)
    os.replace(temporary, path)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in {"ensure", "address"}:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[2])
    if argv[1] == "ensure" and not (path.exists() and path.stat().st_size > 0):
        write_keypair(path, generate_keypair())
    print(base58(read_keypair(path)[32:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
