param(
    [ValidateSet('api', 'frontend')][string]$Component = 'api',
    [string]$DatabaseUrl = $env:VIGIL_DATABASE_URL,
    [switch]$Migrate,
    [switch]$Preview
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
if ($Preview -and $Component -ne 'frontend') {
    throw 'Preview so pode ser usado com o componente frontend.'
}

if ($Component -eq 'api') {
    if (!$DatabaseUrl) {
        $DatabaseUrl = 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:5432/vigil'
    }
    $env:VIGIL_DATABASE_URL = $DatabaseUrl
    $env:VIGIL_ENVIRONMENT = 'dev'
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        if (!(Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
            uv sync --system-certs --frozen --python 3.13
            if ($LASTEXITCODE -ne 0) { throw 'Instalacao das dependencias Python falhou.' }
        }
        if ($Migrate) {
            uv run --frozen --no-sync alembic upgrade head
            if ($LASTEXITCODE -ne 0) { throw 'Migration falhou; API nao sera iniciada.' }
        }
        # Sem reload: evita multiprocessing/named pipes em ambientes Windows restritos.
        uv run --frozen --no-sync uvicorn app.main:app --host 127.0.0.1 --port 8000
        if ($LASTEXITCODE -ne 0) { throw 'API encerrou com erro.' }
    } finally { Pop-Location }
} else {
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        $env:NODE_USE_SYSTEM_CA = '1'
        if (!(Test-Path -LiteralPath 'node_modules/vite')) {
            npm.cmd ci --cache .npm-cache --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'Instalacao das dependencias JavaScript falhou.' }
        }
        if ($Preview) {
            if (!(Test-Path -LiteralPath 'dist/index.html' -PathType Leaf)) {
                throw 'Build frontend ausente. Execute npm.cmd run build em frontend antes do Preview.'
            }
            Write-Output 'Servindo o build existente, sem recompilacao ou hot reload.'
            # Node 24 carrega a configuracao TypeScript sem bundling via esbuild.
            node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort --configLoader native
        } else {
            npm.cmd run dev
        }
        if ($LASTEXITCODE -ne 0) { throw 'Frontend encerrou com erro.' }
    } finally { Pop-Location }
}
