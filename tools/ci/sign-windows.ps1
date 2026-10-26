$ErrorActionPreference = 'Stop'
if (!$env:WINDOWS_CERTIFICATE_BASE64 -or !$env:WINDOWS_SIGNING_THUMBPRINT) {
    throw 'Protected Windows signing certificate and expected thumbprint are required'
}
$pfx = Join-Path $env:RUNNER_TEMP "silicium-certificate-$env:GITHUB_RUN_ID.pfx"
$certificate = $null
try {
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_BASE64))
    $password = ConvertTo-SecureString $env:WINDOWS_CERTIFICATE_PASSWORD -AsPlainText -Force
    $certificate = Import-PfxCertificate -FilePath $pfx -CertStoreLocation 'Cert:\CurrentUser\My' -Password $password
    if ($certificate.Thumbprint -ne $env:WINDOWS_SIGNING_THUMBPRINT) { throw 'Signing certificate thumbprint mismatch' }
    foreach ($file in Get-ChildItem '.artifacts/installers/*.exe') {
        $signature = Set-AuthenticodeSignature -FilePath $file.FullName -Certificate $certificate -HashAlgorithm SHA256
        if ($signature.Status -ne 'Valid') { throw "Authenticode verification failed: $($signature.Status)" }
        $verified = Get-AuthenticodeSignature -FilePath $file.FullName
        if ($verified.Status -ne 'Valid' -or $verified.SignerCertificate.Thumbprint -ne $env:WINDOWS_SIGNING_THUMBPRINT) { throw 'Signed installer verification failed' }
    }
} finally {
    Remove-Item $pfx -Force -ErrorAction SilentlyContinue
    if ($certificate) { Remove-Item "Cert:\CurrentUser\My\$($certificate.Thumbprint)" -Force -ErrorAction SilentlyContinue }
}
