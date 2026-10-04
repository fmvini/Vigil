# Persistência Vigil — 2026-10-04

## 2026-10-04 — Retenção revisada no PostgreSQL real

### Implementado
- Revisados `backend/app/services/retention.py` e `backend/tests/test_retention.py`; implementação existente validada, sem alteração de código ou testes nesta revisão.
- Retenção estritamente anterior ao cutoff: resultados concluídos e jobs terminais há mais de 30 dias, incidentes encerrados há mais de 90 dias e sessões inválidas há mais de 7 dias. Inatividade usa `session_idle_seconds`; timestamps exatamente na fronteira permanecem.
- Resultados são removidos antes dos jobs; jobs ainda referenciados e jobs pending/running permanecem. Evidências de incidentes abertos/fechados passam a NULL pelas FKs, sem alterar snapshots de Monitor ou Project.
- Lotes limitados por entidade, seleção com `FOR UPDATE SKIP LOCKED` e locks antecipados das evidências evitam esperar linhas ocupadas. Caller controla a transação; o serviço não faz commit.
- CLI explícita `run-retention` exige `VIGIL_DATABASE_URL`, limita tamanho/quantidade dos lotes e configura timeouts locais de lock/statement. `--dry-run` executa e reverte somente um lote; erros não imprimem credenciais.

### Arquivos principais alterados
- `backend/app/db/IMPLEMENTATION.md` (registro desta validação).
- Arquivos somente revisados/verificados: `backend/app/services/retention.py`, `backend/tests/test_retention.py`.

### Decisões técnicas
- Mantida a implementação pronta, conforme pedido de apenas validar quando não houver correção necessária.
- Testes reais usam schemas aleatórios próprios e aplicam upgrade/downgrade da migration; nenhuma limpeza de retenção foi aplicada às tabelas do runtime.
- Retomado o cluster existente `.cache/postgresql/data` com `backend/.venv/Scripts/python.exe` e `subprocess.Popen` de `C:/Program Files/PostgreSQL/18/bin/postgres.exe -D <caminho absoluto do cluster> -h 127.0.0.1 -p 55432`, usando `subprocess.CREATE_NO_WINDOW` e stdout/stderr em `.cache/postgresql/python-server.log`. Não houve initdb, remoção de PID ou exclusão de dados. O PostgreSQL fez recovery automático do encerramento anterior.

### Estado atual
- **29 passed, sem skips, em 24.24s**: de `backend/`, com `VIGIL_TEST_DATABASE_URL` apontando para o cluster 55432, executar `.venv/Scripts/python.exe -m pytest tests/test_retention.py -q -p no:cacheprovider --tb=short`.
- Ruff check e format check dos dois arquivos passaram. `alembic upgrade head` e `alembic current` confirmaram runtime em `0001_initial (head)`; `pg_isready` confirmou accepting connections em `127.0.0.1:55432`, PostgreSQL 18.6, PID de início 2704.
- Evidências incluem quatro entidades com linhas ocupadas, evidência de incidente bloqueada, dois janitors com transações sobrepostas/lotes distintos, atividade de sessão concorrente, rollback restaurando linhas e ambas as evidências, dry-run real e commits em múltiplos lotes.
- Primeira tentativa encontrou PG fechado e falhou em setup por connection refused; foi repetida integralmente após a retomada do cluster. Resultado válido é a rodada de 29 passed acima.
- Limitações: dry-run informa apenas um lote, não o total do backlog. Um lote vazio pode ocorrer por locks e requer rodada futura. Fanout de evidências acima de `2 * batch_size` pode adiar resultados até aumentar o lote/corrigir histórico. Não foram medidos volume/planos de consulta de produção nem validado PostgreSQL 17 nesta revisão. API/Vite não foram iniciados por esta área.

### Próximos passos
- Maestro consolida as evidências em docs de progresso/operação e centraliza Git; não houve edição de infra, docs raiz ou Git nesta revisão.
- Antes de operar retenção no runtime, usar a CLI explícita com banco configurado e dry-run; definir execução supervisionada periódica para revisitar linhas puladas por locks.
- Ensaiar retenção no PostgreSQL 17 do Compose e medir planos/latência com volume representativo, sobretudo scans das FKs de evidências e limpeza de sessões.

## Base concluída

- `base.py`: metadata nomeada, UUIDs Python `uuid4`, auditoria `timestamptz`.
- `models.py`: User, Session, Project, Monitor, CheckJob, CheckResult e Incident, com todos os campos de `docs/DATABASE.md`.
- `session.py`: engine `postgresql+asyncpg`, pool limitado 5+5, pre-ping; `create_session_factory(engine)` com `expire_on_commit=False`. Sem singleton, criação de schema ou conexão no import. API fornece `Settings.database_url` (`VIGIL_DATABASE_URL`). Uma sessão por request/task; caller controla commit/rollback/dispose.
- SQLite `sqlite+aiosqlite` requer `allow_sqlite_for_tests=True`, habilita FKs e existe exclusivamente para testes unitários/API. Alembic rejeita SQLite, inclusive offline.
- `backend/alembic.ini`, `backend/migrations/env.py`, `script.py.mako`, `versions/0001_initial.py`: revisão congelada independente dos modelos futuros, upgrade/downgrade online async e SQL offline.
- `backend/tests/test_db_schema.py` e `test_db_postgresql.py`: 37 testes passando, sem skips, em PostgreSQL **18.6 real** e SQLAlchemy 2.0.54/Alembic 1.20.0/asyncpg 0.31.0. Os scripts SQL offline de upgrade/downgrade também foram executados no PostgreSQL e comparados à metadata. SQLite só verifica defaults/factory, não comprova PostgreSQL.

## Integridade e decisões

- CHECKs: normalização/uniqueness do e-mail, enumerações, limites RN004–RN006, contadores, leases, estados finais, ordenação temporal e sucesso com status/latência medidos.
- Índices parciais: projeto ativo por owner, monitores agendáveis, um job pending/running por monitor, publicação/retry pending, lease running, expiração de jobs abertos, um incidente aberto por monitor. Histórico e retenção indexados.
- FK composta `CheckResult(job_id, monitor_id, config_version, scheduled_at)` → identidade completa de CheckJob impede cruzamento de monitor, versão e slot; `job_id` único impede duplicação do resultado. Jobs referenciados não são apagados antes dos resultados.
- Evidências de Incident usam `ON DELETE SET NULL`; testes confirmam preservação do incidente e limpeza resultado→job. Histórico não sofre cascade ao apagar monitor/projeto.
- JSONB em PostgreSQL, JSON em SQLite de testes. Validação/sanitização do conteúdo e imutabilidade de snapshot/resultado são responsabilidade dos serviços. Sem índices JSON indiscriminados ou enums PG difíceis de evoluir.
- Não há relacionamentos ORM com lazy loading; serviços consultam explicitamente as FKs. `updated_at` é atualizado por SQLAlchemy; SQL bruto precisa atualizar auditoria explicitamente.
- Testes PG criam schemas `vigil_test_<uuid>` isolados, aplicam migration, verificam metadata/tipos, executam constraints e removem o schema. Concorrência prova bloqueio por `pg_blocking_pids` e rejeição do segundo insert após commit.

## Ambiente local de integração

Servidor padrão `5432` aceita conexões, mas exige credenciais indisponíveis. Docker daemon indisponível. Foi autorizado e criado cluster isolado em `.cache/postgresql/data`, escutando **somente 127.0.0.1:55432**, com credenciais locais de desenvolvimento:

```powershell
$env:VIGIL_DATABASE_URL = "postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil"
$env:VIGIL_TEST_DATABASE_URL = $env:VIGIL_DATABASE_URL
```

Cluster permanece ativo para Backend/Maestro. Não usa nem altera dados do servidor padrão. O diretório `.cache/` deve permanecer ignorado pelo Git (Maestro cuida da infra).

Start reproduzível, na raiz do projeto, para o cluster já inicializado (o `pg_ctl start` falhou ao criar restricted token neste sandbox; `Start-Process` também falhou por duplicação Path/PATH):

```powershell
python -c "import subprocess,pathlib; d=pathlib.Path('.cache/postgresql/data').resolve(); log=pathlib.Path('.cache/postgresql/python-server.log').open('ab'); subprocess.Popen(['C:/Program Files/PostgreSQL/18/bin/postgres.exe','-D',str(d),'-h','127.0.0.1','-p','55432'],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)"
& "C:/Program Files/PostgreSQL/18/bin/pg_isready.exe" -h 127.0.0.1 -p 55432
```

Stop:

```powershell
& "C:/Program Files/PostgreSQL/18/bin/pg_ctl.exe" -D .cache/postgresql/data -m fast -w stop
```

Migration e testes, de `backend/`, depois do sync do Backend:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic upgrade head --sql
.venv/Scripts/python.exe -m pytest tests/test_db_schema.py tests/test_db_postgresql.py -q
```

Sem `VIGIL_TEST_DATABASE_URL`, testes PostgreSQL reportam skip explícito; falha de conexão de URL configurada falha o teste. Não substituir por SQLite.

## Fontes verificadas

- [SQLAlchemy 2.0 async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html): factories/AsyncSession e ciclo de vida.
- [Constraints e índices SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/constraints.html): FK composta e índices nomeados.
- [Alembic SQL offline](https://alembic.sqlalchemy.org/en/latest/offline.html): geração upgrade/downgrade sem conexão.

## Pipeline DB concluído

Propriedade ampliada explicitamente pelo Maestro para `backend/app/services/check_jobs.py`, `backend/app/monitoring/scheduler.py`, `backend/tests/test_pipeline_db.py`.

- `schedule_due(db, now=None, limit=100)` bloqueia monitores ativos com `FOR UPDATE OF monitors SKIP LOCKED`, escolhe o slot vencido mais recente, contabiliza `skipped_slots`, congela configuração, calcula orçamento com a função compartilhada `app.domain.monitors.cycle_budget_ms` e avança agenda junto com o job. Não gera rajadas de slots antigos. Expira/cancela job anterior inválido antes de liberar o índice único parcial.
- `claim_job(db, job_id, now=None, lease_seconds=90)` revalida projeto/monitor/versão, retry/prazo/orçamento e dono do lease; retorna `ClaimedJob` ou `None`. Nova execução técnica recebe token UUID novo, inicia contador e copia snapshot. Só pending/reexecução precisa de orçamento completo; running válido pode finalizar perto do prazo sem ser invalidado por uma entrega duplicada.
- `finalize_job(db, job_id, lease_token, result, now=None)` revalida token/prazo/versão, valida resultado e resumo sanitizado, grava CheckResult único, aplica `app.domain.health.apply_evaluated_cycle`, abre/encerra incidente, altera snapshot, incrementa Project.revision e conclui job atomicamente. Retorna True apenas ao aplicar; duplicado/rejeitado retorna False. Resultado anterior nunca é reaplicado.
- `record_job_error(db, job_id, lease_token, error_code, now=None)` e `reconcile_jobs(db, now=None, limit=100)` cancelam trabalho inválido, expiram sem orçamento/prazo e recuperam leases expirados. Retry técnico após 1s/2s, máximo 3 execuções. Reexecução transitória ainda elegível preserva sequência de falhas; exclusão final interrompe a sequência, preserva saúde offline/incidente e não cria resultado failure.
- `monitoring/scheduler.py`: `scheduler_tick(factory)` executa reconciliação/agenda; `run_scheduler(factory, stop, tick_seconds=1)` oferece loop dedicado, fora do startup da API. Falhas DB propagam ao supervisor. Sem Redis, HTTP ou dependência de infraestrutura/configuração neste módulo.
- Produção usa `clock_timestamp()` PostgreSQL **após adquirir os locks**; `now` explícito existe para testes determinísticos. Ordem de locks dos serviços: Project → Monitor → CheckJob → evidência/Incident. Scheduler bloqueia Monitor → CheckJob sem atualizar Project; não cria inversão de locks.
- Todas as funções fazem flush **sem commit**. Caller usa `factory.begin()`, deixa a transação encerrar antes do HTTP/publicação e só sinaliza/ACK após commit. Engine/sessão nunca são compartilhados entre tarefas concorrentes.

### Contrato acordado com Backend

Imports: `app.services.check_jobs.ClaimedJob`, `EvaluatedCycle`, `claim_job`, `finalize_job`, `record_job_error`, `reconcile_jobs`, `schedule_due`.

`ClaimedJob`: `job_id`, `monitor_id`, `config_version`, `lease_token`, `lease_expires_at`, `scheduled_at`, `expires_at`, `budget_ms`, `config_snapshot`, `started_at`.

`EvaluatedCycle`: `started_at: datetime`, `completed_at: datetime`, `outcome: str`, `http_status: int | None`, `latency_ms: float | None`, `cycle_duration_ms: float`, `attempt_count: int`, `attempts: list[dict]`, `error_code: str | None = None`.

`queue_delay_ms` é derivado de `started_at - scheduled_at`. `attempts` só aceita `http_status`, `error_code`, `latency_ms`, `duration_ms`, com tamanho igual a `attempt_count`; URL/body/headers/erro bruto são rejeitados. Sucesso exige status esperado e latência medida. Erros do alvo: timeout/dns_error/connection_error/tls_error/unexpected_status. Erros técnicos aceitos: internal_error/execution_crashed/pool_exhausted/blocked_destination/database_error.

### Validação final

- **61 passed, sem skips** em `test_db_schema.py`, `test_db_postgresql.py`, `test_pipeline_db.py`: 37 base/migrations + 24 pipeline.
- Concorrência real: índices parciais de job/incidente bloqueiam segundo insert e o rejeitam após commit; segundo scheduler pula monitor bloqueado; claims/finalizações simultâneos produzem um efeito.
- Reentrega, rollback antes do commit, token de lease vencido/antigo, retry/exhaustão sem amostra falsa, pausa/edição usando os serviços reais da API, slot atrasado, recuperação degradada com incidente encerrado e sanitização de resultados cobertos.
- Suíte integrada observada: **183 passed, 2 skipped**, em 54.14s. Skips somente variantes SQLite de testes concorrentes da API; nenhum teste PostgreSQL foi substituído por SQLite.
- Ruff check/format dos arquivos atribuídos passou; Alembic `upgrade head`/`current` verificaram `0001_initial (head)` no cluster de desenvolvimento. Schemas temporários dos testes removidos; cluster permanece ativo para integração.

## Limitações e próximos passos

- Redis/publicador/worker/transporte HTTP pertencem ao Backend e não foram implementados nesta entrega. O pipeline DB isolado não comprova ACK/reclaim de Redis, recuperação de broker, SSRF na conexão, throughput ou latência de produção.
- IDs e leases oferecem um efeito persistido por ciclo; não prometem apenas uma chamada GET física quando um executor cai. O resumo registra as tentativas da execução técnica que efetivamente finalizou.
- Snapshot JSON e resultados devem ser alterados exclusivamente pelos serviços; não há trigger de imutabilidade para SQL bruto. Autorização e cancelamento/reset administrativo são dos serviços API já integrados.
- Backend deve ligar publicação dos pending elegíveis (`retry_at` nulo/vencido e `published_at` ausente/antigo), executar claim → HTTP sem transação → finalize/record em transação nova e emitir sinais/ACK após commit. Ensaiar commit antes/depois do ACK, lease perdido e reconciliação após indisponibilidade Redis.
- Manter o loop DB em processo dedicado; não iniciá-lo em cada réplica FastAPI. Definir recuperação supervisionada e retenção por lotes antes de produção.
- Validar a migration também no PostgreSQL 17.11 do Compose quando Docker ficar disponível; esta entrega comprovou PostgreSQL 18.6 real, não executou Docker nem PostgreSQL 17.
- Maestro consolida `docs/DEVELOPMENT_LOG.md` e commits. Não editei docs/infra/pyproject/uv.lock nem Git, conforme divisão de propriedade/autorização.
