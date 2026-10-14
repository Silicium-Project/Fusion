from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deploy.release import solana_wallet


def test_base58_matches_solana_program_ids() -> None:
    assert solana_wallet.base58(bytes(32)) == "1" * 32
    memo_program = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
    number = 0
    for char in memo_program:
        number = number * 58 + solana_wallet.BASE58_ALPHABET.index(char)
    assert solana_wallet.base58(number.to_bytes(32, "big")) == memo_program


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is needed to generate a key")
def test_ensure_creates_a_private_keypair_once(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    wallet = tmp_path / "solana" / "id.json"
    assert solana_wallet.main(["solana_wallet.py", "ensure", str(wallet)]) == 0
    address = capsys.readouterr().out.strip()
    keypair = json.loads(wallet.read_text(encoding="utf-8"))
    assert len(keypair) == 64 and all(0 <= value <= 255 for value in keypair)
    assert wallet.stat().st_mode & 0o077 == 0
    assert address == solana_wallet.base58(bytes(keypair[32:]))

    # A second deployment keeps the funded wallet.
    assert solana_wallet.main(["solana_wallet.py", "ensure", str(wallet)]) == 0
    assert capsys.readouterr().out.strip() == address
    assert json.loads(wallet.read_text(encoding="utf-8")) == keypair


def test_deploy_enables_the_trace_only_with_a_wallet() -> None:
    deploy = (Path(__file__).resolve().parents[1] / "deploy/compose/deploy.sh").read_text(encoding="utf-8")
    assert "solana_wallet.py\" ensure" in deploy
    assert "SILICIUM_DEVNET_TRACE=$devnet_trace" in deploy
    assert "'SILICIUM_DEVNET_TRACE=0'" not in deploy
