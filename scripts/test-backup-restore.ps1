param(
    [string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin',
    [string]$HostName = '127.0.0.1',
    [int]$Port = 55432,
    [string]$UserName = 'vigil',
    [string]$Database = 'vigil',
    [string]$Password = $env:PGPASSWORD,
    [ValidateRange(1, 300)][int]$CleanupTimeoutSeconds = 15
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backupDirectory = Join-Path $projectRoot '.cache\backup-restore'
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$restoreDatabase = 'vigil_restore_test_' + [guid]::NewGuid().ToString('N')
$dumpPath = Join-Path $backupDirectory ($restoreDatabase + '.dump')
$oldPassword = $env:PGPASSWORD
$oldOptions = $env:PGOPTIONS
if (!$Password) { $Password = 'vigil_local_only' }
$env:PGPASSWORD = $Password
# Catalog queries do not require parallel workers; constrain this client's
# session only in Windows environments with restricted process creation.
$env:PGOPTIONS = '-c max_parallel_workers_per_gather=0 -c statement_timeout=30000 -c lock_timeout=5000'
$created = $false
$connectionArgs = @('-w', '-h', $HostName, '-p', "$Port", '-U', $UserName)

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou (exit $LASTEXITCODE)." }
}

function ConvertTo-NativeArgument([string]$Value) {
    # Start-Process joins ArgumentList on Windows. Quote each argument using
    # native argv rules, including quotes and trailing backslashes.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Remove-RestoreDatabase {
    $cleanup = $null
    try {
        $cleanupArguments = @($connectionArgs + $restoreDatabase | ForEach-Object {
            ConvertTo-NativeArgument $_
        })
        $cleanup = Start-Process -FilePath (Join-Path $PostgresBin 'dropdb.exe') `
            -ArgumentList $cleanupArguments -WindowStyle Hidden -PassThru
        if (!$cleanup.WaitForExit($CleanupTimeoutSeconds * 1000)) {
            # Only the client created here is stopped. Do not signal database
            # backends: a server-side DROP may still require operator review.
            $cleanup.Kill()
            $cleanup.WaitForExit(1000) | Out-Null
            Write-Warning "Cleanup excedeu ${CleanupTimeoutSeconds}s: $restoreDatabase pendente; inspecione pg_stat_activity antes de tentar novamente."
        } elseif ($cleanup.ExitCode -ne 0) {
            Write-Warning "Nao foi possivel remover banco temporario $restoreDatabase (exit $($cleanup.ExitCode))."
        }
    } catch {
        Write-Warning "Cleanup pendente para $restoreDatabase ($($_.Exception.GetType().Name))."
    } finally {
        if ($cleanup) { $cleanup.Dispose() }
    }
}

try {
    $sourceVersion = & (Join-Path $PostgresBin 'psql.exe') @connectionArgs -X -d $Database -At -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM public.alembic_version'
    Assert-NativeSuccess 'Leitura da migration de origem'
    # Apenas public: schemas efemeros dos testes concorrentes nao integram o backup runtime.
    & (Join-Path $PostgresBin 'pg_dump.exe') @connectionArgs -d $Database -Fc --schema=public --file=$dumpPath
    Assert-NativeSuccess 'Backup PostgreSQL'
    & (Join-Path $PostgresBin 'createdb.exe') @connectionArgs $restoreDatabase
    Assert-NativeSuccess 'Criacao de banco novo de restore'
    $created = $true
    & (Join-Path $PostgresBin 'pg_restore.exe') @connectionArgs -d $restoreDatabase --clean --if-exists --no-owner --no-privileges --exit-on-error $dumpPath
    Assert-NativeSuccess 'Restore PostgreSQL'
    $restoredVersion = & (Join-Path $PostgresBin 'psql.exe') @connectionArgs -X -d $restoreDatabase -At -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM public.alembic_version'
    Assert-NativeSuccess 'Leitura da migration restaurada'
    if ($sourceVersion -ne $restoredVersion) { throw 'Migration restaurada difere da origem.' }
    $counts = & (Join-Path $PostgresBin 'psql.exe') @connectionArgs -X -d $restoreDatabase -At -v ON_ERROR_STOP=1 -c "SELECT json_build_object('users',(SELECT count(*) FROM users),'projects',(SELECT count(*) FROM projects),'monitors',(SELECT count(*) FROM monitors),'jobs',(SELECT count(*) FROM check_jobs),'results',(SELECT count(*) FROM check_results),'incidents',(SELECT count(*) FROM incidents),'sessions',(SELECT count(*) FROM sessions))"
    Assert-NativeSuccess 'Verificacao das sete tabelas restauradas'
    Write-Output "Backup e restore verificados: migration $restoredVersion; contagens $counts"
    Write-Output "Dump local preservado: $dumpPath"
} finally {
    # O unico banco removido e o novo identificador aleatorio criado por este teste.
    if ($created -and $restoreDatabase -match '^vigil_restore_test_[a-f0-9]{32}$') {
        Remove-RestoreDatabase
    }
    $env:PGPASSWORD = $oldPassword
    $env:PGOPTIONS = $oldOptions
}
