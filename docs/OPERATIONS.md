# Operação local e critérios de liberação

O PostgreSQL é a fonte de verdade. API, scheduler/publicador e worker são processos separados. A API pode servir cadastros e consultas com o pipeline desabilitado; isso não comprova execução de verificações externas.

## Verificação

Após instalar dependências, execute na raiz:

```powershell
./scripts/verify.ps1 -TestDatabaseUrl 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil'
```

O comando executa pytest, Ruff, testes/build frontend, validação Compose e whitespace. Preserva relatório JUnit em `.cache/verification/backend.xml` e mostra motivos dos skips. Sem URLs de integração, informa explicitamente as verificações ausentes.

Para exigir PostgreSQL e Redis reais:

```powershell
./scripts/verify.ps1 -RequireIntegration `
  -TestDatabaseUrl $env:VIGIL_TEST_DATABASE_URL `
  -TestRedisUrl $env:VIGIL_TEST_REDIS_URL
```

Esse modo recusa URLs ausentes e testes de integração ignorados. Skips das variantes SQLite que exigem recursos PostgreSQL são esperados. Use um ambiente local isolado: os testes criam schemas PostgreSQL e streams Redis de nomes aleatórios; não devem ser apontados para produção.

Na sessão Windows de 2026-10-04, uma consulta de catálogo do SQLAlchemy ficou em `IPC/MessageQueueInternal` com plano paralelo. O cluster local recebeu `ALTER ROLE vigil IN DATABASE vigil SET max_parallel_workers_per_gather=0`; novas conexões dessa combinação passaram a usar plano serial, e a consulta terminou em 0,105s. A configuração também vale para novos pools API dessa role/banco; outras bases e conexões já abertas não mudaram. É um ajuste do cluster local, não uma migration ou requisito de produção. Para reverter quando o ambiente suportar paralelismo, usar `ALTER ROLE vigil IN DATABASE vigil RESET max_parallel_workers_per_gather`. A causa exata do bloqueio de IPC não foi comprovada; a consulta anterior PID 1968 foi preservada sem sinais e continua pendente de diagnóstico operacional.

Para reproduzir o smoke com API/Vite/PostgreSQL ativos e Edge instalado, executar em `frontend/`: `npm.cmd run test:browser` e `npm.cmd run test:live`. Criam contas/projetos locais de QA. O segundo valida SSE e consultas REST reais, reconciliação após mutação externa à aba, snapshot periódico e revogação. Relatórios/capturas ficam em `.impeccable/review/`, excluídos de Git/Docker.

## Retenção

Com as migrations aplicadas e uma URL PostgreSQL explícita:

```powershell
./scripts/run-retention.ps1 -DatabaseUrl $env:VIGIL_DATABASE_URL
```

Por padrão, executa um lote de até 100 registros por entidade e desfaz a transação. A saída JSON informa `committed=false` e contagens elegíveis; esse preview adquire locks breves e não promete que uma execução posterior encontrará as mesmas linhas.

Para aplicar a limpeza já revisada:

```powershell
./scripts/run-retention.ps1 -DatabaseUrl $env:VIGIL_DATABASE_URL -Apply -BatchSize 100 -MaxBatches 10
```

Cada lote tem commit separado, `lock_timeout=1s` e `statement_timeout=10s`. Resultados/jobs terminais são retidos por 30 dias, incidentes fechados por 90 dias e sessões por sete dias após invalidação. Jobs ativos, incidentes abertos e snapshots dos monitores permanecem. Evidências de resultados removidos tornam-se nulas nos incidentes. Se um lote falhar, lotes anteriores já confirmados permanecem; o lote atual é revertido. Execute em processo dedicado, sem vincular à inicialização de cada réplica API.

## Backup e restauração

```powershell
./scripts/test-backup-restore.ps1
```

O script usa o PostgreSQL 18 local na porta 55432 por padrão. Ajuste `PostgresBin`, `HostName`, `Port`, `UserName`, `Database` e `Password` para outro ambiente. Faz backup somente do schema `public`, restaura em um banco novo com nome aleatório, verifica a revisão Alembic e consulta as sete tabelas; remove apenas esse banco temporário. O dump permanece em `.cache/backup-restore/` e contém dados privados. Essa prova não compara cada linha com a origem nem demonstra recuperação operacional completa.

O cliente de cleanup tem limite externo de 15 segundos (`CleanupTimeoutSeconds`). Se exceder esse limite, o script encerra apenas seu cliente `dropdb` e informa o banco pendente; isso não confirma cancelamento do `DROP` no servidor. Inspecione `pg_stat_activity` antes de repetir a remoção. Na sessão Windows de 2026-10-04, o restore foi verificado, mas seu cleanup ficou em `IPC/ProcSignalBarrier`; nenhum walwriter ou processo do servidor foi encerrado. Uma advertência de cleanup precisa ser resolvida operacionalmente mesmo que a validação do dump tenha passado.

## Pipeline

`VIGIL_PIPELINE_ENABLED` e `VIGIL_MONITORING_NETWORK_ENABLED` permanecem `false` por padrão. Antes de habilitar execução externa, validar ACK/reclaim no Redis real, TLS/SNI/IPv6 com sockets reais em ambiente controlado, controles de egress e recuperação operacional.

Com esses critérios atendidos no ambiente isolado, os comandos implementados são:

```powershell
cd backend
uv run --frozen python -m app.monitoring.run
uv run --frozen taskiq worker app.monitoring.tasks:broker --workers 1 --max-async-tasks 50 --max-prefetch 50 --ack-type manual
```

São processos de longa duração em terminais separados. As flags devem ser configuradas explicitamente nesse ambiente. Testes determinísticos do transporte e mocks do broker não substituem as provas reais acima.
