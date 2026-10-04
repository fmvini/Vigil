# Backend — registro de implementação

## 2026-10-04 — Réplicas HTTP reais e cleanup SSE sob cancelamento

- `test_api_replicas.py` inicia três Uvicorn independentes com esquema PostgreSQL17 UUID e Redis reais, portas loopback efêmeras e gates false. Seis contas/projetos sintéticos mantêm 51 streams HTTP e três assinaturas lentas instrumentadas.
- Commits REST alternam pelas réplicas e chegam aos streams sem eco duplicado. Seiscentos sinais Redis cadenciados geraram 5.100 entregas ordenadas, com whitelist e isolamento por owner; mil sinais em rajada preservaram `snapshot.required` e filas de até 32.
- Limite de três conexões é por conta/processo, confirmado via 429 em cada API; não é cota distribuída. Liberar uma assinatura permite reutilizar o slot HTTP. Logout em uma API fecha streams da sessão nas três pela cadência real de 30s, preservando outros owners.
- O disconnect imediatamente após headers reproduziu vazamento de conexão na revalidação SSE sob cancelamento AnyIO. `session_valid` agora protege leitura/devolução de recursos com CancelScope shield, preservando prazo asyncio de 5s; testes cobrem cancelamento na leitura/close e propagação de cancelamento asyncio direto.
- Ensaio final no host: passed em 35,72s, sem stderr/erro de pool, p50 10,771ms/p95 15,839ms nas 5.100 entregas e revogação em 23,113s. Relatório `.cache/verification/api-replicas-host.xml`. Linux: p50 4,863ms/p95 7,753ms, carga em 2,142s e revogação em 25,454s.
- Regressão central: 386 backend passed/14 skips apenas SQLite em 211,15s, 64 tooling e 41 frontend passed; Ruff/TypeScript/build/Compose e firewall físico aprovados. Módulo SSE final teve 59 passed no host, incluindo o caso adicional de cancelamento asyncio validado após coleta central.
- Limites: carga local cadenciada, sem SLA produtivo, load balancer ou múltiplos hosts; assinaturas lentas exercitam fila Pub/Sub, não backpressure físico do socket. REST conserva revisão persistida mesmo diante de sinais sintéticos de carga. Nenhum HTTP externo/job de check executado.

## 2026-10-04 — Crash abrupto de workers e recuperação durável

- `tests/test_worker_process_recovery.py` inicia interpretadores independentes com Receiver Taskiq, PostgreSQL17 e Redis reais; interrompe somente seus próprios filhos após entrega, após claim confirmado, durante finalização não commitada e após commit antes do ACK.
- Novo consumidor recupera a PEL sem publicação adicional. Lease válida evita execução duplicada; scheduler recupera a lease vencida e publicador envia a tentativa seguinte. Replay após conclusão não altera resultado, incidente ou revisão.
- Três crashes técnicos esgotam o job sem amostra de saúde ou incidente; envelopes pendentes são drenados e ACKados sem nova execução. Cleanup atua somente no schema/stream UUID do teste.
- Cinco cenários passaram no host com PG17.11/Redis7.4.11 em 66,30s e também no container Linux. Regressão central final: 383 backend passed/14 skips apenas SQLite em 214,06s; 30 tooling e 41 frontend passed, Ruff/TypeScript/build/Compose aprovados. A verificação exige este módulo sem skips.
- Limites: executor sintético não faz HTTP; leases de 12s/2s são parâmetros de teste em subprocessos, mantendo o padrão de produção de 90s. Usa tarefa e Receiver reais, sem iniciar o startup produtivo nem alterar gates. Não demonstra recuperação de host/Redis/PG ou políticas físicas de egress.

## 2026-10-04 — Redis Streams, Pub/Sub e sockets TLS reais

- `test_broker_integration.py` usa streams/grupos UUID exclusivos: PEL, reclaim ocioso de múltiplos lotes sem publicação nova, ACK idempotente/envelope inválido e Receiver Taskiq real verificando commit PostgreSQL antes do ACK. Falha após flush reverte resultado e mantém mensagem recuperável.
- `test_events_redis.py` comprova fanout/owner whitelist/eco/cleanup, entrega entre processos Python independentes e publicação sem assinante local. Um proxy TCP exclusivo sofre interrupção real, mantendo sinais locais/snapshots e recuperando entrega remota; Redis compartilhado não é parado ou limpo.
- `test_transport_sockets.py` comprova TLS/SNI/Host em IPv4/IPv6, leitura somente dos headers mesmo com body declarado grande, CA desconhecida/hostname errado sem retries/HTTP e SSRF runtime bloqueando loopback/mistura de IPs antes do socket.
- Certificados/chave em `tests/fixtures/tls/` são fixtures públicos sem finalidade produtiva. CA carregada somente na instância SSLContext do teste; CERT_REQUIRED/check_hostname permanecem ativos. A rota física para loopback existe apenas no adapter do teste.
- No Windows o Avast substituiu até o certificado de loopback. Os oito testes TLS passaram em container Linux, sem alterar validação runtime; Pub/Sub passou também no Windows (3 passed). Scripts de verificação permitem container descartável com dependências dev fixadas e exigem módulos de integração executados, sem skips obrigatórios.
- Limites: evidências usam Redis7.4.11/PG17.11 locais; não demonstram egress/firewall, disponibilidade externa, recuperação de infraestrutura inteira ou carga de produção. Gates continuam false.
- Regressão central final `scripts/verify.ps1 -RequireIntegration -BackendContainer`: 378 passed e 14 skips apenas de variantes SQLite em 158,29s, nenhuma integração obrigatória ignorada. Inclui DB/schema/pipeline/retenção/seed, Redis real, Pub/Sub e sockets TLS. Ruff e 41 testes frontend/typecheck/build/Compose passaram.


## 2026-10-04 — SSE privado com sessão, revogação e isolamento

### Implementado
- `GET /api/v1/events` integrado ao app; autenticação pelo cookie HttpOnly same-origin, sem credenciais em query. Origin presente precisa estar autorizado. Auth conclui sua transação e libera a conexão antes de reservar o stream; falha de commit não ocupa slot.
- Sessão revalidada no banco antes do primeiro sinal e a cada 30s, incluindo usuário ativo, proprietário da sessão, revogação, validade absoluta e inatividade. Essa leitura não estende a atividade. Logout e rotação de login invalidam o stream antigo; a sessão nova permanece válida.
- Sinais restritos ao proprietário autenticado, com whitelist de UUIDs/revision e sem `owner_id`, `source`, URLs, resultados ou credenciais no cliente. Contrato aceita `project.updated`, `monitor.updated`, `incident.opened` e `incident.closed`; produtores atuais de CRUD/worker invalidam por projeto/monitor, permitindo reconciliar incidentes pelo REST.
- Snapshot inicial e periódico de 30s; heartbeat de 15s. Fila de 32 sinais por stream; overflow descarta o backlog e pede `snapshot.required` com reason `backpressure`. Três conexões por conta por processo, com resposta 429 ao exceder.
- Redis Pub/Sub best effort após commit, entrega local e snapshots funcionando quando Redis está indisponível. API publica mesmo sem assinantes locais, descarta eco da própria réplica e valida envelopes antes de publicar/entregar. Falha de publish não desabilita um listener saudável. Publish/cleanup têm deadlines de 1s; envio do stream tem deadline de 10s e libera slot/gerador ao desconectar, cancelar ou falhar.

### Arquivos principais alterados neste retorno
- `backend/app/api/events.py`
- `backend/app/services/events.py`
- `backend/tests/test_events.py`
- `backend/IMPLEMENTATION.md`

### Decisões técnicas
- REST continua sendo a fonte de verdade; SSE transporta invalidações efêmeras, sem replay persistido ou garantia de entrega. Frontend confirmou EventSource same-origin e reconciliação inicial/30s/visibility/reconexão, incluindo `snapshot.required` e atualização do projeto selecionado.
- Integração existente em `app/main.py`, `app/api/dependencies.py`, `app/services/resources.py` e `app/monitoring/{worker,tasks}.py` foi revisada sem novas alterações neste retorno. Eventos de CRUD saem após commit; worker sinaliza após persistência e ACK permanece condicionado ao resultado transacional.
- Teste ASGI revalida a linha efetivamente commitada. No SQLite em memória, login e consulta SSE não podem usar transações simultâneas na conexão única; o teste sincroniza o checkpoint após a invalidação. PostgreSQL real usa schemas isolados por teste.

### Estado atual e evidência
- Regressão final: **117 passed, 8 skipped**, em 197.51s, com PostgreSQL real em `127.0.0.1:55432` e SQLite. Comando, a partir de `backend/`: `.venv/Scripts/python.exe -m pytest tests/test_events.py tests/test_auth.py tests/test_resources.py tests/test_worker.py -q -p no:cacheprovider`, com `VIGIL_TEST_DATABASE_URL` apontando para o cluster local isolado.
- A suite conjunta inclui 56 casos SSE: autenticação/Origin/query, limite e cleanup, sessão revogada/expirada/inativa/deletada, logout/rotação via HTTP, owner filtering real de CRUD, commit/rollback, backpressure, heartbeat/snapshots, send lento em ASGI 2.0/2.4, cancelamento, publicação sem assinantes e Pub/Sub inválido/indisponível. Os oito skips são variantes SQLite de concorrência/worker que exigem PostgreSQL.
- Ruff passou em `app/api/events.py`, `app/services/events.py` e `tests/test_events.py`. Arquivos liberados para revisão do Maestro; nenhuma edição de observations/retention/infra/docs raiz ou operação Git realizada neste retorno.
- Redis real não foi executado: cobertura Pub/Sub usa doubles determinísticos. Limite de conexões é local ao processo, não distribuído. Revogação usa cadência de 30s, sujeita ao tempo de consulta/envio; não promete encerramento instantâneo. Gates de pipeline/network continuam desligados.

### Próximos passos
- Maestro concluir `scripts/verify.ps1`, integrar o smoke real do Frontend e consolidar DEVELOPMENT_LOG/commit local quando o índice Git permitir escrita.
- Quando Redis real estiver disponível, validar propagação entre processos, reconexão, indisponibilidade e cleanup em ambiente isolado. Preservar reconciliação REST e gates até concluir validações operacionais já registradas.

## 2026-10-04 — Transporte/worker e candidato Redis Streams

### Implementado e verificado
- `app/monitoring/transport.py`: backend público HTTPCore resolve todos A/AAAA antes do socket, rejeita qualquer endereço proibido, conecta ao IP literal e confirma peer. Mantém hostname original no Host/SNI, suporta IPv6 público e rejeita endereços mapeados/transição/NAT64. TLS usa CA certifi explícita e valida hostname. DNS é revalidado em cada tentativa; sem keepalive/cookies compartilhados.
- HTTPX `trust_env=False`, sem redirects, GET fixo e leitura só até headers. Limite agregado 32KiB de headers incluindo 1xx; reads até 4KiB podem trazer bytes incidentais de body no mesmo pacote, sem drenar body. Deadline total por tentativa e ciclo, concorrência local50/global e5/host, saturação classificada operacionalmente.
- `executor.py`: retries RN007 de timeout/conexão/DNS transitório e 5xx inesperado, .5s/1s com jitter ±20%. TLS inválido, 3xx/4xx inesperados e DNS permanente não retentam. 5xx esperado é sucesso. Attempts sanitizadas e um EvaluatedCycle consolidado.
- `worker.py`: claim e finalize em transações separadas; sem locks/sessão durante HTTP. Sinal best effort só depois do commit; duplicata não repete HTTP após conclusão. Erros operacionais não fabricam CheckResult failure. Cancelamento conserva lease para recuperação.
- `tasks.py`: Taskiq0.13.0 com `ack_type=manual` e `Context.ack()` após retorno persistido. Falha de claim/finalize/commit deixa mensagem sem ACK. Testes usam Receiver real com PostgreSQL real para verificar ordem e rollback.
- `publisher.py`: seleção pending elegível, publicação fora de transação e marcação condicional por versão/execution_count/retry_at/status; crash entre envio/marcação pode duplicar e é tolerado. Loop scheduler/publicador separado da API em `monitoring/run.py`, integrando `scheduler_tick` do Banco.
- `broker.py`: candidato mantém RedisStreamBroker1.2.4, grupo desde `0-0`, sem trimming e reclaim120s. Override de listen chama XAUTOCLAIM mesmo sem novas mensagens e avança cursor; upstream pinned só reclaims após fetched não vazio. Sem lock Redis de aplicação. Valida/sanitiza envelope UUID/version e força ACK manual antes do Receiver; payload inválido não é logado.
- Router observations do Maestro incluído em `app/main.py` com `/api/v1`; consultas e DTOs permanecem propriedade do Maestro.

### Estado e verificação
Suite integrada após esse incremento: **262 passed, 12 skipped**, em69s, com PostgreSQL18.6 real. Transporte:43 testes determinísticos sem acesso a APIs externas. Casos incluem DNS misto/rebinding, IPv4/IPv6, Host/SNI, TLS inválido, redirect, headers excessivos, slow trickle, retry/backoff e limites de pool. Ruff/lockcheck passaram.

Há skips de variantes SQLite incompatíveis com operações PostgreSQL e **um teste Redis real**. Docker info fora do sandbox confirmou namedpipe inexistente; localhost6379 fechado e nenhum serviço Redis disponível. O teste `tests/test_broker.py::test_real_redis_messages_before_group_ack_and_idle_reclaim` está pronto, mas **não foi executado**. Mock de Redis não é reportado como integração real. Taskiq Receiver+commit PG foram executados; XAUTOCLAIM no servidor Redis permanece pendente.

### Feature flags e continuação
- `VIGIL_PIPELINE_ENABLED=false` e `VIGIL_MONITORING_NETWORK_ENABLED=false` por padrão. Startup worker e scheduler/publicador são recusados até habilitação explícita após experimento Redis real e verificação de egress. Não foi executada nenhuma URL cadastrada ou arbitrária nesta sessão.
- `VIGIL_REDIS_STREAM_NAME=vigil:checks`, `VIGIL_REDIS_CONSUMER_GROUP=vigil-workers`; limites por host são por processo, não globais entre réplicas.
- Quando Redis real estiver disponível: definir `VIGIL_TEST_REDIS_URL` e executar `uv run --frozen python -m pytest tests/test_broker.py -q -p no:cacheprovider`. Somente depois do resultado revisar/habilitar flags no ambiente isolado com egress adequado.
- Com gates validados, processos planejados: `uv run --frozen python -m app.monitoring.run` e `uv run --frozen taskiq worker app.monitoring.tasks:broker --workers 1 --max-async-tasks 50 --max-prefetch 50 --ack-type manual`. Comandos CLI verificados via help; processos **não iniciados** nesta sessão.
- Ainda pendentes prova TLS com socket real em ambiente controlado, controles de egress de produção, Redis real/crash/reclaim e observabilidade/carga operacional. A suíte confirma transporte por backend determinístico e SSLContext verificadora, não um deploy público.
- Próximo autorizado: SSE privado com snapshots periódicos, revogação DB, fila limitada, owner filtering e degradação se Pub/Sub indisponível.

### Fontes oficiais
[HTTPCore network backends](https://www.encode.io/httpcore/network-backends/), [HTTPX transports](https://www.python-httpx.org/advanced/transports/), [HTTPX async streaming](https://www.python-httpx.org/async/), [Taskiq arquitetura/context](https://taskiq-python.github.io/guide/architecture-overview.html), [Taskiq Receiver](https://github.com/taskiq-python/taskiq/blob/master/taskiq/receiver/receiver.py), [RedisStreamBroker](https://github.com/taskiq-python/taskiq-redis/blob/main/taskiq_redis/redis_broker.py), [Redis XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/). Versões verificadas no PyPI e comportamento comparado ao código instalado fixado no lock; sem troca de broker.

## 2026-10-04 — Primeiro incremento de API

### Implementado
- FastAPI com SQLAlchemy async e factories compartilhadas de `app/db/`, sem modelos duplicados nem criação automática de tabelas no startup.
- Configuração via `app.config.Settings`, dependências diretas fixadas e `uv.lock` universal. Python 3.12–3.14; execução/testes locais em 3.13.3.
- `GET /health/live` independente de dependências; `GET /health/ready` verifica PostgreSQL com deadline e retorna 503 sanitizado em falha. Redis não é dependência da API inicial.
- Prefixo REST `/api/v1`; cadastro sem login automático, login/me com CSRF e logout revogável.
- Argon2id, comparação de credenciais desconhecidas com hash dummy, rehash no login, processamento em thread com limite de quatro hashes simultâneos.
- Cookie opaco de 256 bits. Banco guarda apenas SHA-256 hexadecimal do token; rotação no login revoga o cookie anterior deste navegador. Inatividade de 24h e prazo absoluto de 7 dias; atualização de atividade após 5min não estende o prazo absoluto.
- Cookie `vigil_session` apenas em `dev`; `__Host-vigil_session` em `test`/`prod`, HttpOnly, Secure, SameSite=Lax, Path=/, sem Domain.
- Origin exato autorizado e `X-Vigil-Request: browser` em mutações; JSON obrigatório em register/login; `X-CSRF-Token` vinculado à sessão nas mutações autenticadas. Frontend/API sob o mesmo origin via proxy; não habilitado CORS permissivo.
- Projetos e monitores: criação, consulta, listas paginadas, PATCH parcial e DELETE lógico idempotente. Pausa/retomada idempotentes, sem apagar histórico ou fabricar saúde.
- Isolamento por `Project.owner_id`; acesso cruzado retorna 404. Cliente não pode alterar owner/FKs, versão, saúde ou lifecycle.
- Cotas RN002 protegidas por lock da linha User, seguido de Project/Monitor. Pausados contam; arquivados liberam cota. Testes reais concorrentes verificam projetos e monitores.
- RN003–RN006: URL HTTP(S), portas 80/443, GET fixo, sem credenciais/fragmento/query com nomes conhecidos de secrets, rejeição lexical de IPs/destinos locais/ambíguos. Limites estritos e validação de orçamento máximo incluindo jitter e overhead. PATCH valida configuração completa após merge.
- Alteração de regras invalida versão/jobs/lease, reinicia snapshot e fecha incidentes administrativamente. Renomear preserva snapshot/jobs. Pausa conserva saúde/incidente e interrompe sequência; projeto arquivado arquiva monitores atomicamente.
- Erros `{error:{code,message,details}}`; validação não ecoa senhas, URLs ou inputs. Respostas privadas com `Cache-Control: no-store`.

### Arquivos principais
- `app/main.py`, `app/config.py`, `app/security.py`
- `app/api/{auth,dependencies,errors,resources,schemas}.py`
- `app/services/resources.py`, `app/domain/monitors.py`
- `tests/{conftest,test_auth,test_resources,test_validation,test_api_health}.py`
- `pyproject.toml`, `uv.lock`

`app/db/`, migrations, alembic.ini e tests/test_db* pertencem a Banco de Dados. `app/domain/health.py` e `tests/test_health.py` foram implementados por Maestro. Dockerfile/Compose/docs raiz também pertencem a Maestro.

### Contratos entregues ao Frontend
- `POST /auth/register` → 201 `{id,email,created_at}` sem cookie.
- `POST /auth/login`, `GET /auth/me` → 200 `{user:{id,email,created_at},csrf_token}`.
- `POST /auth/logout` → 204. Exige sessão válida e proteções de mutação.
- `/projects`: GET `{items,total}`, POST 201; `/projects/{id}`: GET/PATCH 200, DELETE 204.
- `/projects/{id}/monitors`: GET `{items,total}`, POST 201.
- `/monitors/{id}`: GET/PATCH 200, DELETE 204; POST `/pause` e `/resume` → 200 Monitor.
- Paginação `limit` 1–100 (default20), `offset` ≥0. Ordem estável created_at/id.
- DTO Project: id,name,description,public_slug,public_status_enabled,revision,archived_at,created_at,updated_at.
- DTO Monitor: id,project_id,name,url,method,interval_seconds,timeout_ms,expected_status,failure_threshold,retry_count,latency_threshold_ms,is_public,config_version,paused_at,archived_at,next_check_at,health_status,consecutive_failures,last_checked_at,last_scheduled_at,last_http_status,last_latency_ms,last_outcome,last_error_code,last_degradation_reason,created_at,updated_at,is_paused,freshness.
- `health_status=null` e `freshness=no_data` até existir medição; paused tem prioridade, stale é calculado por idade. Dados privados não incluem password_hash/token_hash.
- Códigos principais: validation_error (422), unauthenticated/invalid_credentials (401), origin_forbidden/browser_request_required/csrf_invalid (403), json_required (415), not_found (404), conflict/quota_exceeded (409), database_unavailable/not_ready (503).

### Configuração e execução
Variáveis `VIGIL_DATABASE_URL` (`postgresql+asyncpg://...`), `VIGIL_REDIS_URL` (reservada para pipeline), `VIGIL_ENVIRONMENT` (dev/test/prod), `VIGIL_ALLOWED_ORIGINS` (array JSON de origins exatos, sem barra final). Produção exige URL DB explícita e origins HTTPS. Variáveis opcionais: `VIGIL_SESSION_IDLE_SECONDS`, `VIGIL_SESSION_ABSOLUTE_SECONDS`, `VIGIL_READINESS_TIMEOUT_SECONDS`.

```powershell
cd backend
$env:UV_CACHE_DIR = "$PWD\..\.cache\uv"
uv sync --frozen --python 3.13 --system-certs
$env:VIGIL_DATABASE_URL = "postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil"
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

A credencial acima pertence apenas ao cluster local isolado criado por Banco de Dados; use credenciais próprias em outros ambientes. O switch `--system-certs` foi necessário para a CA do ambiente nos downloads oficiais.

### Verificação
```powershell
$env:VIGIL_TEST_DATABASE_URL = "postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil"
uv run --frozen python -m pytest -q -p no:cacheprovider
uv run --frozen ruff check app/api app/config.py app/security.py app/main.py app/domain/monitors.py app/services/resources.py tests/test_auth.py tests/test_validation.py tests/test_resources.py tests/test_api_health.py tests/conftest.py
uv lock --check --offline
```

Resultado do marco inicial: **156 passed, 2 skipped**, em 39s, com PostgreSQL 18.6 real e SQLite. Os skips são apenas as duas variantes SQLite de testes concorrentes, pois SQLite não implementa os row locks PostgreSQL. Cada teste API PG cria/remove um schema aleatório, preservando tabelas runtime. Ruff, compilação e lock check passaram. Testes DB/migrations (Banco) e health (Maestro) incluídos na execução completa. Dois casos adicionais de URL multicast foram adicionados após esse marco e serão verificados antes do próximo relatório.

### Fontes oficiais consultadas
- Versões verificadas em metadados oficiais [PyPI](https://pypi.org/) em 2026-10-04: FastAPI0.142.2, Pydantic2.13.5, pydantic-settings2.15.0, asyncpg0.31.0, Alembic1.20.0, argon2-cffi25.1.0, uvicorn0.54.0; ferramentas de teste e transitivas estão no lock.
- SQLAlchemy2.0.54 fixado deliberadamente no ramo 2.0, alinhado ao Banco: [documentação/release](https://docs.sqlalchemy.org/en/20/), [asyncio e sessões](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html).
- [FastAPI async](https://fastapi.tiangolo.com/async/) e [dependency yield/scope](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/). A transação usa scope=function para commit/rollback antes de enviar a resposta.
- [Argon2id/PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html), [Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/).

### Limitações e próximo incremento autorizado
- Este marco é API de configuração/autenticação, sem scheduler, broker, worker, HTTP externo, SSE, métricas/histórico ou status pública. `next_check_at` registra agenda futura e não comprova execução de check.
- Validação de formulário não é proteção SSRF na conexão. Não resolve DNS nem acessa URLs cadastradas. Valores arbitrários de secrets em path/query não são reconhecíveis de forma geral; names conhecidos são rejeitados e frontend deve orientar URLs sem secrets.
- Rate limiting distribuído, métricas/logs operacionais e política de cadastro público ainda pendentes; quatro hashes concorrentes limitam memória, não substituem controle de abuso.
- Readiness verifica conectividade DB, sem afirmar saúde de Redis/pipeline ou schema atualizado.
- Próximo: validar transporte fixando IP público e preservando Host/SNI; experimentar Taskiq/Redis Streams com ACK após commit/reclaim; integrar contratos transacionais `services/check_jobs.py` (Banco) e health puro (Maestro); então expor histórico, métricas, incidentes e DTO público separado.
- Git local e DEVELOPMENT_LOG serão consolidados por Maestro conforme autorização; nenhum git add/commit/push realizado por Backend.
