#!/usr/bin/env bash
# Simple validator: compile & split a program, run the real binary and the splitter summary, and diff their outputs.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: tools/check_split.sh <source_path> [program_libs]

Steps:
  1) make run in splitter with PROGRAM=<source_path> PROGRAM_LIBS=<program_libs>
  2) run the compiled binary (run_build/<name>) and capture stdout/exit code
  3) run fragment_executor on the generated summary (emulation) and capture stdout/exit code
  4) diff outputs and report status

Notes:
  - Runs from repo root.
  - Uses emulation mode for safety. Set EXECUTOR_FLAGS="--native" to force native.
EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

PROGRAM_PATH="$1"
PROGRAM_LIBS=""
EXTRA_MAKE_VARS=()
EXTRA_ENV=()

shift
while [[ $# -gt 0 ]]; do
    arg="$1"
    if [[ "$arg" == *"="* ]]; then
        EXTRA_MAKE_VARS+=("$arg")
        case "$arg" in
            SKIP_HASH=*) EXTRA_ENV+=("$arg") ;;
        esac
    elif [[ -z "$PROGRAM_LIBS" ]]; then
        PROGRAM_LIBS="$arg"
    else
        EXTRA_MAKE_VARS+=("$arg")
    fi
    shift
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPLITTER_DIR="$ROOT_DIR/splitter"
EXECUTOR="$ROOT_DIR/executor/fragment_executor"

if [[ ! -x "$EXECUTOR" ]]; then
    echo "Executor introuvable: $EXECUTOR" >&2
    exit 1
fi

prog_name="$(basename "$PROGRAM_PATH")"
prog_stem="${prog_name%.*}"
real_bin="$SPLITTER_DIR/run_build/$prog_stem"
summary="$SPLITTER_DIR/run_output/$prog_stem/summary.json"

cleanup() {
    [[ -n "${REAL_OUT:-}" && -f "$REAL_OUT" ]] && rm -f "$REAL_OUT"
    [[ -n "${SPLIT_OUT:-}" && -f "$SPLIT_OUT" ]] && rm -f "$SPLIT_OUT"
}
trap cleanup EXIT

echo "==> Ãƒâ€°tape 1 : build & split ($PROGRAM_PATH)"
(
    cd "$SPLITTER_DIR"
    make clean >/dev/null
    make all >/dev/null
    make prep-program PROGRAM="$PROGRAM_PATH" PROGRAM_LIBS="$PROGRAM_LIBS" "${EXTRA_MAKE_VARS[@]}"
    ./splitter "run_build/$prog_stem" --output-dir "run_output/$prog_stem"
)

if [[ ! -x "$real_bin" ]]; then
    echo "Binaire construit introuvable: $real_bin" >&2
    exit 1
fi
if [[ ! -f "$summary" ]]; then
    echo "Summary introuvable: $summary" >&2
    exit 1
fi

REAL_OUT="$(mktemp -t check_split_real.XXXXXX)"
SPLIT_OUT="$(mktemp -t check_split_split.XXXXXX)"

echo "==> Ãƒâ€°tape 2 : exÃƒÂ©cution binaire rÃƒÂ©el"
set +e
"$real_bin" >"$REAL_OUT"
real_rc=$?
set -e

echo "==> Ãƒâ€°tape 3 : exÃƒÂ©cution summary (fragment_executor)"
set +e
if [[ ${#EXTRA_ENV[@]} -gt 0 ]]; then
    env "${EXTRA_ENV[@]}" "$EXECUTOR" --summary "$summary" ${EXECUTOR_FLAGS:-} >"$SPLIT_OUT"
else
    "$EXECUTOR" --summary "$summary" ${EXECUTOR_FLAGS:-} >"$SPLIT_OUT"
fi
split_rc=$?
set -e

echo "==> Ãƒâ€°tape 4 : comparaison"
diff -u "$REAL_OUT" "$SPLIT_OUT" || diff_rc=$? || true

status=0
if [[ ${diff_rc:-0} -ne 0 || $real_rc -ne $split_rc ]]; then
    status=1
    echo "Ãƒâ€°CHEC : sorties diffÃƒÂ©rentes ou codes de retour divergents."
    echo "  real rc=$real_rc, split rc=$split_rc"
    echo "  stdout rÃƒÂ©el : $REAL_OUT"
    echo "  stdout split: $SPLIT_OUT"
else
    echo "OK : mÃƒÂªmes sorties et mÃƒÂªme code de retour."
fi

exit $status
