param([string]$Container = 'vigil-postgres-1')

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Instale as dependencias backend antes do ensaio.' }
if (!$env:VIGIL_BACKUP_DATABASE_URL) { throw 'Informe VIGIL_BACKUP_DATABASE_URL explicitamente (PG17 local/55433/vigil).' }
& $pythonPath (Join-Path $PSScriptRoot 'backup_restore_check.py') --container $Container
if ($LASTEXITCODE -ne 0) { throw 'Ensaio falhou ou cleanup ficou pendente; consulte o relatorio antes de repetir.' }
