# Push local secrets to GitHub Actions (run once from repo root).
# Requires: gh CLI logged in (gh auth login), repo pushed to GitHub.
#
# Usage:
#   .\scripts\setup_github_secrets.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

$config = Join-Path $Root "config.json"
$envFile = Join-Path $Root ".env"

if (-not (Test-Path $config)) {
    throw "config.json not found at $config"
}

Write-Host "Setting CONFIG_JSON from config.json..."
Get-Content -Raw -Encoding UTF8 $config | gh secret set CONFIG_JSON

if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { continue }
        $key, $_, $value = $line -split "=", 3
        $key = $key.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($key -in @("STAYAPI_API_KEY", "GMAIL_APP_PASSWORD") -and $value) {
            Write-Host "Setting $key..."
            $value | gh secret set $key
        }
    }
} else {
    Write-Host ".env not found — set STAYAPI_API_KEY and GMAIL_APP_PASSWORD manually:"
    Write-Host "  gh secret set STAYAPI_API_KEY"
    Write-Host "  gh secret set GMAIL_APP_PASSWORD"
}

Write-Host ""
Write-Host "Done. Verify at: GitHub repo -> Settings -> Secrets and variables -> Actions"
Write-Host "Trigger a test run: gh workflow run daily.yml"
