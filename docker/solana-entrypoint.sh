#!/usr/bin/env bash
set -euo pipefail

run_silicium_node() {
  local subcommand="${1:-start}"
  if [[ "${subcommand}" != "start" ]]; then
    cat >&2 <<'USAGE'
Usage: silicium-node start [--network devnet|testnet|mainnet] [--ledger PATH] [--identity PATH] [--vote-account PATH] [--rpc-port PORT]
       [--dynamic-port-range START-END] [--] [additional solana-validator args]
USAGE
    exit 1
  fi
  shift || true

  local network="${SILICIUM_NETWORK:-testnet}"
  local ledger_dir="${SILICIUM_LEDGER_DIR:-$HOME/.silicium/ledger}"
  local identity_path="${SILICIUM_IDENTITY_PATH:-$HOME/.config/solana/validator-identity.json}"
  local vote_account_path="${SILICIUM_VOTE_ACCOUNT_PATH:-}"
  local rpc_port="${SILICIUM_RPC_PORT:-8899}"
  local rpc_bind_address="${SILICIUM_RPC_BIND_ADDRESS:-0.0.0.0}"
  local public_rpc_address="${SILICIUM_PUBLIC_RPC_ADDRESS:-}"
  local cli_url_override="${SILICIUM_CLI_URL:-}"
  local dynamic_port_range="${SILICIUM_DYNAMIC_PORT_RANGE:-8000-8020}"
  local local_reset="${SILICIUM_LOCAL_RESET:-false}"
  local extra_args=()
  local run_localnet="false"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --network)
        network="$2"
        shift 2
        ;;
      --ledger)
        ledger_dir="$2"
        shift 2
        ;;
      --identity)
        identity_path="$2"
        shift 2
        ;;
      --vote-account)
        vote_account_path="$2"
        shift 2
        ;;
      --rpc-port)
        rpc_port="$2"
        shift 2
        ;;
      --dynamic-port-range)
        dynamic_port_range="$2"
        shift 2
        ;;
      --)
        shift
        extra_args+=("$@")
        break
        ;;
      *)
        extra_args+=("$1")
        shift
        ;;
    esac
  done

  local rpc_url=""
  local entrypoints=()
  case "$network" in
    silicium|localnet)
      rpc_url="http://127.0.0.1:${rpc_port}"
      entrypoints=()
      network="silicium"
      run_localnet="true"
      ;;
    devnet)
      rpc_url="https://api.devnet.solana.com"
      entrypoints=(
        entrypoint.devnet.solana.com:8001
        entrypoint2.devnet.solana.com:8001
        entrypoint3.devnet.solana.com:8001
      )
      ;;
    testnet)
      rpc_url="https://api.testnet.solana.com"
      entrypoints=(
        entrypoint.testnet.solana.com:8001
        entrypoint2.testnet.solana.com:8001
        entrypoint3.testnet.solana.com:8001
        # Some historical hosts may not exist; we filter unresolved below
      )
      ;;
    mainnet|mainnet-beta)
      rpc_url="https://api.mainnet-beta.solana.com"
      entrypoints=(
        entrypoint.mainnet-beta.solana.com:8001
        entrypoint2.mainnet-beta.solana.com:8001
        entrypoint3.mainnet-beta.solana.com:8001
        entrypoint4.mainnet-beta.solana.com:8001
      )
      network="mainnet-beta"
      ;;
    *)
      echo "Unknown network '$network'. Use 'silicium', 'devnet', 'testnet' or 'mainnet'." >&2
      exit 1
      ;;
  esac

  mkdir -p "$(dirname "$identity_path")" "$ledger_dir"
  if [[ ! -f "$identity_path" ]]; then
    solana-keygen new --no-bip39-passphrase --force --outfile "$identity_path" >/dev/null
    echo "Generated validator identity at $identity_path"
  fi

  if [[ -n "$vote_account_path" && ! -f "$vote_account_path" ]]; then
    mkdir -p "$(dirname "$vote_account_path")"
    solana-keygen new --no-bip39-passphrase --force --outfile "$vote_account_path" >/dev/null
    echo "Generated vote account keypair at $vote_account_path"
  fi

  local effective_cli_url="${cli_url_override:-$rpc_url}"
  solana config set --url "$effective_cli_url" >/dev/null
  if [[ -f "$identity_path" ]]; then
    solana config set --keypair "$identity_path" >/dev/null
    solana config set --keypair "$identity_path" >/dev/null
  fi

  local cmd=()

  if [[ "$run_localnet" == "true" ]]; then
    cmd=(
      solana-test-validator
      --ledger "$ledger_dir"
      --rpc-port "$rpc_port"
      --bind-address "$rpc_bind_address"
      --dynamic-port-range "$dynamic_port_range"
      --limit-ledger-size
    )

    if [[ "$local_reset" == "true" ]]; then
      cmd+=(--reset)
    fi

  else
    cmd=(
      solana-validator
      --identity "$identity_path"
      --ledger "$ledger_dir"
      --rpc-port "$rpc_port"
      --rpc-bind-address "$rpc_bind_address"
      --dynamic-port-range "$dynamic_port_range"
      --wal-recovery-mode skip_any_corrupted_record
      --no-port-check
      --limit-ledger-size
      --no-os-network-limits-test
    )

    if [[ -n "$vote_account_path" ]]; then
      cmd+=(--vote-account "$vote_account_path")
    else
      cmd+=(--no-voting)
    fi

    if [[ ${#entrypoints[@]} -gt 0 ]]; then
      # Only include entrypoints that resolve to avoid validator CLI errors
      local resolved_count=0
      for entrypoint in "${entrypoints[@]}"; do
        local host="${entrypoint%%:*}"
        if command -v getent >/dev/null 2>&1; then
          if getent hosts "$host" >/dev/null 2>&1; then
            cmd+=(--entrypoint "$entrypoint")
            ((resolved_count++)) || true
          else
            echo "Warning: skipping unresolved entrypoint $entrypoint" >&2
          fi
        else
          # Fallback: best-effort, include without pre-check
          cmd+=(--entrypoint "$entrypoint")
          ((resolved_count++)) || true
        fi
      done

      if [[ $resolved_count -eq 0 ]]; then
        echo "Error: no entrypoints resolved for network '$network'." >&2
        echo "Check DNS/connectivity or pass --entrypoint HOST:PORT via extra args." >&2
        exit 1
      fi
    fi

    if [[ -n "$public_rpc_address" ]]; then
      cmd+=(--public-rpc-address "$public_rpc_address")
    fi
  fi

  cmd+=("${extra_args[@]}")

  if [[ "$run_localnet" == "true" ]]; then
    # Expose the identity as the default CLI signer for localnet sessions
    if [[ -f "$identity_path" ]]; then
      mkdir -p "$HOME/.config/solana"
      cp "$identity_path" "$HOME/.config/solana/id.json"
      chmod 600 "$HOME/.config/solana/id.json"
    fi
    echo "Starting Silicium localnet (RPC URL: $rpc_url)"
    echo "Ledger directory: $ledger_dir"
  else
    echo "Starting silicium node on network '$network' (RPC URL: $rpc_url)"
  fi
  exec "${cmd[@]}"
}

ensure_default_signer() {
  local default_signer="$HOME/.config/solana/id.json"
  if [[ ! -f "$default_signer" ]]; then
    mkdir -p "$(dirname "$default_signer")"
    solana-keygen new --no-bip39-passphrase --force --outfile "$default_signer" >/dev/null
    chmod 600 "$default_signer"
    echo "Generated default signer at $default_signer"
  fi
}

configure_cli_defaults() {
  local network="${SILICIUM_NETWORK:-testnet}"
  local rpc_port="${SILICIUM_RPC_PORT:-8899}"
  local default_url=""
  case "$network" in
    silicium|localnet)
      default_url="http://127.0.0.1:${rpc_port}"
      ;;
    devnet)
      default_url="https://api.devnet.solana.com"
      ;;
    testnet)
      default_url="https://api.testnet.solana.com"
      ;;
    mainnet|mainnet-beta)
      default_url="https://api.mainnet-beta.solana.com"
      ;;
    *)
      default_url=""
      ;;
  esac

  local cli_url="${SILICIUM_CLI_URL:-$default_url}"
  if [[ -n "$cli_url" ]]; then
    solana config set --url "$cli_url" >/dev/null
  fi
}

if [[ $# -eq 0 ]]; then
  ensure_default_signer
  configure_cli_defaults
  exec solana
fi

case "$1" in
  solana)
    shift
    ensure_default_signer
    configure_cli_defaults
    exec solana "$@"
    ;;
  silicium-node)
    shift
    run_silicium_node "$@"
    ;;
  -*)
    ensure_default_signer
    configure_cli_defaults
    exec solana "$@"
    ;;
  bash|sh|/bin/bash|/bin/sh)
    exec "$@"
    ;;
  *)
    if command -v "$1" >/dev/null 2>&1; then
      exec "$@"
    else
      ensure_default_signer
      configure_cli_defaults
      exec solana "$@"
    fi
    ;;
esac
