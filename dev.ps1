$ErrorActionPreference = 'Stop'
& node (Join-Path $PSScriptRoot 'tools/dev.mjs') @args
exit $LASTEXITCODE
