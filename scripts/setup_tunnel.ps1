# One-time setup of the permanent Cloudflare link.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_tunnel.ps1 -Hostname app.yourdomain.com
# The domain must already be active in your Cloudflare account.
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$')]
    [string]$Hostname,
    [string]$TunnelName = "cuspia"
)

$ErrorActionPreference = "Stop"

function Find-Cloudflared {
    $command = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($path in @(
            "$env:ProgramFiles\cloudflared\cloudflared.exe",
            "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe")) {
        if (Test-Path $path) { return $path }
    }
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Filter "cloudflared*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }
    throw "cloudflared is not installed. Run: winget install --id Cloudflare.cloudflared -e"
}

$cloudflared = Find-Cloudflared
$configDir = Join-Path $env:USERPROFILE ".cloudflared"

if (-not (Test-Path (Join-Path $configDir "cert.pem"))) {
    Write-Host "A browser opens: sign in to Cloudflare and choose your domain."
    & $cloudflared tunnel login
    if ($LASTEXITCODE -ne 0) { throw "Cloudflare sign-in failed." }
}

function Get-Tunnel {
    $json = (& $cloudflared tunnel list --output json | Out-String).Trim()
    if (-not $json -or $json -eq "null") { return $null }
    $list = $json | ConvertFrom-Json
    return @($list) | ForEach-Object { $_ } | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
}

$tunnel = Get-Tunnel
if (-not $tunnel) {
    & $cloudflared tunnel create $TunnelName
    if ($LASTEXITCODE -ne 0) { throw "Could not create the tunnel." }
    $tunnel = Get-Tunnel
}
if (-not $tunnel) { throw "The tunnel was not found after creation." }

$credentials = Join-Path $configDir "$($tunnel.id).json"
if (-not (Test-Path $credentials)) { throw "Tunnel credentials not found: $credentials" }

# No --overwrite-dns: an existing record for this name must never be replaced silently.
& $cloudflared tunnel route dns $TunnelName $Hostname
if ($LASTEXITCODE -ne 0) { throw "Could not point $Hostname to the tunnel." }

$config = @"
tunnel: $($tunnel.id)
credentials-file: $credentials
ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:8000
  - service: http_status:404
"@
Set-Content -Path (Join-Path $configDir "config.yml") -Value $config -Encoding ASCII

Write-Host ""
Write-Host "Done. Your permanent link: https://$Hostname"
Write-Host "Start it with: powershell -ExecutionPolicy Bypass -File scripts\start_public.ps1"
