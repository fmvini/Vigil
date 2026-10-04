param(
    [string]$TestDatabaseUrl = $env:VIGIL_TEST_DATABASE_URL,
    [string]$TestRedisUrl = $env:VIGIL_TEST_REDIS_URL,
    [switch]$RequireIntegration
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
if ($TestDatabaseUrl) { $env:VIGIL_TEST_DATABASE_URL = $TestDatabaseUrl }
if ($TestRedisUrl) { $env:VIGIL_TEST_REDIS_URL = $TestRedisUrl }
if ($RequireIntegration -and (!$TestDatabaseUrl -or !$TestRedisUrl)) {
    throw 'RequireIntegration exige TestDatabaseUrl e TestRedisUrl (ou VIGIL_TEST_DATABASE_URL e VIGIL_TEST_REDIS_URL).'
}
if (!$TestDatabaseUrl) { Write-Warning 'PostgreSQL real nao informado: testes dessa integracao serao ignorados.' }
if (!$TestRedisUrl) { Write-Warning 'Redis real nao informado: ACK/reclaim nao sera validado.' }

$reportDirectory = Join-Path $projectRoot '.cache\verification'
New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
$backendReport = Join-Path $reportDirectory 'backend.xml'

function Assert-CommandSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou (exit $LASTEXITCODE)." }
}

Push-Location (Join-Path $projectRoot 'backend')
try {
    uv run --system-certs --frozen pytest -q -ra -p no:cacheprovider "--junitxml=$backendReport"
    Assert-CommandSuccess 'Testes backend'
    if ($RequireIntegration) {
        [xml]$report = Get-Content -LiteralPath $backendReport -Raw
        # SQLite variants may skip PostgreSQL-only behavior. Real integrations
        # must execute: a supplied URL alone is not evidence of coverage.
        $integrationTests = @($report.SelectNodes('//testcase') | Where-Object {
            $_.name -notmatch '\[[^\]]*\bsqlite\b' -and (
                $_.classname -match '(test_db_postgresql|test_pipeline_db|test_retention|test_worker|test_publisher)' -or
                $_.name -match '(\[[^\]]*\bpostgres\b|test_real_redis_)'
            )
        })
        if (!$integrationTests.Count) { throw 'Nenhum teste de integracao encontrado no relatorio backend.' }
        if (!@($integrationTests | Where-Object { $_.name -match 'test_real_redis_' }).Count) {
            throw 'Teste real Redis ACK/reclaim ausente no relatorio backend.'
        }
        if (!@($integrationTests | Where-Object { $_.classname -match 'test_db_postgresql' }).Count) {
            throw 'Testes reais PostgreSQL ausentes no relatorio backend.'
        }
        $skippedIntegrations = @($integrationTests | Where-Object { $_.SelectSingleNode('skipped') })
        if ($skippedIntegrations.Count) {
            $names = ($skippedIntegrations | ForEach-Object { $_.name }) -join ', '
            throw "Integracoes obrigatorias ignoradas: $names"
        }
    }
    uv run --system-certs --frozen ruff check app tests
    Assert-CommandSuccess 'Lint backend'
} finally { Pop-Location }

Push-Location (Join-Path $projectRoot 'frontend')
try {
    npm.cmd run test
    Assert-CommandSuccess 'Testes frontend'
    npm.cmd run build
    Assert-CommandSuccess 'Build frontend e TypeScript'
} finally { Pop-Location }

Push-Location $projectRoot
try {
    docker compose --profile app config --quiet
    Assert-CommandSuccess 'Configuracao Compose'
    git diff --check
    Assert-CommandSuccess 'Verificacao de whitespace'
} finally { Pop-Location }

Write-Output "Verificacoes concluidas. Relatorio backend: $backendReport"
if (!$RequireIntegration) {
    Write-Output 'Modo parcial: consulte os skips; use -RequireIntegration para exigir PostgreSQL/Redis reais.'
}
