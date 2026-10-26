$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pin = Get-Content (Join-Path $root 'tools/config/powershell-analysis.json') -Raw | ConvertFrom-Json
$temporary = Join-Path ([IO.Path]::GetTempPath()) "silicium-ps-analysis-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $archive = Join-Path $temporary 'module.zip'
    Invoke-WebRequest -Uri $pin.url -OutFile $archive
    if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) { throw 'PSScriptAnalyzer checksum mismatch' }
    Expand-Archive $archive -DestinationPath (Join-Path $temporary 'module')
    $manifest = @(Get-ChildItem (Join-Path $temporary 'module') -Filter PSScriptAnalyzer.psd1 -Recurse)
    if ($manifest.Count -ne 1) { throw 'Expected exactly one pinned analysis module' }
    Import-Module $manifest[0].FullName -Force
    $rules = @('PSAvoidUsingInvokeExpression', 'PSAvoidUsingEmptyCatchBlock', 'PSAvoidUsingPlainTextForPassword', 'PSAvoidDefaultValueForMandatoryParameter', 'PSMisleadingBacktick', 'PSUseCorrectCasing')
    $inventory = & node (Join-Path $root 'tools/dev.mjs') workspace files --json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inventory workspace sources' }
    $paths = @(($inventory | ConvertFrom-Json) | Where-Object { $_ -like '*.ps1' -and $_ -notlike 'docs/archive/*' })
    if ($LASTEXITCODE -ne 0 -or $paths.Count -eq 0) { throw 'Cannot inventory PowerShell sources' }
    $failures = @()
    foreach ($relative in $paths) {
        $file = Join-Path $root $relative
        $syntaxErrors = $null
        $tokens = $null
        [Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$syntaxErrors) | Out-Null
        if ($syntaxErrors) { $failures += $syntaxErrors }
        $failures += @(Invoke-ScriptAnalyzer -Path $file -IncludeRule $rules -Severity Error, Warning)
    }
    if ($failures.Count) {
        $failures | Format-Table -AutoSize | Out-String | Write-Output
        throw "PowerShell analysis failed: $($failures.Count) finding(s)"
    }
    Write-Output "PSScriptAnalyzer $($pin.version): $($paths.Count) scripts"
} finally {
    Remove-Item $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
