param(
    [string]$DatabaseUrl = $env:VIGIL_DATABASE_URL,
    [ValidateRange(1, 1000)][int]$BatchSize = 100,
    [ValidateRange(1, 1000)][int]$MaxBatches = 1,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
if (!$DatabaseUrl) { throw 'Informe DatabaseUrl ou VIGIL_DATABASE_URL explicitamente.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
$previousDatabaseUrl = $env:VIGIL_DATABASE_URL
$env:VIGIL_DATABASE_URL = $DatabaseUrl
$arguments = @(
    'run', '--frozen', '--no-sync', 'python', '-m', 'app.services.retention',
    'run-retention', '--batch-size', "$BatchSize", '--max-batches', "$MaxBatches"
)
# Preview is the default; the Python CLI executes a single batch and rolls back.
if (!$Apply) { $arguments += '--dry-run' }

Push-Location (Join-Path $projectRoot 'backend')
try {
    & uv @arguments
    if ($LASTEXITCODE -ne 0) { throw "Retencao falhou (exit $LASTEXITCODE)." }
} finally {
    Pop-Location
    $env:VIGIL_DATABASE_URL = $previousDatabaseUrl
}
