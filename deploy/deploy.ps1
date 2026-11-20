<#
  Deploy Wall of Text from a Windows PC to the Pi over SSH (BUILD_PLAN override 10).

  Usage (PowerShell, from the repo root):
    .\deploy\deploy.ps1                         # update code, keep Wi-Fi/passwords/data
    .\deploy\deploy.ps1 -PiHost 192.168.1.40    # if walloftext.local doesn't resolve
    .\deploy\deploy.ps1 -Full                   # first install (needs Ethernet on the Pi)

  Needs: OpenSSH client (built into Windows 10/11) and tar.exe (also built in).
  If frontend/package.json exists and npm is installed, the frontend is built first.
#>
param(
  [string]$PiHost = "walloftext.local",
  [string]$User = "pi",
  [switch]$Full
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ((Test-Path "frontend/package.json") -and (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Host "== Building frontend"
  Push-Location frontend
  npm ci
  npm run build
  Pop-Location
}

$archive = Join-Path $env:TEMP "walloftext-deploy.tgz"
Write-Host "== Packing"
tar -czf $archive --exclude=.git --exclude=.venv --exclude=node_modules --exclude=backend/var --exclude=__pycache__ .

$target = "$User@$PiHost"
Write-Host "== Copying to $target"
scp $archive "${target}:/tmp/walloftext-deploy.tgz"

$mode = if ($Full) { "" } else { "--update" }
Write-Host "== Installing on the Pi (you may be asked for your sudo password)"
ssh -t $target "rm -rf ~/walloftext-src && mkdir -p ~/walloftext-src && tar -xzf /tmp/walloftext-deploy.tgz -C ~/walloftext-src && sudo bash ~/walloftext-src/deploy/install.sh $mode"

Remove-Item $archive
Write-Host "== Done: http://$PiHost/"
