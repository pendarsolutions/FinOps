# Windows equivalent of the Makefile targets.
#   .\scripts\finops.ps1 dev | install | seed-pricing | seed-demo | sync-prices | test | lint | api | web
param([Parameter(Mandatory = $true)][string]$Target)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = "packages;apps/api;apps/worker"
$py = Join-Path $root ".venv\Scripts\python.exe"

function Cli([string[]]$a) { & $py -m finops_api.cli @a; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }

switch ($Target) {
  "dev"          { docker compose up --build }
  "install"      { python -m venv .venv; & $py -m pip install -r requirements-dev.txt; Push-Location apps/web; npm install; Pop-Location }
  "migrate"      { Cli @("migrate") }
  "seed-pricing" { Cli @("migrate"); Cli @("seed-pricing") }
  "seed-demo"    { Cli @("migrate"); Cli @("seed-pricing"); Cli @("seed-demo-user") }
  "sync-prices"  { Cli @("sync-prices") }
  "purge-uploads"{ Cli @("purge-uploads") }
  "test"         { & $py -m pytest -q; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; Push-Location apps/web; npm run typecheck; Pop-Location }
  "lint"         { & $py -m ruff check packages apps/api apps/worker tests }
  "api"          { Cli @("migrate"); Cli @("seed-pricing"); Cli @("seed-demo-user"); & $py -m uvicorn finops_api.main:app --reload --port 8000 }
  "web"          { Push-Location apps/web; npm run dev; Pop-Location }
  default        { Write-Error "unknown target $Target" }
}
