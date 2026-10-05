# Persistência Vigil — 2026-10-04

## 2026-10-05 — Seed QA recusa diretório inválido antes de acessar banco

### Implementado
- Movida a criação/validação do diretório pai do manifesto para antes de `create_engine` em `run_seed`. Um pai que é arquivo ou cuja criação falha é recusado antes de conexão/transação, evitando commits de fixture para esse erro determinístico.
- Adicionada regressão usando `pyproject.toml` como pai inválido, sem temporários/PG; a criação de engine é proibida. Provas controladas de erro/CancelledError confirmam saída da transação por rollback, dispose e ausência de escrita do manifesto.
- Registrado limite estrutural das FKs simples de evidência no documento local: existência do resultado é protegida no schema; alinhamento ao monitor é garantido por finalize/seed. Nenhuma escrita pública de IDs de evidência foi encontrada com Backend.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`
- `backend/tests/test_db_qa_seed_preflight.py`
- `backend/app/db/RETENTION_QA_CONTRACT.md`
- `backend/app/db/IMPLEMENTATION.md`

### Decisões técnicas
- Correção restrita à ordem de validação do filesystem, sem alterar models/migrations/retention/Backend ou o conteúdo e open exclusivo do manifesto.
- Reprodução anterior usou FileExistsError real e transações/seed controlados: engine → seed → commit → verificação → commit → erro de diretório → dispose. Não é prova de commit/rollback em servidor PostgreSQL.

### Estado atual
- **38 passed, 2 skipped, em 0.59s** em `test_db_qa_seed_preflight.py`, `test_db_qa_seed.py`, `test_db_retention_contract.py` e `test_db_schema.py`; skips são os dois testes reais PG do seed, sem URL. Ruff check/format dos arquivos Python alterados aprovados. Nenhum seed real/PG18/runtime foi acessado; sem staging/commit/push.
- Auditoria da integridade anterior encontrou 69 cláusulas metadata no DDL offline inicial (9 FKs, 47 CHECKs, 6 UNIQUE, 7 PK), sem cláusulas ausentes. SQLite com FK=1 rejeitou 15 casos inválidos de identidade/duplicação/leases/datas/resposta e comprovou SET NULL/rollback em memória.
- SQL direto aceita evidência de outro monitor, failure sem error_code e duração infinita; finalize/seed garantem alinhamento e `_validate_cycle` rejeitou os dois últimos. São limites de defesa no schema, sem bug API alcançável demonstrado.
- Limite conhecido permanece: falha/cancelamento depois do primeiro commit, inclusive na verificação ou abertura/escrita do manifesto, pode deixar owner QA isolado sem manifesto. Não existe atomicidade entre arquivo e PostgreSQL; esta correção cobre somente falhas de diretório antes de conexão.

### Próximos passos
- Maestro revisa o fix, registra `docs/DEVELOPMENT_LOG.md` e centraliza Git segundo a regra atual de commits apenas feat/fix. Banco não contorna o bloqueio Git.
- Quando houver PG17 seguro disponível, repetir os testes reais do seed em schema UUID/migrations próprios, sem novo seed em public ou alteração do manifesto já revisado.
- A hipótese de índices de evidência continua pendente dos planos reais previstos em `RETENTION_QA_CONTRACT.md`; não criar migration/otimização especulativa.

## 2026-10-05 — Auditoria offline das FKs de evidência e contrato do ensaio

### Implementado
- Tooling `audit_retention_contract.py` compara somente as duas FKs de evidência e os índices declarados de `incidents` com o SQL offline do head Alembic real. CLI JSON usa `retention_contract_matches_migration` e `scope=incident_evidence_fks_and_indexes_offline`; nenhuma URL runtime é lida e nenhuma conexão é aberta.
- Regressões detectam drift de nulabilidade, ação DELETE, alvo FK e índice apenas na metadata. Classificação de candidatos B-tree respeita primeira coluna/método; ALTER/DROP é recusado conservadoramente. O teste do CLI proíbe conexões síncronas/assíncronas e fornece URLs runtime/teste inválidas.
- Registrado contrato de ensaio antes/depois em PG17 descartável, com migration real, queries do serviço existente, fixture seletiva, EXPLAIN sem ANALYZE e testes de integridade/rollback antes de propor migration.

### Arquivos principais alterados
- `backend/app/db/audit_retention_contract.py`
- `backend/tests/test_db_retention_contract.py`
- `backend/app/db/RETENTION_QA_CONTRACT.md`
- `backend/app/db/IMPLEMENTATION.md`

### Decisões técnicas
- Mantidos models, migration inicial e serviço/testes Backend de retenção. Não criar otimização especulativa antes de corroborar a hipótese com planos PG17.
- Auditoria delimitada ao contrato de evidências/índices declarados, não à paridade global do schema. Parser offline não substitui catálogo e falha conservadoramente em ALTER/DROP.
- Um candidato de índice não prova aplicabilidade do predicado ou uso pelo planner. Nenhum ganho de performance foi alegado; staging/commit/documentação raiz seguem com Maestro.

### Estado atual
- **24 passed, zero skips, em 0.53s**: `tests/test_db_retention_contract.py` e `tests/test_db_schema.py`, sem cache/pyc. Ruff check e format check aprovados; CLI emitiu JSON com head `0001_initial`, contrato e índices coerentes e `postgresql_executed=false`.
- Achado factual: ambas as evidências são nullable e FK para `check_results.id` com SET NULL; nenhuma possui candidato B-tree declarado com a coluna na primeira posição na metadata ou migration inicial.
- Revisão helper de carga Backend: 34 passed, quatro guardas PG17 skipped por ausência de URL e um Redis deselected; Ruff aprovado. Contrato QA é isolado/cooperativo, metadata não valida migrations, verificação por ACK e sampler adicionam overhead e um projeto serializa locks. Guardas novas não foram executadas no PostgreSQL.
- PG17 indisponível: inspeção passiva não encontrou listener55433 nem instalação local17; nenhuma conexão/alteração PG18/runtime. Docker aberto pelo usuário posteriormente, mas pipe negado para Maestro, conforme coordenação. Não foi iniciado ensaio nem houve stage/commit/push.
- Limite: auditoria não comprova execução de migration, catálogo, comportamento SET NULL, planos, locks, seletividade real ou custo de retenção.

### Próximos passos
- Maestro revisa a unidade local, registra progresso em `docs/DEVELOPMENT_LOG.md` e centraliza Git; Banco não disputa staging.
- Quando houver PG17 descartável acessível, executar os sete passos de `backend/app/db/RETENTION_QA_CONTRACT.md`, preservando serviços/dados de runtime.
- Coletar baseline das queries reais de evidência e testar candidatos somente no schema QA. Somente com evidência corroborada, criar migration aditiva/metadata e `test_db*` de upgrade/downgrade/catálogo/SET NULL/rollback; repetir `test_retention.py` sem alterar o contrato do serviço.

## 2026-10-04 — Regressão do tooling QA e fechamento da validação PG17

### Implementado
- Ampliada a cobertura do seed existente para verificar owner exclusivo, preservação de Monitor/Project anteriores, hash de login válido e leitura autenticada dos dados já commitados pela API em schema efêmero.
- Verificados paginação de checks sem duplicatas, segunda página de incidentes encerrados, isolamento entre proprietários e ausência da sentinela privada nos DTOs públicos.
- Adicionados valores numéricos independentes para p95 global e por monitor, contagens/buckets em 24h/7d/30d, retries recuperados e rollback de todas as entidades novas preservando o owner anterior.
- A proteção de manifesto existente agora é testada sem `tmp_path`: o teste garante que o arquivo nem é aberto, evitando a falha de ACL do temporário pytest no Windows restrito. O teste também exige banco explicitamente e mantém a recusa de PG18/55432, 5432, host remoto, outro banco, query options, driver incorreto e SQLite.
- No módulo de tooling, substituído o import dinâmico de `sys` por import explícito; nenhuma mudança de comportamento do seed ou do produto.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`
- `backend/tests/test_db_qa_seed.py`
- `backend/app/db/IMPLEMENTATION.md`

### Decisões técnicas
- Esta revisão executou apenas testes em schemas aleatórios do PG17/55433. Não foi executado novo seed em `public`, não foi atualizado o manifesto privado e não foi repetido o smoke aprovado.
- Manifesto existente `frontend/.impeccable/review/observations-fixture.json` preservado; a leitura de metadados confirmou `fixture_version=1`, `fixture_kind=synthetic_persisted_qa`, `external_checks_executed=false`, banco `vigil/public`, porta 55433 e `server_version_num=170011`. Credenciais não foram expostas.
- Não houve escrita/conexão ao runtime PG18 nesta etapa, alteração de models/migrations, infra, docs raiz, staging, commit ou push. Maestro permanece responsável pelo staging e documentação central.

### Estado atual
- Tooling QA: **13 passed, sem skips, em 3.69s** no PG17.11/55433, com `.venv/Scripts/python.exe -m pytest tests/test_db_qa_seed.py -q -p no:cacheprovider --tb=short`; Ruff check e format check dos dois arquivos passaram.
- Validação PG17 anterior desta etapa: **90 passed, sem skips, em 59.82s**, em `test_db_schema.py`, `test_db_postgresql.py`, `test_pipeline_db.py` e `test_retention.py`. Migration `0001_initial (head)` confirmada. Servidor oficial `postgres:17.11-alpine`, porta publicada 55433/interna 5432 e volume `vigil_postgres_data` preservados.
- Limitações: o teste de manifesto existente valida o bloqueio antes de qualquer I/O; não mede ACLs do filesystem. Os testes novos usam HTTP ASGI local da API, não navegador nem HTTP dos monitores. Manifesto/freshness do smoke anterior não foram renovados. Falha ao gravar manifesto após commit ainda pode deixar owner QA isolado, conforme registro anterior.

### Próximos passos
- Maestro pode revisar/stagear esta unidade de regressão; arquivos da área serão liberados após o relatório de evidências.
- Para futura carga, preparar primeiro schema/owner PG17 e stream/group Redis exclusivos; medir agenda → publicação → claim → commit → ACK, queue delay, locks, pool DB e backlog/leases. Nenhuma carga iniciada nesta revisão.
- Começar a análise de planos com `EXPLAIN` sem `ANALYZE`, verificando filtros de jobs abertos e índices parciais. Ensaios que executem mutações devem permanecer no ambiente QA isolado e não competir com o smoke existente.

## 2026-10-04 — Fixture sintética de observações no PostgreSQL 17

- `seed_observations_qa.py` é tooling opt-in: exige URL explícita local em 55433/database vigil, PostgreSQL 17/schema public, ambiente não produtivo e ambos os gates desligados. Não é importado pelo produto.
- Cada execução cria owner/projeto novos, seis monitores, 76 ciclos concluídos e 38 incidentes sintéticos. URLs `.invalid` nunca são acessadas; `next_check_at` permanece NULL. Encerramentos administrativos são exemplos de DTO, sem alegar execução dessas ações.
- Manifesto privado registra login e expectativas derivadas das amostras. Métricas/buckets de 24h/7d/30d e incidentes são confrontados com consultas SQL antes e depois do commit. Manifestos existentes não são sobrescritos.
- `tests/test_db_qa_seed.py`: 10 passed no PG17.11/55433, incluindo rejeição do PG18/55432, gates/produção, filtro público, p95 independente e rollback completo em schema isolado. Ruff passou.
- Seed runtime e smoke foram executados apenas no PG17 Compose. Nenhuma gravação no PG18. Credenciais/relatórios ficam fora do Git. Falha de escrita do manifesto após o commit pode deixar um owner QA isolado; nenhuma limpeza destrutiva é automática.


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
