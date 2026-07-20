[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Executable = Join-Path $Root 'release\M5AIDictationServer\M5AIDictationServer.exe'
$CertificateBase64 = $env:WINDOWS_SIGNING_CERTIFICATE_BASE64
$CertificatePassword = $env:WINDOWS_SIGNING_CERTIFICATE_PASSWORD
$TimestampUrl = $env:WINDOWS_SIGNING_TIMESTAMP_URL

if ([string]::IsNullOrWhiteSpace($CertificateBase64)) {
    throw 'GitHub secret WINDOWS_SIGNING_CERTIFICATE_BASE64 is not configured.'
}
if ([string]::IsNullOrWhiteSpace($CertificatePassword)) {
    throw 'GitHub secret WINDOWS_SIGNING_CERTIFICATE_PASSWORD is not configured.'
}
if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
    $TimestampUrl = 'http://timestamp.digicert.com'
}
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "Windows executable not found: $Executable"
}

$SignTool = Get-Command signtool.exe -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty Source -First 1
if (-not $SignTool) {
    $KitsBin = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $SignTool = Get-ChildItem -LiteralPath $KitsBin -Filter signtool.exe -File -Recurse `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -ExpandProperty FullName -First 1
}
if (-not $SignTool) {
    throw 'signtool.exe was not found on this Windows runner.'
}

$TemporaryRoot = if ($env:RUNNER_TEMP) {
    $env:RUNNER_TEMP
} else {
    Join-Path $Root '.build\signing'
}
New-Item -ItemType Directory -Path $TemporaryRoot -Force | Out-Null
$PfxPath = Join-Path $TemporaryRoot ("m5-dictation-codesign-{0}.pfx" -f [guid]::NewGuid())
$ImportedCertificates = @()

try {
    try {
        [IO.File]::WriteAllBytes(
            $PfxPath,
            [Convert]::FromBase64String($CertificateBase64)
        )
    }
    catch {
        throw 'WINDOWS_SIGNING_CERTIFICATE_BASE64 is not a valid Base64-encoded PFX file.'
    }

    $SecurePassword = ConvertTo-SecureString $CertificatePassword -AsPlainText -Force
    $ImportedCertificates = @(
        Import-PfxCertificate `
            -FilePath $PfxPath `
            -CertStoreLocation 'Cert:\CurrentUser\My' `
            -Password $SecurePassword `
            -Exportable:$false
    )
    $SigningCertificate = $ImportedCertificates |
        Where-Object {
            $_.HasPrivateKey -and
            $_.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.3'
        } |
        Select-Object -First 1
    if (-not $SigningCertificate) {
        throw 'The PFX does not contain a certificate valid for code signing.'
    }

    & $SignTool sign `
        /fd SHA256 `
        /sha1 $SigningCertificate.Thumbprint `
        /s My `
        /tr $TimestampUrl `
        /td SHA256 `
        $Executable
    if ($LASTEXITCODE -ne 0) {
        throw "signtool.exe failed to sign the executable (exit code $LASTEXITCODE)."
    }

    & $SignTool verify /pa /v $Executable
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode verification failed (exit code $LASTEXITCODE)."
    }

    Write-Host "Signed and verified: $Executable"
}
finally {
    foreach ($Certificate in $ImportedCertificates) {
        if ($Certificate.Thumbprint) {
            Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($Certificate.Thumbprint)" `
                -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $PfxPath -Force -ErrorAction SilentlyContinue
}
