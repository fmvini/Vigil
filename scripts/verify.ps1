param(
    [string]$TestDatabaseUrl = $env:VIGIL_TEST_DATABASE_URL,
    [string]$TestRedisUrl = $env:VIGIL_TEST_REDIS_URL,
    [switch]$RequireIntegration,
    [switch]$BackendContainer,
    [string]$ContainerNetwork,
    [string]$TestBuildCaFile
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($TestBuildCaFile) { $TestBuildCaFile = (Resolve-Path -LiteralPath $TestBuildCaFile).Path }
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
$scriptsReport = Join-Path $reportDirectory 'scripts.xml'

function Assert-CommandSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou (exit $LASTEXITCODE)." }
}

Push-Location (Join-Path $projectRoot 'backend')
try {
    if ($BackendContainer) {
        & (Join-Path $PSScriptRoot 'verify-backend-container.ps1') -TestDatabaseUrl $TestDatabaseUrl -TestRedisUrl $TestRedisUrl -TestBuildCaFile $TestBuildCaFile -ContainerNetwork $ContainerNetwork
    } else {
        uv run --system-certs --frozen pytest -q -ra -p no:cacheprovider "--junitxml=$backendReport"
    }
    Assert-CommandSuccess 'Testes backend'
    if ($RequireIntegration) {
        [xml]$report = Get-Content -LiteralPath $backendReport -Raw
        # SQLite variants may skip PostgreSQL-only behavior. Real integrations
        # must execute: a supplied URL alone is not evidence of coverage.
        $integrationTests = @($report.SelectNodes('//testcase') | Where-Object {
            $_.name -notmatch '\[[^\]]*\bsqlite\b' -and (
                $_.classname -match '(test_db_postgresql|test_db_qa_seed|test_pipeline_db|test_retention|test_worker|test_publisher|test_broker_integration|test_events_redis|test_events_tcp|test_transport_sockets|test_api_replicas)' -or
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
        foreach ($module in @('test_broker_integration', 'test_events_redis', 'test_events_tcp', 'test_transport_sockets', 'test_worker_process_recovery', 'test_api_replicas')) {
            if (!@($integrationTests | Where-Object { $_.classname -match $module }).Count) {
                throw "Testes de integracao ausentes no relatorio backend: $module"
            }
        }
        $skippedIntegrations = @($integrationTests | Where-Object { $_.SelectSingleNode('skipped') })
        if ($skippedIntegrations.Count) {
            $names = ($skippedIntegrations | ForEach-Object { $_.name }) -join ', '
            throw "Integracoes obrigatorias ignoradas: $names"
        }
    }
    uv run --system-certs --frozen ruff check --config pyproject.toml app tests ../scripts/backup_restore_check.py ../scripts/egress_check.py ../scripts/verify_backend_container.py ../scripts/tests ../infra/worker
    Assert-CommandSuccess 'Lint backend'
    uv run --system-certs --frozen pytest ../scripts/tests -c pyproject.toml -q -ra -p no:cacheprovider "--junitxml=$scriptsReport"
    Assert-CommandSuccess 'Testes de tooling operacional'
    if ($RequireIntegration) {
        [xml]$toolingReport = Get-Content -LiteralPath $scriptsReport -Raw
        $snapshotTests = @($toolingReport.SelectNodes('//testcase') | Where-Object { $_.name -match '^test_real_(digest|exported_snapshot)' })
        if ($snapshotTests.Count -ne 2 -or @($snapshotTests | Where-Object { $_.SelectSingleNode('skipped') }).Count) {
            throw 'Provas obrigatorias de conteudo/snapshot PostgreSQL do tooling ausentes ou ignoradas.'
        }
        $browserTests = @($toolingReport.SelectNodes('//testcase') | Where-Object { $_.name -eq 'test_real_native_browser_reconnect_recovers_gap_and_replacement' })
        if ($browserTests.Count -ne 1 -or @($browserTests | Where-Object { $_.SelectSingleNode('skipped') }).Count) {
            throw 'Prova obrigatoria de reconexao EventSource no navegador ausente ou ignorada (Node/Playwright/Edge requeridos).'
        }
        uv run --system-certs --frozen python ../scripts/egress_check.py --build
        Assert-CommandSuccess 'Firewall fisico IPv4/IPv6 e privilegios do worker'
    }
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
    docker compose -f compose.yaml -f compose.worker.yaml --profile app --profile workers config --quiet
    Assert-CommandSuccess 'Configuracao opt-in de worker protegido'
    git diff --check
    Assert-CommandSuccess 'Verificacao de whitespace'
} finally { Pop-Location }

Write-Output "Verificacoes concluidas. Relatorio backend: $backendReport"
Write-Output "Relatorio tooling operacional: $scriptsReport"
if (!$RequireIntegration) {
    Write-Output 'Modo parcial: consulte os skips; use -RequireIntegration para exigir PostgreSQL/Redis reais.'
}
