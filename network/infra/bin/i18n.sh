#!/usr/bin/env bash

sil_i18n_root() {
  if [[ -n "${SILICIUM_I18N_ROOT:-}" ]]; then
    printf "%s" "$SILICIUM_I18N_ROOT"
    return 0
  fi
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  printf "%s" "$(cd "$script_dir/../.." && pwd)"
}

sil_i18n_shell_dir() {
  if [[ -n "${SILICIUM_I18N_SHELL_DIR:-}" ]]; then
    printf "%s" "$SILICIUM_I18N_SHELL_DIR"
    return 0
  fi
  printf "%s/i18n/shell" "$(sil_i18n_root)"
}

sil_i18n_locale_dir() {
  if [[ -n "${SILICIUM_I18N_LOCALE_DIR:-}" ]]; then
    printf "%s" "$SILICIUM_I18N_LOCALE_DIR"
    return 0
  fi
  printf "%s/i18n/locales" "$(sil_i18n_root)"
}

sil_i18n_locale() {
  local raw="${SILICIUM_LOCALE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-en-US}}}}"
  raw="${raw%%.*}"
  raw="${raw%%@*}"
  case "$raw" in
    ""|C|POSIX)
      printf "en-US"
      ;;
    *)
      printf "%s" "$raw"
      ;;
  esac
}

sil_i18n_python_bin() {
  if [[ -n "${SILICIUM_I18N_PYTHON_BIN:-}" ]]; then
    printf "%s" "$SILICIUM_I18N_PYTHON_BIN"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf "%s" "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf "%s" "python"
    return 0
  fi
  return 1
}

sil_i18n_json_lookup() {
  local catalog="$1"
  local key="$2"
  local py_bin
  py_bin="$(sil_i18n_python_bin 2>/dev/null)" || return 1
  [[ -f "$catalog" ]] || return 1
  local message=""
  message="$(
    SIL_I18N_KEY="$key" "$py_bin" - "$catalog" 2>/dev/null <<'PY'
import json
import os
import sys

catalog = sys.argv[1]
key = os.environ.get("SIL_I18N_KEY", "")
if not key:
    raise SystemExit(0)

with open(catalog, "r", encoding="utf-8") as handle:
    payload = json.load(handle)
value = payload.get("messages", {}).get(key, "")
if isinstance(value, str):
    sys.stdout.write(value)
PY
  )"
  if [[ -n "$message" ]]; then
    printf "%s" "$message"
    return 0
  fi
  return 1
}

sil_i18n_lookup() {
  local key="$1"
  local shell_dir locale_dir locale language
  shell_dir="$(sil_i18n_shell_dir)"
  locale_dir="$(sil_i18n_locale_dir)"
  locale="$(sil_i18n_locale)"
  language="${locale%%[-_]*}"

  local candidate
  for candidate in "$locale" "$language" "en-US"; do
    [[ -z "$candidate" ]] && continue
    local json_catalog="${locale_dir}/${candidate}.json"
    local json_message
    json_message="$(sil_i18n_json_lookup "$json_catalog" "$key" || true)"
    if [[ -n "$json_message" ]]; then
      printf "%s" "$json_message"
      return 0
    fi

    local shell_catalog="${shell_dir}/${candidate}.sh"
    [[ -f "$shell_catalog" ]] || continue
    unset -f sil_i18n_catalog_lookup >/dev/null 2>&1 || true
    # shellcheck source=/dev/null
    . "$shell_catalog"
    if declare -F sil_i18n_catalog_lookup >/dev/null 2>&1; then
      local message
      message="$(sil_i18n_catalog_lookup "$key")"
      if [[ -n "$message" ]]; then
        printf "%s" "$message"
        return 0
      fi
    fi
  done
  printf "[missing:%s]" "$key"
}

sil_i18n_echo() {
  local key="$1"
  shift
  local fmt
  fmt="$(sil_i18n_lookup "$key")"
  printf "$fmt\n" "$@"
}
