# Starts the app and its public link. Close this window (or press Ctrl+C) to take the link offline.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start_public.ps1
param([string]$TunnelName = "cuspia")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$envFile = Join-Path $root ".env"
if ((Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^AUTH_REQUIRED=(false|0|no)' -Quiet)) {
    throw "Refusing to go online: AUTH_REQUIRED is off in .env"
}

$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    foreach ($path in @(
            "$env:ProgramFiles\cloudflared\cloudflared.exe",
            "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe")) {
        if (Test-Path $path) { $cloudflared = $path; break }
    }
}
if (-not $cloudflared) {
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Filter "cloudflared*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $cloudflared = $found.FullName }
}
if (-not $cloudflared) { throw "cloudflared is not installed. Run: winget install --id Cloudflare.cloudflared -e" }

Write-Host "Building the interface..."
Push-Location frontend
try {
    if (-not (Test-Path node_modules)) { & npm.cmd install --no-fund --no-audit }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "The interface could not be built." }
} finally { Pop-Location }

$backend = Start-Process -FilePath (Join-Path $root ".venv\python.exe") `
    -ArgumentList "-X utf8 -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000" `
    -WorkingDirectory $root -NoNewWindow -PassThru

try {
    $ready = $false
    foreach ($attempt in 1..60) {
        if ($backend.HasExited) { throw "The server stopped. Is port 8000 already in use?" }
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/status" -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) { throw "The server did not start." }

    if (Test-Path (Join-Path $env:USERPROFILE ".cloudflared\config.yml")) {
        Write-Host "Permanent link online. Keep this window open and the PC awake."
        & $cloudflared tunnel run $TunnelName
    } else {
        Write-Host "No domain configured: using a TEMPORARY link (shown below as trycloudflare.com)."
        & $cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:8000"
    }
} finally {
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    Write-Host "The link is offline."
}
