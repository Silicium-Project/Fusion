#!/bin/bash
set -u

wallet_path="${SILICIUM_SOLANA_WALLET_PATH:-/data/solana-wallet.json}"
wallet_address="$(/usr/local/bin/solana-worker-wallet ensure "$wallet_path")" || exit 1
printf ' Devnet worker wallet: %s\n' "$wallet_address"

pairing_code_file="${SILICIUM_DEVICE_PAIRING_CODE_FILE:-/run/secrets/device-pairing-code}"
pairing_api_url="${SILICIUM_DEVICE_PAIRING_API_URL:-http://backend:8080/devices/pair}"
pairing_marker="/data/account-link-code.sha256"

pair_account() {
	while true; do
		if [[ ! -r "$pairing_code_file" ]]; then
			sleep 30
			continue
		fi
		pairing_code="$(tr -d '[:space:]' < "$pairing_code_file")"
		if [[ -z "$pairing_code" ]]; then
			sleep 30
			continue
		fi
		if [[ ! "$pairing_code" =~ ^[[:xdigit:]]{64}$ ]]; then
			echo ' Account pairing code is malformed; waiting for a valid account-link request.'
			sleep 30
			continue
		fi

		pairing_hash="$(printf '%s' "$pairing_code" | sha256sum | cut -d ' ' -f 1)"
		stored_pairing_hash="$(cat "$pairing_marker" 2>/dev/null || true)"
		if [[ "$pairing_hash" == "$stored_pairing_hash" ]]; then return; fi

		proof_file="$(mktemp /tmp/device-pairing.XXXXXX.json)"
		chmod 0600 "$proof_file"
		if SILICIUM_DEVICE_LINK_CODE="$pairing_code" \
		  SILICIUM_NODE_ID="${SILICIUM_NODE_ID:-}" \
		  SILICIUM_DATA_DIR="${SILICIUM_DATA_DIR:-/data}" \
		  /usr/local/bin/p2p_node --sign-device-link > "$proof_file" 2>/dev/null; then
		  pairing_status=''
		  for attempt in $(seq 1 10); do
		    pairing_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
		      --max-time 5 --header 'Content-Type: application/json' \
		      --data-binary "@$proof_file" "$pairing_api_url" 2>/dev/null || true)"
		    if [[ "$pairing_status" == 200 ]]; then break; fi
		    case "$pairing_status" in
		      ''|000|429|500|502|503|504) sleep 2 ;;
		      *) break ;;
		    esac
		  done
		  if [[ "$pairing_status" == 200 ]]; then
		    umask 077
		    printf '%s\n' "$pairing_hash" > "$pairing_marker"
		    echo ' Account linked to the website.'
		    rm -f "$proof_file"
		    return
		  else
		    echo " Account pairing rejected or pending (HTTP ${pairing_status:-unavailable}); waiting for a fresh account-link request."
		  fi
		else
		  echo ' Account pairing could not sign this device; retrying while the worker keeps running.'
		fi
		rm -f "$proof_file"
		sleep 30
	done
}

/usr/local/bin/compute_daemon &
compute_pid=$!

/usr/local/bin/p2p_node &
node_pid=$!

pair_pid=''
stop_children() {
  if [[ -n "$pair_pid" ]]; then
    kill "$pair_pid" 2>/dev/null || true
  fi
  kill "$node_pid" "$compute_pid" 2>/dev/null || true
  if [[ -n "$pair_pid" ]]; then
    wait "$pair_pid" 2>/dev/null || true
  fi
  wait "$node_pid" 2>/dev/null || true
  wait "$compute_pid" 2>/dev/null || true
}
trap stop_children INT TERM HUP

# Pairing retries in the background so a website or relay outage cannot delay
# peer discovery, heartbeats, or task execution.
pair_account &
pair_pid=$!

# Restart the whole container if either half of the worker fails. This keeps
# Docker's restart policy responsible for recovery without hiding a dead
# compute daemon behind a healthy P2P process.
wait -n "$node_pid" "$compute_pid" || true

stop_children
exit 1
