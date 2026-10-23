#!/usr/bin/env bash
# Repository hygiene guards (RULES.md G1 and G3).
# - no tracked file over 1 MiB, except the applied design mockups;
# - no archive, binary or model extension;
# - no Fusion .gitignore rule targeting a submodule path.
set -euo pipefail

max_kib=1024
allow_large='^design/mockups/precision-v4-2026-10-20/'
forbidden_ext='\.(zip|exe|dll|msi|onnx|safetensors|gguf|ppm|pfx)$'
status=0

while IFS= read -r -d '' path; do
  [[ -f "$path" ]] || continue
  size_kib=$(( ($(stat -c %s "$path") + 1023) / 1024 ))
  if (( size_kib > max_kib )) && [[ ! "$path" =~ $allow_large ]]; then
    echo "::error file=$path::tracked file is ${size_kib} KiB (limit ${max_kib} KiB)"
    status=1
  fi
  if [[ "$path" =~ $forbidden_ext ]]; then
    echo "::error file=$path::archives, binaries and models must not be committed"
    status=1
  fi
done < <(git ls-files -z)

if grep -nE '^!?(Network|BackEnd|FrontEnd)/' .gitignore; then
  echo "::error file=.gitignore::submodule paths belong in the submodule's own .gitignore"
  status=1
fi

exit "$status"
