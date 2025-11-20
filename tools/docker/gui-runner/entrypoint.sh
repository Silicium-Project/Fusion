#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUMBER=${VNC_DISPLAY:-99}
VNC_PORT=${VNC_PORT:-5900}
SCREEN_GEOMETRY=${VNC_SCREEN:-1280x720x24}

export DISPLAY=":${DISPLAY_NUMBER}"

Xvfb "${DISPLAY}" -screen 0 "${SCREEN_GEOMETRY}" -ac -nolisten tcp &
XVFB_PID=$!

x11vnc -display "${DISPLAY}" \
       -rfbport "${VNC_PORT}" \
       -forever -shared -nopw -quiet -bg

if command -v xset >/dev/null 2>&1; then
    for _ in $(seq 1 50); do
        if xset -display "${DISPLAY}" q >/dev/null 2>&1; then
            break
        fi
        sleep 0.1
    done
else
    sleep 0.5
fi

cleanup() {
    kill "${XVFB_PID}" >/dev/null 2>&1 || true
    pkill -P "${XVFB_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ $# -eq 0 ]]; then
    exec tail -f /dev/null
else
    # Propagate env to child process
    exec "$@"
fi
