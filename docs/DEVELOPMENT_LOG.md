# Registro de desenvolvimento

## 2026-10-04 — Verificação central do frontend e base para commits

### Implementado
- Concluída verificação direta do frontend pelo Maestro em execução autorizada para subprocessos locais: 41 testes Vitest e build TypeScript/Vite passaram.
- Revisada a lista completa de arquivos da base funcional; caches, dumps, credenciais de QA e evidências de navegador permanecem excluídos de Git.

### Arquivos principais alterados
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Consolidar primeiro a base funcional já validada em um commit local coerente antes de novas entregas de transporte/operação.
- Usar a distribuição WSL/Docker já instalada para investigar Redis real; nenhuma flag de execução externa foi habilitada.

### Estado atual
- Backend da base: 352 testes aprovados, 13 skips documentados; frontend confirmado diretamente com 41 testes, sem skips, e build aprovado.
- Remoto `origin` configurado; staging dos 110 arquivos revisados foi autorizado e concluído. Base pronta para commit local; sem push automático.
- WSL Ubuntu disponível; Docker Desktop solicitado em segundo plano, Redis ainda não validado.

### Próximos passos
- Consolidar commit local da base e iniciar testes de transporte com sockets reais em ambiente controlado.
- Disponibilizar Redis isolado, validar ACK/reclaim/PubSub reais e repetir modo obrigatório de verificação.
- Manter gates desligados até concluir egress e os critérios operacionais restantes.

## 2026-10-04 — SSE e observações integrados ao navegador

### Implementado
- SSE privado com autenticação concluída antes de reservar conexão, revalidação de sessão, isolamento por proprietário, filas limitadas e cleanup em desconexão/cancelamento/envio lento.
- Frontend integrado a métricas, histórico, incidentes e página pública; SSE invalida consultas REST, com snapshots serializados, reconciliação pendente e polling de 30s.
- Corridas de troca/edição de projeto, leitura lenta e 401 atrasado corrigidas; paginação se ajusta quando retenção reduz os resultados.
- Smokes reproduzíveis de CRUD/status pública e SSE real, incluindo mutação fora da aba, snapshot periódico e revogação de sessão.

### Arquivos principais alterados
- `backend/app/api/events.py`, `backend/app/services/events.py`, `backend/tests/test_events.py`, `backend/IMPLEMENTATION.md`
- `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/Observations.tsx`, `frontend/src/live.ts`
- `frontend/src/test/App.test.tsx`, `frontend/src/test/Observations.test.tsx`, `frontend/src/test/api.test.ts`, `frontend/src/test/live.test.tsx`
- `frontend/scripts/browser-smoke.mjs`, `frontend/scripts/live-smoke.mjs`, `frontend/package.json`, `frontend/IMPLEMENTATION.md`
- `docs/API.md`, `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- SSE transporta invalidações efêmeras, sem replay; os dados exibidos vêm das consultas REST. Redis indisponível não impede sinais locais, snapshots e polling.
- Três streams por conta por processo, fila de 32 sinais, envio limitado a 10s, heartbeat 15s e revalidação/snapshot 30s. Produtores atuais invalidam projeto/monitor; incidentes são reconciliados pelo REST.
- Mantidos gates pipeline/network desligados. Smokes criam somente cadastros de QA e não executam URLs monitoradas.
- Cluster local recebeu `ALTER ROLE vigil IN DATABASE vigil SET max_parallel_workers_per_gather=0` após introspecção ficar em IPC com plano paralelo. Nova conexão executou plano serial em 0,105s; também afeta novos pools API dessa role/banco. Sem migration, restart ou sinal ao servidor. Reversão: `ALTER ROLE vigil IN DATABASE vigil RESET max_parallel_workers_per_gather` quando o ambiente suportar paralelismo.

### Estado atual
- Backend: 117 passed/8 skipped na regressão events/auth/resources/worker com PostgreSQL real e SQLite; 56 casos SSE. Ruff passou.
- Frontend reportou 41 testes aprovados, typecheck/build e smokes reais desktop/mobile de CRUD/status pública/SSE. Relatórios em `frontend/.impeccable/review/`, fora de Git/Docker.
- Maestro confirmou 42 passed/1 skipped em observações/health e, depois, backend completo **352 passed/13 skipped em 359,23s**, com PostgreSQL real. Doze skips são variantes SQLite e um é Redis ausente. Ruff de `app/tests` passou; relatório `.cache/verification/backend.xml` contém 365 casos. A primeira rodada foi interrompida ao travar em introspecção PostgreSQL; a repetição com novas conexões passou após ajuste local do paralelismo.
- Verificação central parou no frontend por `spawn EPERM` ao iniciar esbuild, antes de executar os testes JS nessa rodada; não é falha de assertion. Evidência frontend válida é a suíte/build/smokes de 41 testes reportados pelo especialista. Maestro confirmou também typecheck diretamente; Compose e whitespace passaram separadamente.
- Gate `RequireIntegration` executado sobre o relatório real rejeitou exatamente o skip Redis, aceitando a cobertura PostgreSQL e os skips SQLite esperados. Ausência de URLs obrigatórias também foi rejeitada antes de rodar a suíte.
- API 8000, Vite 5173 e PostgreSQL 55432 ativos. Redis real/PubSub entre réplicas, execução externa do pipeline e deploy continuam sem validação.
- Backends locais anteriores PID 1968 (introspecção IPC) e PID 34620 (DROP do banco temporário de restore) preservados e pendentes de diagnóstico operacional; novos testes usam conexões próprias.
- Git: `origin` configurado, mas staging recusado por permissão de `.git/index.lock`; nenhum commit ou push realizado nesta sessão.

### Próximos passos
- Criar commits locais das entregas verificadas quando o índice Git permitir escrita. Reexecutar `scripts/verify.ps1` integralmente quando o ambiente permitir subprocessos esbuild; preservar o relatório backend e evidências frontend existentes.
- Disponibilizar Redis real e executar modo obrigatório de `scripts/verify.ps1`; validar ACK/reclaim e fan-out Pub/Sub entre processos.
- Resolver backends/banco temporário pendentes em ambiente operacional adequado; não repetir DROP nem encerrar walwriter para contornar a restrição.
- Validar sockets TLS/SNI/IPv6, egress, recuperação/carga e PostgreSQL 17 do Compose antes de habilitar pipeline ou publicar deploy.

## 2026-10-04 — Verificação de integrações e operação local

### Implementado
- Verificação com URLs PostgreSQL/Redis explícitas, relatório JUnit, motivos dos skips e modo `RequireIntegration` que recusa ausência/skip das integrações reais.
- Wrapper PowerShell de retenção com banco obrigatório, limites de lotes e rollback por padrão; aplicação exige `-Apply`.
- Deadline externo de cleanup do teste de backup/restore: encerra apenas o cliente criado pelo script e informa pendência, sem sinalizar backends PostgreSQL.
- Runbook de operação e exclusão de temporários pytest, cache npm e evidências privadas de QA dos contextos Git/Docker apropriados.

### Arquivos principais alterados
- `scripts/verify.ps1`, `scripts/run-retention.ps1`, `scripts/test-backup-restore.ps1`
- `.gitignore`, `README.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`
- `frontend/.dockerignore`, `backend/.dockerignore`
- `backend/app/db/IMPLEMENTATION.md` (validação de retenção pelo especialista).

### Decisões técnicas
- Não considerar configuração de URL como prova de integração: o modo obrigatório também confere os testes executados no relatório.
- Preview de retenção executa somente um lote real e reverte; não estima backlog completo nem altera gates do pipeline.
- Não repetir DROP nem encerrar walwriter para resolver um cleanup preso no ambiente restrito.

### Estado atual
- PostgreSQL 18.6 retomado no cluster existente, porta 55432, migration `0001_initial`; retenção passou em 29 testes reais sem skips.
- Maestro confirmou wrapper de retenção com `committed=false`, sintaxe dos três scripts, rejeição de URLs obrigatórias ausentes, gate de skips sobre relatório JUnit real e configuração Compose.
- Cleanup validado com executável controlado: sucesso, exit 7 e cliente travado encerrado em aproximadamente 1,05s com timeout de 1s; nenhum banco envolvido nesse teste.
- Backup/restore verificou migration e sete tabelas no banco novo; cleanup real ficou em `IPC/ProcSignalBarrier`. Banco `vigil_restore_test_2b30885f075f4396bd10830998d66b7b` e backend DROP PID 34620 permanecem pendentes; walwriter PID 27364 preservado. O cliente original foi interrompido, sem confirmação de cancelamento da query no servidor.
- Docker/Redis reais indisponíveis. SSE/frontend ainda em conclusão pelos agentes neste marco.
- Remoto `origin` configurado pelo usuário; staging tentado e recusado com `.git/index.lock: Permission denied`. Nenhum commit ou push realizado.

### Próximos passos
- Concluir entregas SSE/frontend e rodar verificação central com PostgreSQL real.
- Executar `scripts/verify.ps1 -RequireIntegration` quando Redis real estiver disponível; validar ACK/reclaim e Pub/Sub entre processos antes de liberar pipeline.
- Inspecionar cleanup pendente do banco de restore em ambiente que permita operação PostgreSQL normal; não repetir DROP sem diagnóstico.
- Criar commits locais das unidades verificadas quando escrita no índice Git estiver disponível; não fazer push automático.

## 2026-10-04 — Pipeline transacional e consultas de observação

### Implementado
- Agendamento por slot recente, intenção persistida e avanço atômico da agenda, SKIP LOCKED, lease/versionamento e finalização idempotente de resultado/saúde/incidente/revisão.
- Reconciliação e até três execuções técnicas com retry de 1s/2s; exclusões internas não fabricam indisponibilidade do alvo.
- Consultas privadas de checks, métricas por monitor/projeto, série UTC e incidentes com janelas/paginação/isolamento.
- Status pública com opt-in duplo e DTOs explícitos sem dados privados.
- Frontend base validado em navegador real (cadastro/login, CRUD, pausa/retomada, sessão após reload, archive/logout), com correção de corrida ao salvar e trocar de projeto.

### Arquivos principais alterados
- `backend/app/services/check_jobs.py`, `backend/app/monitoring/scheduler.py`, `backend/tests/test_pipeline_db.py`
- `backend/app/api/observations.py`, `backend/app/services/observations.py`, `backend/tests/test_observations.py`
- `backend/app/main.py`, `frontend/src/App.tsx`, `frontend/src/Forms.tsx`
- `frontend/IMPLEMENTATION.md`, `backend/app/db/IMPLEMENTATION.md`, `docs/API.md`

### Decisões técnicas
- Caller controla transação/commit dos jobs; HTTP e publicação não podem ocorrer segurando locks.
- p95/contagens/média calculados no PostgreSQL sobre amostras brutas; adapter SQLite de teste usa percentil interpolado equivalente.
- Métricas/checks têm retenção consultável de 30 dias; incidentes até 90 dias, com filtro por sobreposição para não esconder incidente aberto antigo.
- RedisStreamBroker terá reclaim em ticks mesmo sem mensagens novas; experimento real continua pendente por ausência de Redis acessível.

### Estado atual
- Banco/pipeline: 61 testes reais passaram (37 de base/migrations e 24 de pipeline), com reentrega, rollback, concorrência e lease antigo.
- Observações: 24 testes passaram nos adapters SQLite/PostgreSQL, usando router integrado ao app.main; Ruff passou. API local reiniciada com as novas rotas.
- Frontend base: 18 testes Vitest e build passaram; smoke desktop/mobile sem overflow ou erros inesperados. Capturas em `frontend/.impeccable/review/`.
- Backend reportou 41 testes de transporte determinístico e 10 de worker/publicação/ACK passando; experimento Redis real ainda não executado. Gates pipeline/network permanecem false.
- Retenção e SSE estão em implementação; frontend integra métricas/histórico/status pública. Commit continua impedido pela sandbox Git de Maestro.

### Próximos passos
- Concluir revisão de consultas e testes de retenção por lotes no PostgreSQL.
- Integrar SSE com verificação de sessão, sinais por proprietário e reconciliação/polling no frontend.
- Disponibilizar Redis real para `test_broker.py`, validar reclaim/ACK/falhas do broker e somente então avaliar habilitar runtime do pipeline.
- Verificar TLS/SNI/IPv6/egress e backup/restore antes de deploy público; não há deploy realizado.

## 2026-10-04 — API e persistência integradas ao frontend real

### Implementado
- Cadastro, login/logout, sessões opacas revogáveis, Argon2id, CSRF e validação de Origin.
- CRUD, arquivamento lógico e isolamento por proprietário de projetos/monitores; cotas com locks PostgreSQL, pausa/retomada e invalidação de jobs por versão.
- Sete entidades SQLAlchemy e migration Alembic inicial congelada, com FK composta para identidade do resultado, índices parciais e retenção de evidências por SET NULL.
- React/TypeScript/Vite com autenticação, gestão de projetos/monitores e dashboard que distingue saúde de freshness.
- Scripts de execução/verificação local e infraestrutura Compose com migration antes da API e Nginx no mesmo origin.

### Arquivos principais alterados
- `backend/app/main.py`, `backend/app/config.py`, `backend/app/security.py`
- `backend/app/api/auth.py`, `backend/app/api/dependencies.py`, `backend/app/api/resources.py`, `backend/app/api/schemas.py`, `backend/app/api/errors.py`
- `backend/app/services/resources.py`, `backend/app/domain/monitors.py`
- `backend/app/db/base.py`, `backend/app/db/models.py`, `backend/app/db/session.py`
- `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_initial.py`
- `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json`
- `frontend/src/App.tsx`, `frontend/src/Forms.tsx`, `frontend/src/api.ts`, `frontend/src/domain.ts`, `frontend/src/styles.css`
- `scripts/start-local.ps1`, `scripts/verify.ps1`, `compose.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`

### Decisões técnicas
- API `/api/v1` com cookie same-origin e CSRF em memória no frontend; sem JWT/localStorage.
- Transação da API usa dependency scope=function para terminar antes de enviar resposta. Updated_at de ORM é atualizado explicitamente antes de serializar para evitar MissingGreenlet.
- API local roda sem reload porque multiprocessing/named pipes são restritos nesta sessão Windows.
- Dependências instaladas com certificados do sistema, mantendo TLS verificado.

### Estado atual
- Suite backend completa reportada pelo especialista: 156 passed, 2 skips de concorrência somente SQLite; dois casos adicionais de multicast passaram depois. Maestro confirmou independentemente 107 testes API/validação e 49 testes persistência/health.
- Build/TypeScript frontend e 16 testes Vitest passaram, executados pelo especialista em seu fluxo autorizado de subprocessos.
- API em `127.0.0.1:8000`, frontend em `127.0.0.1:5173`, PostgreSQL real 18.6 isolado em `127.0.0.1:55432`. Migration aplicada ao runtime; readiness OK. Smoke de navegador em andamento.
- Docker Compose valida configuração, mas daemon/imagens não foram executados. Runtime Compose PG17 ainda não foi testado; integração real desta sessão usa PG18.6.
- Pipeline/HTTP seguro, métricas REST, SSE e status pública ainda não estão concluídos; cadastros não executam chamadas externas nesta etapa.
- Git local inicializado com autorização; staging/commit seguem impedidos pela sandbox de Maestro ao escrever `.git/index.lock`. Nenhum push.

### Próximos passos
- Banco de Dados: concluir e validar `backend/app/services/check_jobs.py`, `backend/app/monitoring/scheduler.py` e `backend/tests/test_pipeline_db.py` no PostgreSQL real.
- Backend: transporte HTTP resistente a SSRF, broker/worker/publicador com ACK após commit; depois histórico, métricas, incidentes e DTO público separado.
- Frontend: concluir smoke desktop/mobile; integrar próximos contratos REST apenas após dados reais disponíveis.

## 2026-10-04 — Regras de saúde e métricas verificadas

### Implementado
- Regras puras de transição online/degraded/offline, com threshold, retries recuperados, limiar de latência e sinalização de abertura/encerramento de incidente.
- Lacunas e pausa interrompem sequência de falhas sem recuperar monitor offline.
- Freshness independente da saúde; resumo de projeto exclui leituras antigas e monitores pausados.
- Uptime por ciclos e média/p95 interpolado apenas de latências de sucesso, em janela semiaberta limitada a 30 dias.

### Arquivos principais alterados
- `backend/app/domain/health.py`
- `backend/tests/test_health.py`
- `scripts/verify.ps1`

### Decisões técnicas
- As regras não conhecem ORM, HTTP ou filas; o pipeline deve validar identidade, versão, prazo e lease antes de aplicá-las.
- Resultados não avaliados não entram nas métricas e não fabricam falhas do alvo.

### Estado atual
- 13 testes pytest passaram; Ruff passou para os dois arquivos de regras/testes.
- PostgreSQL 18.6 real está ativo em cluster isolado local, porta 55432; migrations e testes de persistência seguem com o especialista.
- UI/API estão em validação; pipeline ainda em implementação. Commit continua impedido pela restrição de escrita no índice Git desta sessão.

### Próximos passos
- Integrar regras à finalização transacional de jobs em `backend/app/services/check_jobs.py`.
- Validar reentrega, lease antigo e concorrência no PostgreSQL; integrar transporte HTTP seguro e workers.
- Verificar cadastro/projetos/monitores no Portal `Vigil Preview` em desktop e mobile.

## 2026-10-04 — Início coordenado do projeto

### Implementado
- Analisados os quatro documentos de planejamento e o README.
- Definidos contratos iniciais de API, roadmap e divisão de propriedade entre os três agentes Maestri.
- Inicializado Git local na branch `main`, após autorização explícita do usuário.
- Criada configuração Compose inicial de PostgreSQL e Redis com portas locais e persistência.

### Arquivos principais alterados
- `.gitignore`, `.env.example`, `compose.yaml`
- `docs/API.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Commits e integração centralizados no Maestro, com agentes implementando em diretórios próprios.
- Entrega inicial cobre persistência, autenticação, projetos, monitores e dashboard sem medições fictícias.
- PostgreSQL segue como fonte de verdade; testes SQLite não substituem integração real.

### Estado atual
- Backend, frontend e migrations estão em implementação pelos agentes; ainda não são entregas validadas.
- Docker CLI está instalado, mas o daemon não estava ativo na inspeção inicial; tentativa de inicialização em andamento.
- PostgreSQL instalado foi identificado pelo especialista de banco; validação real em cluster isolado está em andamento.
- Git foi inicializado com autorização, mas a sandbox desta sessão nega escrita em `.git/index.lock`; staging e commits estão tecnicamente impedidos, sem push realizado.

### Próximos passos
- Validar e integrar entregas dos três agentes; rodar suites, build e migration PostgreSQL.
- Completar execução local e atualizar o README com comandos comprovados.
- Implementar transporte HTTP seguro e pipeline durável após a base estar validada.
