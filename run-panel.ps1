# Start the panel, locked, reachable from other machines.
#
# Usage:
#   .\run-panel.ps1                 # bind all interfaces on 8000
#   .\run-panel.ps1 -Port 8787      # different port
#   .\run-panel.ps1 -NewPassword    # rotate the password
#
# The password lives in .panel-password (git-ignored) and is read at launch, so
# it never has to sit in your shell history.

param(
    [int]$Port = 8000,
    [string]$Bind = "0.0.0.0",
    [switch]$NewPassword
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$pwFile = Join-Path $root ".panel-password"

function New-StrongPassword {
    # URL-safe, no ambiguous characters, 24 chars ~ 140 bits
    $alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    -join (1..24 | ForEach-Object { $alphabet[(Get-Random -Maximum $alphabet.Length)] })
}

if ($NewPassword -or -not (Test-Path $pwFile)) {
    $pw = New-StrongPassword
    Set-Content -Path $pwFile -Value $pw -NoNewline
    Write-Host "Generated a new panel password in $pwFile" -ForegroundColor Yellow
}

$env:PANEL_PASSWORD = (Get-Content $pwFile -Raw).Trim()
if (-not $env:PANEL_PASSWORD) { throw "Empty password in $pwFile" }

$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
          Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.*" } |
          Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "  Contact Forms panel" -ForegroundColor Cyan
Write-Host "  local : http://127.0.0.1:$Port"
if ($lanIp) { Write-Host "  LAN   : http://${lanIp}:$Port" }
Write-Host "  pass  : $env:PANEL_PASSWORD" -ForegroundColor Green
Write-Host "  (remote clients need HTTPS — see upgrades-roadmap/remote-access.md)"
Write-Host ""

Push-Location $root
try {
    python -m uvicorn gsa_wrap.api:app --host $Bind --port $Port
} finally {
    Pop-Location
}
