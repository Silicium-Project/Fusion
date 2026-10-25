#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' 'This legacy entry point is retired. Use ./dev deploy request --manifest FILE --environment dev|prod --apply.' >&2
exit 2
