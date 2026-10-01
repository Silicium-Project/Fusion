"""On-chain (Solana) reputation profile of this node and of known peers."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tools.node.constants import TOOLS_DIR
from tools.node.util import reputation_value, utc_now


class OnchainProfileMixin:
    """Refresh on-chain reputation for the local worker and its peers."""

    @staticmethod
    def _onchain_account_fields(account: Any) -> tuple[float, float, float, float, float, str]:
        """(global, compute, verify, storage, stake, status) of a worker account.

        Accepts both the camelCase (Anchor JS) and snake_case field names.
        """
        onchain_global = reputation_value(account, "globalReputation") or reputation_value(account, "global_reputation")
        onchain_compute = reputation_value(account, "computeReputation") or reputation_value(account, "compute_reputation")
        onchain_verify = reputation_value(account, "verifyReputation") or reputation_value(account, "verify_reputation")
        onchain_storage = reputation_value(account, "storageReputation") or reputation_value(account, "storage_reputation")
        onchain_stake = reputation_value(account, "stakeAmount") or reputation_value(account, "stake_amount")
        onchain_status = str(account.get("status", "")) if isinstance(account, dict) else str(getattr(account, "status", ""))
        return onchain_global, onchain_compute, onchain_verify, onchain_storage, onchain_stake, onchain_status

    def solana_owner_pubkey(self) -> str:
        """Base58 owner key of the configured wallet (via node + @solana/web3.js), cached."""
        if self._solana_owner:
            return self._solana_owner
        try:
            secret = json.loads(Path(self.config.solana_wallet).expanduser().read_text(encoding="utf-8"))
            completed = subprocess.run(
                [
                    "node",
                    "-e",
                    (
                        "const {Keypair}=require('@solana/web3.js');"
                        "const kp=Keypair.fromSecretKey(Uint8Array.from(JSON.parse(process.argv[1])));"
                        "console.log(kp.publicKey.toBase58());"
                    ),
                    json.dumps(secret),
                ],
                cwd=str(TOOLS_DIR.resolve().parent / "solana-layer"),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                self._solana_owner = completed.stdout.strip()
        except Exception:
            self._solana_owner = ""
        return self._solana_owner

    def refresh_local_onchain_profile(self, *, force: bool = False) -> None:
        """Refresh this worker's on-chain reputation (rate-limited unless forced)."""
        if not self.config.solana_enable or not self.config.solana_reputation_enable:
            return
        now = time.time()
        if not force and (now - self._last_reputation_refresh_unix) < max(1, self.config.solana_reputation_refresh_s):
            return
        owner = self.solana_owner_pubkey()
        if not owner:
            return
        try:
            snapshot = self.solana.call("fetch_worker", {"owner": owner})
        except Exception:
            return
        account = snapshot.get("account", {}) if isinstance(snapshot, dict) else {}
        accounts = snapshot.get("accounts", {}) if isinstance(snapshot, dict) else {}
        onchain_global, onchain_compute, onchain_verify, onchain_storage, onchain_stake, onchain_status = (
            self._onchain_account_fields(account)
        )
        self._solana_owner = str(accounts.get("owner", owner))
        self._solana_worker = str(accounts.get("worker", ""))
        self._solana_onchain_reputation = onchain_global
        self._solana_onchain_compute_reputation = onchain_compute
        self._solana_onchain_verify_reputation = onchain_verify
        self._solana_onchain_storage_reputation = onchain_storage
        self._solana_onchain_stake_amount = onchain_stake
        self._solana_onchain_status = onchain_status
        self._last_reputation_refresh_unix = now
        self.peer_network.set_local_profile(
            capacity=self.runtime.capacity(),
            reputation_score=self.reputation.local_score(),
            onchain_reputation=onchain_global,
            onchain_global_reputation=onchain_global,
            onchain_compute_reputation=onchain_compute,
            onchain_verify_reputation=onchain_verify,
            onchain_storage_reputation=onchain_storage,
            onchain_stake_amount=onchain_stake,
            onchain_status=onchain_status,
            solana_owner=self._solana_owner,
            solana_worker=self._solana_worker,
        )

    def refresh_known_peer_onchain_reputations(self, *, force: bool = False) -> None:
        """Refresh the on-chain reputation of every known peer with a Solana owner."""
        if not self.config.solana_enable or not self.config.solana_reputation_enable:
            return
        if not force and (time.time() - self._last_peer_reputation_refresh_unix) < max(1, self.config.solana_reputation_refresh_s):
            return
        attempted = False
        for peer in self.peer_network.peers_snapshot().get("peers", []):
            if not isinstance(peer, dict) or peer.get("self"):
                continue
            owner = str(peer.get("solana_owner", "")).strip()
            if not owner:
                continue
            attempted = True
            try:
                snapshot = self.solana.call("fetch_worker", {"owner": owner})
            except Exception:
                continue
            account = snapshot.get("account", {}) if isinstance(snapshot, dict) else {}
            accounts = snapshot.get("accounts", {}) if isinstance(snapshot, dict) else {}
            onchain_global, onchain_compute, onchain_verify, onchain_storage, onchain_stake, onchain_status = (
                self._onchain_account_fields(account)
            )
            self.peer_network.update_peer_metadata(
                str(peer.get("node_id", "")),
                {
                    "onchain_reputation": onchain_global,
                    "onchain_global_reputation": onchain_global,
                    "onchain_compute_reputation": onchain_compute,
                    "onchain_verify_reputation": onchain_verify,
                    "onchain_storage_reputation": onchain_storage,
                    "onchain_stake_amount": onchain_stake,
                    "onchain_status": onchain_status,
                    "solana_worker": str(accounts.get("worker", peer.get("solana_worker", ""))),
                    "solana_owner": str(accounts.get("owner", owner)),
                    "onchain_verified_utc": utc_now(),
                },
            )
        # Do not throttle the next refresh when peer discovery has not yet
        # converged. A one-shot scheduler may learn the peer immediately after
        # this pass and must be able to fetch its on-chain profile then.
        if attempted:
            self._last_peer_reputation_refresh_unix = time.time()
