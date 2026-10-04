param(
    [string]$TestDatabaseUrl,
    [string]$TestRedisUrl,
    [string]$TestBuildCaFile,
    [string]$ContainerNetwork,
    [string]$Image = 'vigil-api'
)

$ErrorActionPreference = 'Stop'
$env:VIGIL_TEST_DATABASE_URL = $TestDatabaseUrl
$env:VIGIL_TEST_REDIS_URL = $TestRedisUrl
$runnerArguments = @('run', '--system-certs', '--frozen', 'python', (Join-Path $PSScriptRoot 'verify_backend_container.py'), '--image', $Image)
if ($TestBuildCaFile) { $runnerArguments += @('--ca-file', $TestBuildCaFile) }
if ($ContainerNetwork) { $runnerArguments += @('--network', $ContainerNetwork) }
& uv @runnerArguments
if ($LASTEXITCODE -ne 0) { throw "Testes backend no container falharam (exit $LASTEXITCODE)." }
