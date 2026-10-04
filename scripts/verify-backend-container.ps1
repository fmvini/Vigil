param(
    [string]$TestDatabaseUrl,
    [string]$TestRedisUrl,
    [string]$TestBuildCaFile,
    [string]$Image = 'vigil-api'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot 'backend'
$reportPath = Join-Path $projectRoot '.cache\verification'
New-Item -ItemType Directory -Path $reportPath -Force | Out-Null
# Published loopback services remain untouched; the temporary container uses
# Docker Desktop's host gateway. Test schemas/Redis streams remain isolated.
$databaseUrl = $TestDatabaseUrl -replace '@(127\.0\.0\.1|localhost):', '@host.docker.internal:'
$redisUrl = $TestRedisUrl -replace '://(127\.0\.0\.1|localhost):', '://host.docker.internal:'
$dockerArguments = @(
    'run', '--rm',
    '--mount', "type=bind,source=$backendPath,target=/verification,readonly",
    '--mount', "type=bind,source=$reportPath,target=/reports",
    '-w', '/verification',
    '-e', 'UV_PROJECT_ENVIRONMENT=/app/.venv',
    '-e', 'PYTHONDONTWRITEBYTECODE=1',
    '-e', "VIGIL_TEST_DATABASE_URL=$databaseUrl",
    '-e', "VIGIL_TEST_REDIS_URL=$redisUrl"
)
if ($TestBuildCaFile) {
    $caPath = (Resolve-Path -LiteralPath $TestBuildCaFile).Path
    $dockerArguments += @('--mount', "type=bind,source=$caPath,target=/tmp/public-ca.pem,readonly")
}
# Dev dependencies follow uv.lock. Optional public CA is used only for package
# downloads in this disposable container, never in the monitoring transport.
$testCommand = @'
if [ -f /tmp/public-ca.pem ]; then
    cat /etc/ssl/certs/ca-certificates.crt /tmp/public-ca.pem > /tmp/test-ca.pem
    export SSL_CERT_FILE=/tmp/test-ca.pem
fi
uv sync --frozen --no-install-project
unset SSL_CERT_FILE
/app/.venv/bin/python -m pytest -q -ra -p no:cacheprovider --junitxml=/reports/backend.xml
'@
$dockerArguments += @($Image, 'sh', '-ec', $testCommand)
& docker @dockerArguments
if ($LASTEXITCODE -ne 0) { throw "Testes backend no container falharam (exit $LASTEXITCODE)." }
