# Registro de desenvolvimento

## 2026-10-06 — Perfil gratuito online com checks em lotes

### Implementado
- Web Docker recompila React e serve SPA/API na mesma origem; bootstrap explícito
  cria somente schema privado vigil e aplica Alembic antes de iniciar a API.
- API sem Redis opt-in, runtime-config anônimo e formulário com mínimo dinâmico.
  Perfil cloud usa 900/900 segundos; defaults locais 60/null preservados.
- Runner one-shot reutiliza claim/HTTP/finalização duráveis, backlog e retries, sem
  broker Redis. Workflow público/manual/agendado 15min usa Docker protegido e relay
  TCP com hostname original e TLS verificado. Recursos próprios recebem cleanup validado.
- Factory TLS/schema/pool e Alembic privado integrados. SET SESSION no connect evita
  search_path de startup descartado pelo Neon; sem fallback public/DDL na factory.
- Timeout de conexão cloud10s/local3s; relatórios distinguem fase e deadline global.
  Retenção até10s por batch dentro do prazo90s, sem alterar TTL ou statement/lock limits.

### Arquivos principais alterados
- `backend/app/config.py`, `backend/app/main.py`, `backend/app/web.py`, `backend/app/api/runtime.py`
- `backend/app/api/resources.py`, `backend/app/services/resources.py`, `backend/app/domain/monitors.py`
- `backend/app/monitoring/batch.py`, `backend/app/monitoring/run.py`, `backend/app/monitoring/tasks.py`, `backend/app/monitoring/status.py`
- `backend/app/db/session.py`, `backend/migrations/env.py`, `backend/app/services/check_jobs.py`, `backend/app/services/retention.py`
- `backend/tests/test_batch.py`, `backend/tests/test_batch_postgresql.py`, `backend/tests/test_db_session.py`, `backend/tests/test_db_fresh_slot.py`, `backend/tests/test_pipeline_db.py`
- `backend/tests/test_runtime_config.py`, `backend/tests/test_web.py`, `backend/tests/test_retention.py`
- `frontend/src/runtimeConfig.ts`, `frontend/src/Forms.tsx`, `frontend/src/domain.ts`, `frontend/src/test/RuntimeConfig.test.tsx`, `frontend/src/test/App.test.tsx`, `frontend/src/test/Observations.test.tsx`, `frontend/src/test/fixtures.ts`
- `infra/free-cloud/Dockerfile`, `infra/free-cloud/pg_relay.py`, `infra/worker/egress.py`, `.dockerignore`, `render.yaml`, `.github/workflows/free-checks.yml`
- `scripts/free_cloud_start.py`, `scripts/free_cloud_checks.py`, `scripts/tests/test_free_cloud.py`, `docs/FREE_CLOUD.md`, `docs/API.md`, `README.md`, `backend/app/db/IMPLEMENTATION.md`

### Decisões técnicas
- Usuário escolheu Neon separado, gratuito, checks15min. Supabase Vault/VFitness e
  bancos locais preservados; não transferir dados locais automaticamente.
- Projeto Neon exclusivo vigil/lingering-water-00111721, Oregon, compute fixo0.25CU
  e scale-to-zero5min. Schema vigil no head0002; clientTLS1.3/hostname verificado.
- Render Free single instance, healthCheckPath live para evitar manter compute DB
  acordado por probes; readiness explícita no deploy. API gatesfalse, runner true/true.
- Cron best-effort sem SLA/replay de checks omitidos. Fresh slot usa clock real DB
  após locks; legado abaixo900 legível e excluído da agenda até ajuste explícito.
- Workflow somente default branch público não fork, sem PRs, checkout fixado e
  runner padrão. Secrets servidor; nenhum DSN/cookie/senha em Git ou frontend.

### Estado atual
- Banco:138 passed/zero skips em PG18 UUID autorizados, antes do ajuste de connect;
  `.cache/verification/db-cloud-neon-contracts-pg18-final.xml`, cleanup/catalog public preservados.
- Backend:183 passed/76 skips sem URLs na regressão inicial; PG18 synthetic22 passed/3
  skips SQLite-only, `.cache/verification/backend-cloud-pg18.xml`.
- Maestro final:137 passed/zero skips de schema/timeout/tooling/egress em4.87s;
  `.cache/verification/cloud-final-boundaries.xml`. API/batch/readiness83 passed/7
  variantes incompatíveis SQLite/PG skipped em180.26s; `cloud-final-api-pg18.xml`.
- Frontend:build Linux completo e Vitest real10 arquivos/95 testes passed,6.61s.
  Novo bundle index-Q0hhzUNE.js, sem reutilizar dist histórico; formulário900/900
  em1440/390 sem overflow, cópia15min e mínimo900 conferidos no portal.
- Firewall físico na imagem final:18 bloqueios, controles negativos reais, IPv4/IPv6,
  TLS/SNI/CA/hostname e NDP passed; `.cache/egress-qa/a58fbf4f57d348c0bbaa83f9a4c93fed/report.json`, cleanup confirmado.
- Neon real:bootstrap/head0002, readiness200, cadastro/login/monitor QA próprio,
  batch com1 completed/0 backlog, cleanup confirmado. HTTP example.com retornou200,
  latência74.65ms, saúde online e last_checked_at2026-10-06T17:32:03.111087Z.
  Check HTTPS anterior gravou tls_error da inspeção local, sem relaxar verificação.
- Preview QA em5180(prod)/5181(dev somente para browser local) usa banco Neon
  separado; runtime local anterior8000/5173 mantido. Ruff/diff-check aprovados.
- Serviço Render ainda não publicado e agenda GitHub desativada por variável false;
  aguarda código remoto e validação pública. Conta/projeto QA ainda existem nesta etapa.
  Sem nova execução do verify completo RequireIntegration, guardasPG17 preservadas.

### Próximos passos
- Após commit local da unidade, obter pedido explícito de push exigido pelo AGENTS;
  enviar main, publicar Render Free já preparado e validar URL HTTPS live/ready/UI.
- Validar workflow manual no GitHub contra Neon e só então ativar variável true;
  conferir rodada agendada e limites/cotas, sem adicionar cartão/upgrade.
- Arquivar projeto QA próprio e logout, remover containers QA identificados e arquivos
  privados temporários; preservar banco e credenciais exclusivamente nos secrets.
- Registrar URL/provas públicas efetivas; não chamar online/agenda de concluídos
  apenas porque build e runner local passaram.

## 2026-10-06 — Prontidão por migration e execução local

### Implementado
- Readiness exige conectividade e uma única revision Alembic igual ao head dinâmico dos arquivos instalados. Preserva liveness, deadline, cancelamento e503 sanitizado, sem aplicar migrations.
- Adicionado `start-local.ps1 frontend -Preview`, servindo build existente em5173 com proxy/API e configuração nativa Node24, sem bundling/hot reload.
- README/API/OPERATIONS documentam o ambiente local e procedimentos de reinício. Provas e regressões acompanham a correção.

### Arquivos principais alterados
- `backend/app/main.py`, `backend/app/readiness.py`
- `backend/tests/test_api_health.py`, `backend/tests/test_readiness.py`
- `scripts/start-local.ps1`, `README.md`, `docs/API.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Head resolvido via ScriptDirectory ancorado no backend, sem hardcode/CWD/conexão no startup. Probe usa apenasSELECT e respeita search_path. Confirma versão declarada, não integridade global do schema.
- Somente SQLite explicitamente injetado em testes dispensa Alembic; fixtures PG metadata sem alembic_version corretamente retornam503.
- Preview serve dist histórico e52dd02; src/public/package/config não mudaram, mesmos assets da coleta anterior. Sem novo rebuild ou equivalência criptográfica fonte→bundle nesta sessão.
- Runtime usa PostgreSQL18.6 próprio em `.cache/postgresql/data`, porta55432, API8000 e frontend5173; PostgreSQL independente5432 preservado. Redis/scheduler/worker não iniciados e gates de checks externos preservados.

### Estado atual
- Readiness final:31 passed/2 skips exclusivamente SQLite-only em4.87s; `.cache/verification/backend-local-readiness-pg18-final.xml`. Missing/empty/old/unknown/multiple/current exercitados em schemas UUID próprios; cleanup confirmado, public nohead0002 sem DDL/DML dos testes.
- Regressão offline:110 passed/49 skips de integrações semURLs, em28s; `.cache/verification/backend-local-readiness-regression.xml`. Ruff completo, diff-check e AST PowerShell aprovados; Preview iniciado pelo novo comando.
- HTTP live/ready8000 e frontend5173 responderam200; portal Vigil Preview no login. Cadastros/consultas disponíveis, com smoke jobsUI vazio descrito na entrada anterior. Redis ausente limita fanout/pipeline; checks automáticos não estão ativos.
- Build/esbuild e launch Edge restringidos por spawn EPERM; Docker sem daemon disponível. Verify completo obrigatório/campanha v3 não executados.
- Escrita Git antes bloqueada; usuário liberou commits locais e a operação foi autorizada pelo revisor do ambiente. Três unidades concluídas agrupam implementação/testes/docs em feat/fix, sem commit exclusivo de testes/log ou push.

### Próximos passos
- Quando Docker/Edge estiverem disponíveis, executar verify completo obrigatório com dependências isoladas e provas de egress/recovery; manter limites desta sessão registrados.
- Para testar checks externos, preparar Redis e scheduler/worker pelo procedimento existente e validar egress antes de habilitar ambos os gates; next_check_at não demonstra execução ativa.
- Para editar UI, voltar ao Vite normal em ambiente que permita esbuild; recompilar antes de usar Preview sobre novos sources.

## 2026-10-06 — Relatório de latência v3 com replay auditável

### Implementado
- Tooling guarda evidências projetadas de SSE/GET/DOM por atualização e oferece replay offline, sem modificar UI, transporte ou polling do produto.
- Builder exige UUID de projeto como string primitiva; corrigida aceitação de arrays/String encapsulada por coerção regex. Regressões integram a implementação.
- Contratos/documentação registram smoke jobsUI real de leitura do dataset vazio.

### Arquivos principais alterados
- `frontend/scripts/live-latency-observer.mjs`, `frontend/scripts/live-latency-observer-browser.mjs`, `frontend/scripts/live-latency-smoke.mjs`
- `frontend/scripts/live-latency-unit.mjs`, `frontend/scripts/live-latency-replay.mjs`
- `frontend/LIVE_LATENCY_V3_CONTRACT.md`, `frontend/IMPLEMENTATION.md`, `frontend/JOBS_UI_CONTRACT.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Whitelist de campos vincula run/projeto/revisão/nome QA e IDs CDP, mantendo clocks CDP e browser separados e sem copiar credenciais ou payloads privados.
- Replay comprova consistência da evidência projetada, sem autenticação criptográfica, paint, causalidade exclusiva de SSE ou instante exato de commit. Relatório v2 histórico preservado; não fabricar conversão para v3.

### Estado atual
- Sete testes Node passed/zero skips, typecheck/syntax/diff-check aprovados; `frontend/.impeccable/review/live-latency-resume-20261006/unit.tap`. Build/esbuild e launch Edge restringidos por spawn EPERM nesta sessão; aprovações anteriores são históricas.
- Smoke jobsUI real passed:17 consultas200, situações all/exhausted/expired e períodos24h/7d/30d, reload, fechamento40s sem novas leituras, reabertura default. Desktop1440/mobile390 sem overflow e controles44px.
- Owner/projeto QA privados próprios vazios; guardas owner/singleton/marker/zero-monitores passaram. Archive204 seguidoGET404/lista autenticada vazia; logout204/me401. Conta e projeto arquivado retidos pela API, sem purge/seed histórico/gates alterados.
- Evidências/capturas em `frontend/.impeccable/review/live-latency-resume-20261006/`: `jobs-api-real.json` SHA256354C17C44433F11BA8BF6D1F6C71CFC183C7579B4209B0B2E7F6E3D8874DC58C, `jobs-desktop.png`, `jobs-mobile.png`.
- Runtime serviu dist histórico e52dd02, src/public/package/config intactos. Sem novo rebuild ou campanha física v3. Dataset vazio não cobre linhas/paginação/filtro de monitor/teclado nativo/token antigo; ResourceTiming não é trace bruto dos métodos ou SLA.

### Próximos passos
- Executar primeira campanha física v3 em QA exclusivo com Docker/Edge disponíveis, seguida do replay offline; preservar v2 e cleanup.
- Em outra janela QA própria, preencher falhas exhausted/expired e validar filtro de monitor, paginação e teclado com cleanup confirmado.

## 2026-10-06 — Índices de evidência e ensaio de retenção

### Implementado
- Migration 0002 e metadata acrescentam índices parciais em opening_check_id e closing_check_id dos incidentes, corroborados por planos PostgreSQL17 históricos.
- Helper QA captura queries reais de retenção, compara EXPLAIN JSON sem ANALYZE em schema UUID próprio e só marca completed após cleanup bem-sucedido. Regressões acompanham a implementação.

### Arquivos principais alterados
- `backend/app/db/models.py`, `backend/app/db/retention_plan_qa.py`
- `backend/migrations/versions/0002_incident_evidence_indexes.py`
- `backend/tests/test_db_postgresql.py`, `backend/tests/test_db_retention_contract.py`, `backend/tests/test_db_incident_evidence_indexes.py`, `backend/tests/test_db_retention_plan.py`
- `backend/app/db/IMPLEMENTATION.md`, `backend/app/db/RETENTION_QA_CONTRACT.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Índices B-tree parciais preservam FKs, nulabilidade e regras de retenção. CREATE INDEX normal é transacional e bloqueia escritas durante construção; exige janela adequada e acrescenta manutenção/storage.
- Planos estimados não demonstram redução medida de latência ou SLA. Guardas PG17 permanecem; resultados históricos e novas provas PG18 são separados.

### Estado atual
- Histórico PG17:102 passed/zero skips em26.491s; hashes de models/migration/testesPG conferidos. Evidência em `.cache/verification/backend-retention-qa-9e7cf99f9f0f42519af3af1be88f7f8d/`.
- Banco:47 testes offline passed/zero skips em0.65s, incluindo completed/cleanup; `.cache/verification/db-retention-resume-20261006-offline-final.xml`.
- Central:102 passed/zero skips em38.41s com schemas próprios noPG18, incluindo dbpostgresql/schema/contrato/helper/retenção; `.cache/verification/local-pg18-retention.xml`. Nenhuma nova campanha de planos PG17 após o fix de cleanup.
- Banco local vigil/55432 atualizado de0001 para0002 após preflight sem outros clientes e backup `.cache/local-runtime/vigil-before-0002.dump` (138434bytes). Revision e ambos os índices confirmados; schemas temporários ausentes. Serviço independente na5432 preservado.
- Fontes liberadas pelos agentes, Ruff completo e diff-check aprovados. Permissão de commits locais liberada pelo usuário; implementação, testes e documentação integram a mesma unidade, sem push.

### Próximos passos
- Repetir helper/catálogo/retenção em PG17 exclusivo com fontes atuais quando Docker estiver disponível, preservando cleanup e hashes.
- Registrar continuidade das unidades de tooling v3 e execução local em seus commits correspondentes.

## 2026-10-05 — Verificação obrigatória de jobs e provas QA reais

### Implementado
- `verify.ps1 -RequireIntegration` exige testes PostgreSQL de jobs no JUnit; omissão ou skip real recusa a verificação. Skips exclusivos de SQLite continuam permitidos.
- API e seção Falhas do processamento do Vigil concluídas no código integrado anteriormente; contrato documentado como implementado, com projeção sanitizada, filtros e paginação somente leitura.
- Regra de commits atualizada no AGENTS: unidade concluída agrupa implementação/testes/docs, sem commits de testes ou log automáticos.

### Arquivos principais alterados
- `scripts/verify.ps1`, `AGENTS.md`
- `docs/API.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`, `frontend/JOBS_UI_CONTRACT.md`

### Decisões técnicas
- Verificação deve comprovar execução dos jobs PG, além de receber uma URL. Quatro cenários controlados do bloco PowerShell validaram presença, omissão, skip PG e skip SQLite; AST sem erros. Não foi executado o comando verify completo nesta etapa.
- Serviços QA exclusivos usam UUID/labels/IDs, limites, tmpfs e mounts readonly. Docker/Git voltaram a funcionar via revisão de permissões; bloqueios descritos nas entradas anteriores são históricos. Nenhum serviço PG18 ou gate compartilhado foi alterado.
- Campanha de carga e testes migrations/jobs são ensaios distintos: helper usa metadata; migrations reais são exercitadas em fixtures próprias. Nenhum índice especulativo ou alegação de plano/paridade global.

### Estado atual
- Backend QA token `2c11a939f92546d0aeeae1f50bd7dac1`:52 passed/zero skips em5,416s (sete jobsPG, quatro namespacePG, um Redis,40 casos puros/controlados), sete SQLite deselected. Provas RR/RO/UPDATE25006 e COUNT/página durante commit de writer distinto passaram. Migrations:29 passed/zero skips em13,427s; head0001_initial/base, tipos/UTC, constraints, identidade composta, SET NULL das duas evidências e concorrência.
- Banco revisou JUnits, log, hashes e limpeza: schemas/keys vazios antes/depois, sete fontes inalteradas; três containers, rede e imagem QA exclusivos removidos e ausência confirmada. Artefatos privados em `.cache/verification/backend-qa-2c11a939f92546d0aeeae1f50bd7dac1/`.
- Carga Taskiq/PG17/Redis/TLS: baseline100/60s e rajada100/0s com contagens completas, zero erros,13 métricas×100 amostras, commit por PID distinto antes do ACK e cleanup confirmado. Agenda commit→XACK p95:99,31ms baseline/4198,21ms rajada; máximos callbacks/HTTP1/1 e15/4. Relatórios `.cache/pipeline-load/31315bf2092c4c75923cfa9c98769b9b/` e `2d39277258f64df6b1e2a9f5aacb9a86/`. Limite50 não foi saturado; um projeto serializa locks e observadores adicionam overhead. Sem SLA/capacidade sustentada.
- UI jobs:72 Vitest/zero skips, build e seis estados Edge desktop/mobile passaram com API sintética; não prova integração dessa seção com PG real. APIjobs continua usando fixture metadata separada da fixture Alembic; nenhum EXPLAIN/volume de histórico medido.
- Coleta UI/API real `29b74cc0-09f0-406a-a5bf-232df865f8c6`:240 REST+25 PATCH medidos passed/errors0, correlacionando SSE nativo/revisão/GET posterior por requestId CDP/DOM. PATCH-start→DOM p95=264,30ms; SSE→GET p95=216,70ms. Build e52dd02/PG170011/head0001_initial/Redis, owner/projeto privado vazio e gates false; uma API não prova fanout. Cleanup API archive/logout/token antigo confirmado; depois containers e duas redes próprias removidos. API/PG/Redis internos, bridge adicional exclusiva do web para loopback. Dois preflights anteriores de binding foram limpos antes de criar conta. Evidências `.cache/verification/ui-real-e481d12e845740a58c5f8f0833bc2e08/` e `frontend/.impeccable/review/live-latency/<UUID>/report.json`. Quantis nearest-rank, polling mantido, sem tempo exato commit→DOM/SLA.
- Frontend aprovou revisão readonly da coleta real e recalculou todos os quantis/contagens independentemente. O JSONv2 guarda flags/deltas, sem requestIds e timestamps CDP brutos: reconstrução independente de cada pareamento exige mais evidência; a revisão também conferiu fontes do observador. Sem sobreposição periódica observada não significa causalidade exclusiva.

### Próximos passos
- Integrar prova de leitura da seção jobs no navegador contra schema Alembic real em nova janela QA exclusiva; a coleta concluída mede projeto vazio/REST/SSE, com jobs fechado.
- Antes de otimizar histórico ou retenção, executar o contrato de planos PG17 com volume representativo em `backend/app/db/RETENTION_QA_CONTRACT.md`; não inferir ganho dos índices candidatos.
- Executar verify completo obrigatório em janela isolada com todas as dependências; esta etapa não substitui provas de fanout/réplicas/firewall/recovery do restante da suíte.

## 2026-10-05 — Logo de olho e favicons do Vigil

### Implementado
- Marca vetorial de olho aplicada no login, dashboard, abertura de sessão e status pública. Componente Brand compartilha símbolo decorativo e nome textual acessível, preservando destinos dos links.
- Logo com lettering Public Sans Bold em contornos, PNG transparente de 1024px, favicon SVG e ICO de 16/32px, além de ícone de 180px para tela inicial.

### Arquivos principais alterados
- `frontend/src/Brand.tsx`, `frontend/src/App.tsx`, `frontend/src/Forms.tsx`, `frontend/src/Observations.tsx`, `frontend/src/styles.css`
- `frontend/public/brand/vigil-eye.svg`, `frontend/public/brand/vigil-logo.svg`, `frontend/public/brand/vigil-logo.png`, `frontend/public/brand/README.md`, `frontend/public/brand/PUBLIC-SANS-LICENSE.txt`
- `frontend/public/favicon.svg`, `frontend/public/favicon.ico`, `frontend/public/apple-touch-icon.png`, `frontend/index.html`
- `frontend/DESIGN.md`, `frontend/.impeccable/design.json`, `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Olho geométrico mantém verde profundo e tipografia existentes. Favicon em negativo é simplificado para tamanhos pequenos; símbolo estático não comunica saúde ou atividade de monitor.
- SVG da logo é independente de fontes externas; Public Sans já instalada foi convertida em contornos com ferramenta temporária, sem adicionar dependência ao produto. PNG/ICO são renderizações dos SVGs autorais.
- Ícone da aplicação tem alt vazio/aria-hidden para evitar nome duplicado. Links mantêm foco visível e área mínima de 44px, com olho de 36px.

### Estado atual
- Central: 72 Vitest passed/zero skips, TypeScript/Vite build aprovado. Edge154 verificou login/dashboard/status pública em 1440 e 390: seis capturas, assets carregados, sem overflow/erros, nome/destinos/foco preservados e altura de 44px.
- Frontend fez revisão visual read-only das seis montagens e da prancha da identidade, sem bloqueadores. Evidências em `frontend/.impeccable/review/branding/`; ICO decodificado no navegador.
- Essas capturas usam API sintética isolada, sem alegar smoke físico do produto. A seção de jobs também passou nos seis estados desktop/mobile, com `processing-failures/report.json` final aprovado.

### Próximos passos
- Reutilizar os assets e o componente Brand nas próximas superfícies; preservar nome acessível, destinos e área de foco.
- Continuar provas PG17/Redis dos jobs e helper em QA exclusivo; registrar campanha física e limites separadamente.

## 2026-10-05 — Relatório de carga exige tipos inteiros do protocolo

### Implementado
- Corrigida aceitação de booleano/decimal no identificador de versão, limites configurados de concorrência e UID do relatório QA. O runner exige inteiros JSON além dos valores esperados.

### Arquivos principais alterados
- `scripts/pipeline_load_check.py`, `scripts/tests/test_pipeline_load_check.py`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Igualdade numérica do Python não valida o tipo do protocolo: true == 1 e 1.0 == 1. A recusa de tipos incorretos complementa as guardas existentes de contagens, quantis, ordem, identidade e cleanup.
- Versão 1, limites 50/5/50 e UID10001 permanecem; não houve alteração no helper, infraestrutura ou runtime.

### Estado atual
- Sete entradas indevidas reproduzidas antes da correção, em `.cache/verification/load-protocol-types-before.xml`. Depois, 49 testes do runner passaram em 0,14s; Ruff check/format aprovados. JUnit `.cache/verification/load-protocol-types-after.xml`.
- Regressão de guardas de egress/proxy/carga: 95 passed/1 deselected em 0,18s; o caso de diretório temporário foi excluído por restrição de ACL já identificada. JUnit `.cache/verification/load-protocol-guards-regression.xml`; lint completo de scripts/infra aprovado.
- São provas de parsing e guardas com recursos controlados, não campanha física PG17/Redis/TLS. Commit local continua impedido pela escrita em `.git`.

### Próximos passos
- Executar a campanha real com o helper v1 de 13 fases quando o terminal tiver acesso ao Docker; preservar os relatórios e validar cleanup.
- Integrar testes à unidade do runner/fix, sem commit exclusivo de testes.

## 2026-10-05 — Contrato de leitura de falhas do processamento

### Implementado
- Acordado o contrato privado de leitura de jobs exhausted/expired, com filtros, paginação, projeção sanitizada e janela de agenda. API e interface ainda estão em implementação.
- Frontend documentou DTO e léxico estático; Banco revisou população da query, snapshot, autorização e limites dos índices existentes sem alterar persistência.

### Arquivos principais alterados
- `docs/API.md`, `docs/DEVELOPMENT_LOG.md`
- `frontend/JOBS_UI_CONTRACT.md`, `frontend/IMPLEMENTATION.md`
- Fontes em implementação: `backend/app/api/jobs.py`, `backend/app/services/operational_jobs.py`, `backend/app/main.py`.

### Decisões técnicas
- Default all reúne somente exhausted/expired. Pausados entram e arquivados não. A leitura não modifica jobs, saúde ou incidentes e não depende de Redis.
- Autenticação termina antes do snapshot de observação; owner/projeto/monitor, COUNT e itens usam a mesma leitura. Projeção SQL impede carregar configuração privada no DTO; códigos desconhecidos viram null.
- Janela usa scheduled_at, retenção usa finished_at e elegibilidade. Snapshot de uma resposta não estabiliza páginas entre requests; COUNT/OFFSET não têm custo limitado pela quantidade de itens. Nenhuma migration especulativa.
- Recuperação de manifesto QA permanece apenas proposta: não implementar journal/publisher/reseed nesta etapa. Arquivo e PostgreSQL não têm commit atômico conjunto.

### Estado atual
- Contrato confirmado pelos três agentes. Backend implementa API/testes; Frontend implementa componente isolado contra fixture exata, aguardando freeze para revisão integrada. Ainda não há evidência de funcionamento da feature de jobs.
- Central confirmou a baseline das unidades anteriores: 174 passed/5 skips de integrações PG/Redis, mais 7 testes Node sem skips e TypeScript aprovado. JUnit `.cache/verification/contracts-jobs-integration-baseline.xml`. Isso não valida a API nova.
- Regressão central de compatibilidade com o router registrado: 62 passed/3 skips que exigem PG/56 deselected, em 124,38s; JUnit `.cache/verification/api-compatibility-jobs-router.xml`. Banco compilou COUNT/página em dialect PostgreSQL sem conexão, confirmou join inequívoco e oito campos; não é plano ou teste RR/RO real.
- Docker e Git seguem sem acesso de escrita/pipe neste terminal; testes físicos e commits locais continuam pendentes.

### Próximos passos
- Revisar e executar `backend/tests/test_operational_jobs.py` após liberação do Backend; exigir isolamento, fronteiras, whitelist, zero efeitos e provas PG separadas.
- Liberar consumo do DTO congelado ao Frontend; validar componente, mensagens, GET apenas, troca de projeto, teclado e mobile com fixture própria.
- Atualizar esta documentação para implementado somente após os testes correspondentes; executar PG17 RR/RO e smoke físico quando a infraestrutura estiver acessível.

## 2026-10-05 — Filtros de qualidade na lista de monitores

### Implementado
- Seletor Todos/Atualizados/Desatualizados/Sem dados/Pausados combinado com busca de nome/URL, usando freshness atual e clock15s existente; não filtra pela saúde histórica.
- Contagem do snapshot fora de aria-live, reset ao trocar projeto, estados vazios distintos e Limpar filtros com retorno de foco à busca. Pausa/retomada pode retirar item do filtro sem alterar a seleção.

### Arquivos principais alterados
- `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/test/MonitorFilters.test.tsx`
- `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Filtragem local sobre snapshot do projeto, sem API/busca global ou inferência de disponibilidade. Timer existente permite envelhecer dados sem nova resposta HTTP.

### Estado atual
- Frontend entregou64 Vitest passed/zero skips em7,84s, TypeScript/build/whitespace aprovados; seis regressões de filtros.
- Edge154 com build e API sintética próprios passou todas as opções, foco/teclado/reset em1440/390, sem overflow/erros. Controles mobile44px ou mais; relatório `frontend/.impeccable/review/monitor-filters/report.json`. Não é prova do produto8080/PG real.
- Maestro confirmou typecheck e revisão de lógica/reset; unidade liberada sem alterações de auth/polling/API. Commit permanece impedido por Git readonly.

### Próximos passos
- Smoke físico da lista após readiness com owner exclusivo, preservando checks externos desligados.
- Alinhar DTO exato e implementar leitura de falhas operacionais do Vigil em seção separada dos incidentes do alvo, sem retry/mutação.

## 2026-10-05 — Configuração recusa portas de origem inválidas

### Implementado
- Settings valida a porta explícita da origem HTTP(S), rejeita zero/vazia/não numérica/fora do intervalo e sanitiza erros de parsing IPv6. Strings não são normalizadas; defaults e regra HTTPS de produção preservados.

### Arquivos principais alterados
- `backend/app/config.py`, `backend/tests/test_validation.py`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- urlsplit não validava porta sem acessar parsed.port; a validação agora ocorre no startup para impedir configuração de origem inviável.

### Estado atual
- Oito entradas indevidas aceitas antes, com regressão registrada. Central66 passed/zero skips em0,12s; nove negativos e oito positivos novos, incluindo IPv6/portas1/65535. JUnit `.cache/verification/origin-port-central.xml`; Ruff aprovado.
- Nenhum endpoint, DB, gate ou processo foi alterado. Git readonly mantém commit pendente.

### Próximos passos
- Preservar origens explícitas válidas e produção HTTPS na próxima verificação de API.
- Finalizar feature de jobs operacionais readonly em módulo separado, sem introduzir política Redis ou migration especulativa.

## 2026-10-05 — Seed QA recusa diretório inválido antes do banco

### Implementado
- `run_seed` valida/cria o diretório pai do manifesto antes de criar engine, evitando fixture commitada para esse erro determinístico de filesystem.
- Regressão usa pai que é arquivo real e proíbe engine; erro/cancelamento com transações controladas confirma saída/rollback/dispose sem manifesto.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`, `backend/tests/test_db_qa_seed_preflight.py`
- `backend/app/db/IMPLEMENTATION.md`, `backend/app/db/RETENTION_QA_CONTRACT.md`, `docs/DEVELOPMENT_LOG.md`
- `AGENTS.md` registra preferência atual por commits de feat/fix, com testes acompanhando a unidade e sem commit exclusivo de testes.

### Decisões técnicas
- Mudança restrita à ordem; open exclusivo e conteúdo do manifesto preservados. Arquivo/PG não são atômicos: I/O/cancelamento após commit ainda pode deixar owner QA isolado.
- Auditoria estrutural registra que FK de evidência garante existência, enquanto finalize/seed garantem mesmo monitor; não foi encontrado vetor público para fornecer IDs de evidência.

### Estado atual
- Banco entregou38 passed/2 skips PG em0,59s. Central preflight/contratos/schema/validação aninhada30 passed/zero skips em0,50s; JUnit `.cache/verification/seed-preflight-central.xml`, Ruff/whitespace aprovados.
- Nenhum seed real, manifesto anterior, schema/migration/serviço ou PG18/runtime foi alterado. Commit local segue bloqueado pela escrita em `.git`.

### Próximos passos
- Repetir testes reais do seed em schema UUID PG17/migrations próprio, sem renovar manifesto/public existente.
- Manter limite pós-commit explícito; discutir fluxo de publicação do manifesto somente com teste de falhas real e preservação de recursos exclusivos.

## 2026-10-05 — Janelas de observação rejeitam epoch implícito

### Implementado
- Tipo de query compartilhado nas quatro rotas privadas de checks/métricas/incidentes rejeita epoch em segundos/milissegundos antes da coerção Pydantic; preserva ISO, offsets, defaults e regras de janela do serviço.
- Respostas422 mantêm apenas query.from/to e tipo do erro, sem valores/contexto privados.

### Arquivos principais alterados
- `backend/app/api/observations.py`, `backend/tests/test_observations.py`
- `docs/API.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Corrige aceitação silenciosa de formatos fora do contrato ISO, sem alterar DTOs, serviço, banco ou política de queries desconhecidas. Incidentes públicos aceitam somente period/state/limit/offset, sem janela from/to explícita.

### Estado atual
- Duas falhas HTTP reproduzidas antes do fix, com200 para epoch segundos/ms. Central final direcionada16 passed/7 PG skips/22 deselected em15,86s; nove formatos puros e sete casos HTTP/SQLite. JUnit `.cache/verification/window-epoch-central.xml`.
- Backend entregou regressão49 passed/1 skip SQLite snapshot/38 deselected em52,98s. Readiness ASGI controlada confirmou erro/timeout503 sanitizado e propagação/cleanup de cancelamento; não é prova de driver/pool PG.
- Ruff/format/whitespace aprovados; integração PG pendente e commit bloqueado pela sessão Git readonly.

### Próximos passos
- Repetir testes reais PG17 após liberação de infraestrutura; preservar ISO-Z/-03, sanitização e janelas antigas.
- Continuar revisão de API sem introduzir política de rate limiting antes de coordenar contrato/falha Redis e validar integração real.

## 2026-10-05 — Mensagens de autenticação em português

### Implementado
- Login com invalid_credentials mostra orientação genérica ptBR, sem distinguir conta/senha. Erros conhecidos de sessão/CSRF/origin/browser/JSON e fallback401/403 usam mensagens estáticas, sem ecoar message/details do servidor.
- Transporte, ApiError, cookies, callbacks de sessão e contrato do backend preservados.

### Arquivos principais alterados
- `frontend/src/api.ts`, `frontend/src/test/api.test.ts`, `frontend/src/test/AuthErrors.test.tsx`
- `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Tradução usa código estável do backend; login401 não invalida sessão pelo callback reservado às leituras privadas. Outros erros desconhecidos conservam comportamento anterior.

### Estado atual
- Frontend entregou58 Vitest passed em8,14s e TypeScript/Vite build aprovados; cobre nove traduções com sentinelas, login401 e alerta acessível do formulário.
- Maestro confirmou oito mappings sanitizados e login401 sem callback mediante compilação TypeScript/Node local; typecheck aprovado. Não executado login físico da API nesta unidade. Git readonly impede commit local.

### Próximos passos
- Validar formulário/login no smoke real em owner exclusivo quando readiness estiver disponível; não usar transporte isolado como evidência física.
- Concluir filtro de qualidade dos monitores com contagem/foco/reset e verificação desktop/mobile, em unidade feat separada.

## 2026-10-05 — Sincronização acessível e coleta passiva SSE

### Implementado
- Topo do dashboard mostra conexão, fallback30s, espera durante ação e última consulta de monitores bem-sucedida. Horário conserva em erro, reinicia ao trocar projeto e fica fora da região anunciada.
- Coletor QA correlaciona requestId CDP, sinal/revisão, GET posterior e DOM; prepara240 leituras REST e25 atualizações em owner/projeto privado vazio exclusivo. Guardas e métodos de quantis documentados no relatóriov2.

### Arquivos principais alterados
- `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/test/SyncStatus.test.tsx`
- `frontend/scripts/live-latency-smoke.mjs`, `frontend/scripts/live-latency-observer.mjs`, `frontend/scripts/live-latency-unit.mjs`, `frontend/scripts/live-latency-observer-browser.mjs`
- `frontend/package.json`, `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Conexão/consulta da UI não representa saúde nem horário de check. Somente modo muda dentro de role=status; horário não anuncia ticks.
- PATCH-start→DOM é limite superior, não medição exata commit→DOM. SSE→GET usa um clock CDP; polling permanece ativo e pode tornar causalidade ambígua. Não combinar percentis por rota nem quantis desta amostra vazia com carga de worker.

### Estado atual
- Frontend entregou47 Vitest passed, TypeScript/build aprovados,7 Node e1 Edge em fixture sintética própria; seis estados desktop1440/mobile390 passaram sem overflow/erros. Captura mobile revisada centralmente; relatório `frontend/.impeccable/review/sync-ux/report.json`.
- Maestro confirmou7 Node/zero skips e TypeScript/sintaxe. Vitest/build/Edge no terminal Maestro bloqueiam spawn EPERM; evidências do Frontend são identificadas separadamente.
- Nenhum smoke de latência do produto8080 nem latência de pipeline foi medido nesta unidade. Git local bloqueado pelo sandbox read-only de `.git`; nenhum commit/push alegado.

### Próximos passos
- Confirmar readiness da API/UI reais em terminal com acesso Docker e executar `test:latency` com janela liberada/owner novo. Preservar archive/logout e relatório privado; não renovar seed anterior.
- Concluir correção ptBR de erros de autenticação em `frontend/src/api.ts` com regressões, separada da sincronização e do tooling.

## 2026-10-05 — Guardas de carga e auditoria offline de retenção

### Implementado
- Helper/runner QA observa13 fases de agenda/publicação/claim/commit/ACK com contagens, backlog, concorrência, CPU/RSS e limites de amostragem; namespace UUID, CA fixture e serviços PG17/Redis/TLS descartáveis próprios.
- Runner exige identidade/protocolov1, ordem, commit visível em conexão distinta antes do ACK, todas as amostras/quantis finitos e cleanup; booleanos JSON não substituem contagens numéricas.
- Verificador obrigatório inclui campanha/guardas PG/Redis e coletor Edge; recusa daemon Docker inacessível antes de testes caros/recursos, com mensagem sanitizada.
- CLI offline compara somente FKs de evidência e índices de incidents com SQL Alembic real; registra investigação antes/depois sem alterar models/migrations.

### Arquivos principais alterados
- `backend/tests/helpers/pipeline_load_process.py`, `backend/tests/test_pipeline_load.py`
- `scripts/pipeline_load_check.py`, `scripts/tests/test_pipeline_load_check.py`, `infra/worker/qa_pipeline_load.py`, `scripts/verify.ps1`
- `backend/app/db/audit_retention_contract.py`, `backend/tests/test_db_retention_contract.py`, `backend/app/db/RETENTION_QA_CONTRACT.md`, `backend/app/db/IMPLEMENTATION.md`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Metadata da fixture não valida migrations/head. Verifier por ACK/sampler alteram custo observado; locks de um projeto serializam writes. Percentis de fases não são somáveis; backlog máximo é amostrado e não SLA.
- Auditoria offline tem escopo explícito e recusa ALTER/DROP; ausência de índice inicial apoia investigação, sem provar scan/custo/ganho ou justificar migration especulativa.

### Estado atual
- Central final:105 passed/5 skips obrigatórios ainda não executados (quatro PG17 e um Redis), em1,06s, JUnit `.cache/verification/qa-contracts-central-final.xml`. Runner42, helper39 e contratos/schema24 passaram localmente; Ruff/config do backend/format aprovados.
- Preflight PowerShell aprovado com daemon ausente, versão inválida/válida simuladas e recusa real do pipe, sem iniciar campanha. Tooling parcial completo117 passed/3 skips/2 falhas/4 erros de restrições em pipes/tmp do sandbox; não é aprovação global.
- Campanha física100/60s e negativos PG/Redis atuais continuam pendentes. Docker aberto pelo usuário, pipe negado no Maestro; nenhum startup compartilhado, gate ou PG18 foi alterado. Infra TLS nova ainda precisa da prova Linux real.
- Auditoria confirma head0001_initial e FKs nullable/SET NULL para check_results, sem candidato B-tree inicial nas duas evidências; nenhum SET NULL/plano/otimização real medido. Git bloqueado; não houve commit/push desta unidade.

### Próximos passos
- Liberado acesso ao daemon/Git no terminal, executar verificação obrigatória Linux/PG17/Redis e campanha100 jobs/60s; exigir cleanup confirmado e preservar todos os relatórios de falhas anteriores.
- Executar ensaio de retenção descrito em `backend/app/db/RETENTION_QA_CONTRACT.md` antes de decidir índices/migration; não conectar PG18.

## 2026-10-05 — Validação422 não ecoa nomes JSON extras

### Implementado
- Handler remove do caminho o nome de campo extra controlado pelo cliente; conserva envelope422 e caminhos de campos declarados/índices numéricos.
- Regressões HTTP cobrem cadastro/login, objetos aninhados, erro de parsing JSON e contexto privado de validador.

### Arquivos principais alterados
- `backend/app/api/errors.py`, `backend/tests/test_auth.py`, `backend/tests/test_validation_errors.py`
- `docs/API.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- `extra_forbidden` aponta para o objeto pai; valores/input/contexto permanecem ausentes. Schemas e respostas de sucesso não mudam.

### Estado atual
- Duas regressões de auth falharam antes do fix. Revisão central: auth/validation/observability74 passed/25 skips PostgreSQL em8,02s; três casos aninhados passed em0,05s. Ruff e whitespace aprovados. JUnit `.cache/verification/validation-field-review.xml` e `validation-nested-review.xml`.
- Central parcial anterior:275 passed/214 skips e2 falhas TLS físicas no Windows; peer substituído por Avast, conforme diagnóstico do Backend. Trust não foi alterado. Nenhuma integração PG/Redis desta unidade foi alegada.
- Docker Desktop aberto pelo usuário, mas terminal Maestro recebe permission denied no pipe; provas de carga/retention PG17 continuam pendentes. Sem alteração de gates ou PG18.

### Próximos passos
- Integrar tooling de carga e observação SSE após revisão local; registrar separadamente resultados sintéticos e campanha real ainda pendente.
- Rodar verificação obrigatória Linux/PG17/Redis quando o terminal autorizado tiver acesso Docker; não tratar skips ou interceptação TLS como aprovação global.

## 2026-10-04 — Regressão do seed QA verifica dados commitados

### Implementado
- Testes do tooling existente verificam owner exclusivo, preservação de dados anteriores, hash de login, leitura autenticada pela API, paginação de72 checks/36 incidentes encerrados e exclusão da sentinela privada nos DTOs públicos.
- Métricas/buckets/p95 têm esperados independentes; rollback do chamador remove somente a nova fixture. Guarda de manifesto existente impede abertura/escrita sem depender de ACL de temporários no Windows.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`, `backend/tests/test_db_qa_seed.py`, `backend/app/db/IMPLEMENTATION.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Produto e comportamento do seed permanecem; import sys explícito substitui import dinâmico. Os testes usam migrations/schema PG17 efêmero e HTTP ASGI local, sem checks externos.
- Não repetir seed em public nem renovar manifesto privado/freshness somente para revisar entrega já integrada.

### Estado atual
- Banco entregou13 passed/zero skips em3,69s e Ruff/format; revisão central confirmou13 passed/zero skips em3,52s no PG17/55433, JUnit `.cache/verification/qa-seed-review.xml` e Ruff aprovado.
- PG17 anterior: schema/migrations/pipeline/retention90 passed/zero skips em59,82s, migration0001_initial(head). Nesta revisão nenhum seedCLI/public, novo smoke ou alteração do manifesto existente; PG18 preservado.
- Limites: ASGI não é navegador; proteção de manifesto verifica recusa antes de I/O, sem medir ACL real. Falha de gravação do manifesto depois do commit ainda pode deixar owner QA isolado.

### Próximos passos
- Concluir campanha Taskiq/PG17/Redis/TLS em serviços descartáveis próprios: Backend possui helper/teste; Maestro servidor/rede/runner e integração. Sem modelos/migrations ou escrita no runtime PG18.
- Medir agenda/publicação/claim/commit/ACK separadamente e reportar limites da amostragem de CPU/RSS; gates compartilhados continuam false.

## 2026-10-04 — Cleanup QA valida recursos antes de remover

### Implementado
- Ensaio egress valida rede internal/UUID, IDs Docker, labels e interfaces de todos os containers conhecidos, além dos endpoints da rede, antes da primeira remoção.
- Revalida cada container e remove por ID imutável; revalida identidade e endpoints da rede antes de removê-la por ID. Divergências preservam recursos e tornam o ensaio falho com cleanup pending_review.

### Arquivos principais alterados
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Nomes literais servem somente para inventário/inspeção; remoção usa identidades capturadas para reduzir risco de reutilização de nome.
- Rede não internal, interfaces estrangeiras ou endpoint inesperado já presente bloqueiam todas as remoções. Docker não oferece transação para esse conjunto: mudança tardia pode deixar containers próprios removidos e rede preservada para revisão.

### Estado atual
- Tooling completo:91 passed/zero skips em21,35s, incluindo Edge real, guardas de pré-validação e identidade/endpoint alterados durante cleanup. JUnit `.cache/verification/egress-cleanup-tooling.xml`; Ruff/format passaram nos arquivos modificados.
- Ensaio físico com política/fixture existentes passou firewall/TLS/NDP e confirmou cleanup em `.cache/egress-qa/08c67177d9ff437a867c3d32e837f75f/report.json`; nenhuma rede QA rotulada permaneceu.
- Backend/produto/infra de runtime não mudaram; baseline central anterior433 backend/16 skips SQLite e44 frontend permanece. Gates compartilhados false, PG18 preservado.

### Próximos passos
- Coordenar com Backend helper Taskiq/PG17/Redis/CheckExecutor TLS real para carga em fixtures exclusivas, medindo etapas e backlog; Maestro mantém rede/servidor/runner/relatório.
- Banco finaliza correção pendente do seed QA com testes antes de staging centralizado. Frontend liberado, sem repetir manifesto/smoke expirado sem mudança.

## 2026-10-04 — Heartbeat persistido de ticks concluídos

### Implementado
- Scheduler/publicador observa ticks após commit/publicação e grava hash por stream/group com clock Redis e TTL120s em script atômico. Falha preserva último sucesso/counts.
- Telemetria tem prazo1s, client sem retry e erro JSON sanitizado sem impedir próximos ticks. Cancelamento externo propaga; gate false não cria cliente.
- Diagnóstico readonly observa terceira fonte: last_success/attempt ages, TTL, duração/counts e estados fresh/stale/tick_failed/missing/clock_skew; não inicializa nem renova chave.

### Arquivos principais alterados
- `backend/app/monitoring/heartbeat.py`, `backend/app/monitoring/publisher.py`, `backend/app/monitoring/run.py`, `backend/app/monitoring/status.py`, `backend/app/observability.py`
- `backend/tests/test_scheduler_heartbeat.py`, `backend/tests/test_pipeline_status.py`, `backend/IMPLEMENTATION.md`
- `scripts/verify.ps1`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Identidade JSON stream/group hash SHA256 evita colisão por delimitadores e nomes privados no relatório. Chave única agrega schedulers desse par, sem criar labels por processo.
- TIME do servidor evita comparar relógios de aplicação; timestamps futuros ficam clock_skew/idade null. Fresh significa último sucesso até5s, não liveness da API; ausência após TTL não inventa sucesso.
- Contagens são do último sucesso completo. Tentativa com falha conserva esse histórico e renova TTL; erro de observação não altera persistência do pipeline nem gates.

### Estado atual
- Direcionada inicial28 passed/sem skips; integração/regressão46 passed/5 skips apenas SQLite em30,62s. Primeira central:432 passed/16 skips SQLite e um timeout de admissão TCP da fixture na rajada fria de40 conexões Redis. Relatório preservado em `.cache/verification/heartbeat-central-first.xml`.
- Fixture ajustada para dois writers/reader, três sockets reutilizados e TaskGroup com cleanup;40 escritas/leituras paralelas mantêm prova de atomicidade, sem relaxar prazos do runtime. Final30 passed/sem skips no Windows4,73s/Linux3,89s.
- Central final aprovada:433 backend/16 skips apenas SQLite em245,05s,85 tooling/20,26s e44 frontend;18 casos heartbeat/12 status, zero skips obrigatórios. Ruff/TypeScript/build/Compose/whitespace/firewall/TLS/NDP/DNS Nginx passaram. Cleanup confirmado em `.cache/egress-qa/fdcbf05f68de4f6092df32584171c4ec/report.json` e `.cache/proxy-qa/12431c42864c423abde9105e488bd631/report.json`.
- Provas Redis UUID: sucesso→falha conserva último sucesso, TTL expira de verdade, leituras não renovam chave,40 escritas em dois writers com reader paralelo preservam pares atômicos, namespaces distintos não herdam heartbeat e dados inválidos são sanitizados.
- Prova PG17+Redis confirma publicação já commitada ao observar tick. Entrypoint configurado somente no teste usa schema/fila exclusivos vazios, registra heartbeat sem checks; entrypoint false recusa conexão. Diagnóstico runtime readonly confirmou ausência esperada com gates false.
- CLI final passou também em Linux sem privilégios/código readonly com fila/heartbeat ausentes e gates false. API não foi reiniciada nesta unidade; fontes foram montados somente no container diagnóstico. Nenhum scheduler/worker compartilhado foi iniciado; PG18 preservado. Limites: agregado por fila/grupo, sem saúde por processo/worker, histórico/exporter/carga/SLA; telemetria em falha pode somar1s ao ciclo.

### Próximos passos
- Harden cleanup do ensaio egress em `scripts/egress_check.py`: validar rede internal/UUID, todas as interfaces dos containers e endpoints inesperados antes de remover qualquer recurso; preservar recursos divergentes para revisão.
- Provar carga end-to-end controlada com executor TLS real contra fixtures isoladas e medir atraso/backlog/recursos, mantendo checks externos desligados.

## 2026-10-04 — Diagnóstico read-only de backlog e leases

### Implementado
- CLI privado agrega jobs pending/running/publicação/retry/leases com clock PG e transação REPEATABLE READ/READ ONLY; consultas têm limites de tempo sem row locks.
- Redis distingue stream retido, lag não entregue e ACK pendente em leitura atômica. PEL amostrada em100 menores IDs, com truncamento e medidas exclusivamente da amostra; não faz ACK/reclaim nem cria fila.
- Fontes independentes preservam dados saudáveis em falha parcial, emitindo códigos sanitizados e exit1. Configuração inválida não revela credenciais; não importa tasks nem ativa checks.

### Arquivos principais alterados
- `backend/app/monitoring/status.py`, `backend/tests/test_pipeline_status.py`, `backend/IMPLEMENTATION.md`
- `scripts/verify.ps1`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- pending_due mede elegibilidade temporal, sem alegar autorização/configuração/orçamento suficiente para claim. Contagens de leases/publicação respeitam cutoffs <=now/30s; idade sem população e lag Redis desconhecido ficam null.
- XLEN inclui ACKados; PEL e lag não são intercambiáveis. Não usa XPENDING IDLE, que pode percorrer toda PEL. Consumers registrados não significam processos vivos.
- Nenhum heartbeat foi inventado a partir de jobs; scheduler informa not_implemented/idade null. Flags refletem Settings do CLI e não processos alheios.

### Estado atual
- Direcionada status/observability/publisher/pipeline_db/broker_integration:57 passed/7 skips apenas SQLite em56,38s;12 testes novos. Ruff aprovado, integração central inclui o módulo obrigatório. Relatório `.cache/verification/pipeline-status.xml`.
- Provas PG17/schema UUID: dados intactos, row locks não bloqueiam consulta e DML injetada é rejeitada em read-only. Redis UUID:150 pendentes/amostra100, ACK100 conserva XLEN160 e reduz PEL50, lag10 separado; lag desconhecido não vira zero.
- CLI passou no Windows e Linux UID/GID10001/caps removidas/código readonly contra runtime PG17/Redis com gates false, zero jobs e stream ausente. Conexão Redis local indisponível retornou partial/exit1, preservando snapshot PG; sem mensagens privadas/URLs/DSN no JSON.
- Sem alterações nos processos/dados PG18 nem startup do pipeline. Limites: não há atomicidade entre fontes, benchmark de volume, métricas históricas/exporter ou heartbeat persistido; status ok indica consulta bem-sucedida, não saúde do pipeline.

### Próximos passos
- Persistir heartbeat de tick concluído do scheduler em chave exclusiva com TTL, distinguir falha/ausência/idade sem confundir com liveness/readiness da API.
- Provar carga end-to-end controlada com executor TLS real somente contra fixtures isoladas, incluindo atraso de início/backlog e recursos; checks externos seguem desligados.

## 2026-10-04 — Nginx acompanha mudança de IP da API

### Implementado
- Upstream compartilhado com resolução periódica do DNS Docker para `/api/` e `/health/`, mantendo URI/headers e SSE sem buffering.
- Prova física em rede internal UUID move alias api entre listeners vivos de IPs distintos, verifica nova rota sem reload/restart e primeiro frame SSE antes da conclusão do corpo.
- Guardas recusam mutação/cleanup de redes ou containers estrangeiros; integração obrigatória inclui o ensaio. Smoke CRUD identifica rota/fase e correlaciona GET401 privado somente após logout real.

### Arquivos principais alterados
- `frontend/nginx.conf`, `frontend/scripts/browser-smoke.mjs`, `frontend/IMPLEMENTATION.md`
- `infra/web/qa_upstream.py`, `scripts/proxy_recovery_check.py`, `scripts/tests/test_proxy_recovery.py`, `scripts/verify.ps1`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Shared zone/server resolve usa resolver127.0.0.11, validade5s e timeout2s; evita manter o IP inicial indefinidamente sem prometer atualização instantânea.
- A API antiga permanece viva/alcançável: voltar a receber HTTP200 não basta como evidência, o proxy precisa retornar a identidade da substituta. PIDs master/workers e StartedAt devem permanecer iguais.
- 401 de métricas durante revogação foi reproduzido; o smoke exige resposta GET401 da mesma rota/origem após pedido POST logout e não silencia erros durante o workflow.

### Estado atual
- Configuração anterior manteve 27 respostas da antiga por12s mesmo após DNS apontar só à substituta. Corrigida recuperou em3,534s, primeiro frame SSE16ms, mesmos PIDs e cleanup confirmado: `.cache/proxy-qa/fc6a94fe23394f29986c0498525b9c00/report.json`.
- Tooling85 passed/sem skips em19,63s com PG17/Redis/Edge; Ruff, Compose, whitespace e nginx -t aprovados. Guards novos são8 casos. Não foi repetida a suíte backend/produto JS, que não mudou; baseline central anterior403 backend/16 skips apenasSQLite e44 frontend.
- Web atualizado isoladamente; Edge8080 passou CRUD/history/no_data/status pública/404, desktop1440/mobile390 sem overflow e SSE connected/project.updated/periodic/REST/revogação. API/PG17/Redis preservados, gates false e nenhum sinal/alteração no PG18.
- Limites: troca de alias IPv4 em Docker local/fixtures sintéticas, sem SLA, balanceamento produtivo, migração de streams já abertos, failover de host ou TLS externo.

### Próximos passos
- Implementar snapshot operacional read-only de backlog/PEL/leases e idade de ticks, sem endpoint público nem labels de alta cardinalidade.
- Provar carga controlada end-to-end do pipeline com executor TLS real somente contra fixtures isoladas, mantendo checks externos desabilitados.

## 2026-10-04 — Correlação HTTP e logs JSON de atividade

### Implementado
- Middleware ASGI puro gera X-Request-ID e registra tempo até headers/término com template declarado; requests concorrentes não compartilham contexto, SSE não é bufferizado e cancelamento propaga.
- Formatter limita eventos/fields/códigos, valida UUIDs/números e ignora args/exceções/body/headers/query/URLs/SQL. Sink OSError/ValueError não altera resposta/commit/ACK.
- Worker registra claim/atraso, finalização após commit, recusa/cancelamento/falha persistente; scheduler registra contagens/duração por tick. CMD API desliga access log Uvicorn com URI/query.

### Arquivos principais alterados
- `backend/app/observability.py`, `backend/app/main.py`, `backend/app/api/errors.py`
- `backend/app/monitoring/worker.py`, `backend/app/monitoring/publisher.py`, `backend/app/monitoring/tasks.py`, `backend/app/monitoring/run.py`
- `backend/tests/test_observability.py`, `backend/tests/helpers/api_replica_process.py`
- `backend/Dockerfile`, `backend/IMPLEMENTATION.md`, `frontend/scripts/reconnect-browser-process.mjs`, `scripts/tests/test_api_browser_reconnect.py`, `scripts/verify.ps1`
- `docs/API.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Route é obtida por identidade de rotas de código; desconhecidas ficam unmatched. Isso suporta os routers incluídos da versão FastAPI instalada sem serializar path/query ou depender de APIs privadas.
- 500 de ServerErrorMiddleware externo conserva o ID pelo handler; SSE que falha após headers conserva status original e outcome=error/cancelled. Duração total de stream não é latência REST.
- Helper preserva stderr/erros Uvicorn e grava apenas atividade JSON em relatório privado. Prova Edge arma a API própria antes do crash para correlacionar 503/leituras interrompidas exclusivamente à réplica encerrada.

### Estado atual
- Direcionado: 14 passed/2 skips apenas SQLite em 13,60s. Primeira central: 403 backend/16 skips SQLite em 267,68s; tooling teve 76 passed e uma falha de classificação de ERR_EMPTY_RESPONSE de leitura interrompida durante crash, após recuperar/reconectar/logout com sucesso.
- Correlação da fixture ajustada para conexões da API declaradamente encerrada, incluindo resposta parcial. Edge passou novamente em 22,31s; central final aprovada: 403 backend/16 skips apenas SQLite em 243,32s, 77 tooling e 44 frontend, zero skips obrigatórios. Ruff/TypeScript/build/Compose/whitespace/egress aprovados; cleanup confirmado em `.cache/egress-qa/892dc1d639654f2da9918069b70aba2f/report.json`.
- API local reconstruída/atualizada isoladamente. Prova readonly Nginx8080 correlacionou resposta404 e dois eventos JSON, sem sentinel de query/ID recebido nos logs API; CMD sem access log, gates false e CA de build ausente. Relatório `.cache/verification/activity-runtime.json`.
- Smoke Edge8080 após atualização passou com SSE connected/project.updated/periodic, reconciliação REST e revogação, errors=[]. Web/PG17/Redis e processos PG18 foram preservados.
- Gates false e PG18 preservado. Limites: atividade por processo; métricas agregadas/heartbeats/exporter pendentes. Logs de frameworks/proxy permanecem independentes deste formatter, sem promessa de sanitização global.

### Próximos passos
- Implementar snapshot operacional de backlog/PEL/leases e idade de ticks, sem endpoint público nem labels de alta cardinalidade.
- Provar recuperação do Nginx após mudança real de IP da API em rede QA exclusiva; o proxy atual resolve upstream somente na inicialização.

## 2026-10-04 — SSE retoma após falha HTTP temporária no navegador

### Implementado
- Corrigida fonte EventSource permanentemente CLOSED após HTTP503: recriação com espera 2/4/8/16/30s, limitada a 30s e reiniciada na abertura. CONNECTING preserva retry nativo.
- Identidade da fonte/cancelamento de probe descartam callbacks e 401 antigos; revogação confirmada/unmount cancelam retry. REST/polling permanecem autoridade.
- Ensaio Edge do produto com Vite/proxy/APIs exclusivos, PG17 UUID e Redis reais: crash, commit durante gap, recuperação por REST, nova réplica/fanout e logout. Verificação obrigatória recusa caso ausente/skip.

### Arquivos principais alterados
- `frontend/src/live.ts`, `frontend/src/test/live.test.tsx`, `frontend/scripts/reconnect-browser-process.mjs`, `frontend/IMPLEMENTATION.md`
- `backend/tests/helpers/api_replica_process.py`, `backend/tests/test_api_replicas.py`, `backend/IMPLEMENTATION.md`
- `scripts/tests/test_api_browser_reconnect.py`, `scripts/verify.ps1`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Navegador falhou antes do ajuste em restore, com readyState=2 e sem fonte substituta. O comportamento terminal HTTP é previsto no HTML Standard; polling sozinho não recuperava o indicador/conexão SSE.
- Proxy troca somente seu upstream e só encerra streams próprios. Senhas/cookies/CSRF ficam na memória; 503/transporte deliberados são correlacionados ao proxy e separados de erros inesperados.
- Origin adicional do helper é estritamente HTTP/127.0.0.1/porta alta, sem path/credenciais/query; configuração/contrato backend de produto não mudou.

### Estado atual
- Edge corrigido passed em 21,22s: revisão 1 via REST, revisão 2 via SSE da substituta, logout sem retry e errors=[]. Relatórios privados `frontend/.impeccable/review/reconnect-{before-fix,smoke}.json`.
- Central final: 389 backend/14 skips apenas SQLite em 257,42s, 77 tooling e 44 frontend; Ruff/TypeScript/build/Compose/whitespace aprovados, zero skips obrigatórios. Firewall/TLS/NDP/cleanup confirmados em `.cache/egress-qa/bf151de5cbf34447aea19b3ae2e1a53f/report.json`.
- Web local reconstruído/atualizado isoladamente; smoke EventSource no Edge8080 passou com connected/project.updated/periodic, REST e revogação, errors=[]. API/PG17/Redis permaneceram ativos. Gates false, PG18 preservado. Limites: Edge/proxy QA local, sem balanceador produtivo/failover de host ou SLA.

### Próximos passos
- Avançar observabilidade mínima de requisições/jobs, com logs estruturados e campos sanitizados; métricas/heartbeats de pipeline continuam pendentes.

## 2026-10-04 — Recuperação de stream após crash e substituição de API

### Implementado
- Ensaio real com duas APIs filhas: crash de uma, continuidade da sobrevivente e commit persistido durante a perda do stream.
- Reconexão explícita recebe snapshot inicial e recupera revisão perdida pelo REST sem replay; nova API retorna ao fanout Redis usando o mesmo schema/sessão.
- Fixture centraliza startup/crash/reposição e cleanup de pipes/readers/filhos; saída inesperada é falha e mantém stderr privado.

### Arquivos principais alterados
- `backend/tests/test_api_replicas.py`, `backend/IMPLEMENTATION.md`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Kill usa somente o objeto de subprocesso criado pelo próprio teste, sem PID de runtime/servidores. API substituta recebe porta efêmera nova, evitando rebinding ou interferência em listeners alheios.
- SSE é efêmero: revisão 1 commitada no gap vem do REST, e revisão 2 posterior chega ao stream reaberto e à nova réplica. Sessão persiste no PostgreSQL, sem novo login.
- ReadError/RemoteProtocolError são aceitos somente para reader cuja API foi deliberadamente encerrada; assertions de owner/DTO e erros de outros readers continuam falhando.

### Estado atual
- Três testes reais de recuperação, carga e TCP passaram juntos: host 58,08s/Linux 58,66s. Recuperação manual medida em 1,702s/1,947s, sem stderr inesperado; quotas locais voltaram a um stream na substituta/dois na sobrevivente.
- Relatórios `.cache/verification/replica-recovery-host.xml` e `.cache/verification/events-tcp-linux.xml`; Ruff aprovado. Aplicação/infra não foram alteradas: central anterior permanece 388 backend/14 skips apenas SQLite e 41 frontend; tooling atual tem 76 passed.
- Gates false; PG18 e serviços compartilhados preservados. Limites: reconexão HTTP explícita para porta conhecida, sem retry automático do navegador, balanceador ou recuperação de host/infra.

### Próximos passos
- Provar EventSource nativo reconectando automaticamente e reconciliando o produto por REST, com UI/proxy/API QA exclusivos e nenhum restart compartilhado.
- Incluir evidência reproduzível de navegador na verificação operacional, preservando cookies/credenciais fora dos relatórios.


## 2026-10-04 — Prefixo IPv6 canônico no verificador NDP

### Implementado
- Geração do prefixo QA usa IPv6Address.compressed, incluindo hextets zero adjacentes ao sufixo, para coincidir com a representação retornada pelo Docker.
- Guard parametrizado cobre zeros à esquerda, hextet final zero e prefixo com os três hextets zero.

### Arquivos principais alterados
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Remover zeros à esquerda de cada hextet isoladamente não comprimia a sequência completa; endereços válidos eram recusados antes do peer. Normalização usa parser IPv6 padrão, sem relaxar ownership/isolation guards.

### Estado atual
- Dois novos casos falharam antes da correção. Após fix: 76 testes operacionais passaram com PG17 e Ruff aprovou.
- Prova física com prefixo `3000::/124`, peer `3000::1` e token de recurso aleatório passou: timeout com NDP bloqueado, TLS padrão após restauração e cleanup confirmado. Relatório `.cache/egress-qa/00000000000042dbba8096840331b83f/report.json`.
- Aplicações não foram alteradas; última central continua 388 backend/14 skips apenas SQLite e 41 frontend. Gates false e serviços compartilhados preservados.

### Próximos passos
- Provar reconexão/snapshot REST após queda e retorno de réplica própria, sem parar servidores compartilhados.


## 2026-10-04 — Ensaio de pressão TCP física de SSE

### Implementado
- Cliente TCP real deixa de ler após headers; API Uvicorn filha e buffers de fixture pequenos permitem observar pausa de escrita e backlog físico.
- Prazo de envio real de dez segundos libera slot/gerador e encerra o transporte; outra conta mantém SSE/commit REST e o slot é reutilizado.
- Helper observa diagnóstico exato de timeout de EventResponse sem suprimir stderr; outros erros/avisos de pool continuam falhando. Runner conserva logs Linux no mount privado `/reports`.
- Módulo TCP integrado às provas obrigatórias, recusando skips em verificação completa.

### Arquivos principais alterados
- `backend/tests/test_events_tcp.py`, `backend/tests/test_api_replicas.py`, `backend/tests/helpers/api_replica_process.py`
- `scripts/verify.ps1`, `scripts/verify_backend_container.py`, `scripts/tests/test_verify_backend_container.py`
- `backend/IMPLEMENTATION.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Nenhum send double, mudança de prazo do produto ou alteração de buffers/gates da API compartilhada; dados ficam em schema/owners UUID de PG17 e processos próprios.
- Escrita que cruza high-water mark pode concluir. Após detectar pausa, 16 sinais adicionais garantem envio pendente; isso corrigiu uma sincronização insuficiente do ensaio exposta na primeira regressão central.
- Uvicorn registra TimeoutError deliberado como erro ASGI e fecha o TCP. Teste valida tipo/traceback e count esperados, preservando o diagnóstico original em vez de mascarar exceções.

### Estado atual
- Host final: passed em 15,73s. Linux: TCP e três réplicas passed em 53,26s, buffer pausado em 65.541 bytes, 688 sinais +16 pendentes, liberação em 9,994s e 71.192 bytes drenados até EOF. Relatórios `.cache/verification/events-tcp-{host,linux}.xml`.
- Primeira central teve 387 passed/14 skips SQLite e falhou somente no ensaio TCP ainda sem envio pendente garantido. Segunda central final passou: 388 backend/14 skips apenas SQLite em 250,59s, 74 tooling e 41 frontend, zero skips obrigatórios; Ruff/TypeScript/build/Compose/whitespace aprovados.
- Prova física firewall/TLS/NDP aprovada e cleanup confirmado: `.cache/egress-qa/1d06aae65a5e4776957a2e8a8abe94b8/report.json`. Diagnóstico de timeout esperado preservado também no mount de relatórios Linux.
- Gates false e PG18 preservado. Limites: loopback local, buffers artificiais de fixture e um cliente travado; não mede SLA/capacidade sustentada de produção.

### Próximos passos
- Provar reconexão/snapshot REST após queda e retorno de réplica própria, preservando API/Redis/PG compartilhados.
- Normalizar integralmente prefixos IPv6 de QA quando hextets do UUID forem zero; expandir o guard de endereço canônico antes do próximo ensaio NDP.


## 2026-10-04 — Neighbor Discovery e TLS entre namespaces exclusivos

### Implementado
- Prova física obrigatória entre servidor e cliente em dois containers QA, com IPv6 na eth0, política real de OUTPUT e executor/transporte padrão.
- Controle negativo bloqueia NS/NA somente no cliente descartável: TCP expira e solicitações descartadas são contadas. Política restaurada resolve o vizinho e permite TLS verificado/headers-only.
- Guards de prefixo canônico, endereço/namespace do peer, evidência incompleta, erro/timeout de servidor e cleanup de ambos os endpoints com labels UUID.

### Arquivos principais alterados
- `infra/worker/qa_ndp_probe.py`, `infra/worker/qa_tls_probe.py`, `infra/worker/.dockerignore`
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Prefixo global-unicast QA aleatório /124 fica somente em bridge internal descartável, sem forwarding externo ou portas publicadas; não representa propriedade/conectividade pública do endereço.
- Prefixos externos à bridge internal impediram o primeiro protótipo de alcançar aliases do peer. O novo desenho usa endereços atribuídos à própria interface, preservando isolamento Docker.
- Kernel pode aprender o vizinho de uma solicitação recebida e responder com anúncio. Medição conta ambos os tipos após restaurar a política, sem exigir ordem de timers; cache precisa estar resolvido na eth0.
- Helpers/CA de fixture são mounts readonly de QA, fora da imagem de worker; nenhum ajuste de SSRF, gates, firewall do host ou servidores compartilhados.

### Estado atual
- Prova completa build/firewall/TLS/NDP passou: timeout com NDP negado, duas solicitações descartadas, um anúncio aceito, vizinho resolvido e GET TLS padrão. Ambos os cleanups confirmados; nenhuma rede QA remanescente. Relatório `.cache/egress-qa/a1af1fd82e0e4361a5f0f9afdd5981ff/report.json`.
- 74 testes operacionais passaram com PG17; Ruff passou. Backend/frontend não foram alterados nesta etapa: regressão central anterior permanece 387 backend/14 skips apenas SQLite, 41 frontend e zero skips obrigatórios.
- Gates false; PG18 preservado. Limites: dois namespaces na mesma bridge Docker Desktop, sem NDP entre hosts, conectividade externa ou implantação produtiva.

### Próximos passos
- Exercitar pressão física do socket SSE com cliente sem leitura, confirmando prazo de envio, liberação de slot/recursos e continuidade para cliente saudável.
- Provar reconexão e reconciliação REST após queda de uma réplica própria; não reiniciar API/Redis/PG compartilhados.


## 2026-10-04 — Transporte TLS padrão sob o firewall do worker

### Implementado
- Prova obrigatória com CheckExecutor/SafeTransport/backend físico padrão, sockets TLS IPv4/IPv6 próprios e filtro de OUTPUT ativo, após queda para UID10001.
- Peer pinning, SNI/Host, encerramento após headers e negativos de CA desconhecida, hostname incorreto e respostas DNS privadas/mistas.
- Verificador recusa evidência TLS incompleta mesmo quando o cleanup foi bem-sucedido; helpers/fixtures não entram na imagem de worker.

### Arquivos principais alterados
- `infra/worker/qa_tls_probe.py`, `infra/worker/.dockerignore`
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Somente respostas DNS e CA de fixture são injetadas. Não há adapter de roteamento físico nem desativação de CERT_REQUIRED/hostname; proxy e CA do ambiente não substituem o transporte.
- Servidor anuncia corpo extenso sem enviar bytes: executor precisa fechar após headers. Negativos TLS não fazem HTTP nem retry; DNS inseguro é bloqueado antes do socket.
- Rede internal e containers UUID exclusivos, sem portas publicadas ou checks externos; cleanup verifica labels e endpoints antes de remover recursos próprios.

### Estado atual
- Regressão central final passou: 387 backend/14 skips apenas SQLite em 215,90s, 65 tooling, 41 frontend; Ruff/TypeScript/build/Compose/whitespace aprovados, zero skips obrigatórios.
- Prova física: seis sockets permitidos/18 bloqueados, entrypoint sem privilégios e seis casos TLS aprovados, dois GETs de headers, cleanup confirmado. Relatório `.cache/egress-qa/640f13b7725540ed85ff49ef665567dc/report.json`.
- Gates false e PG18 preservado. Limites: endereços públicos de fixture têm rotas locais ao namespace; não comprova NDP entre namespaces, disponibilidade pública, HTTP externo ou implantação produtiva.

### Próximos passos
- Provar NDP/TLS entre dois namespaces exclusivos em rede internal com prefixo QA próprio; destinos fora do prefixo são bloqueados pelo isolamento Docker antes de alcançar o peer.
- Exercitar backpressure TCP físico e recuperação de réplica, mantendo controles compartilhados intactos.


## 2026-10-04 — Réplicas SSE reais e conexão devolvida após disconnect

### Implementado
- Três APIs Uvicorn próprias com PostgreSQL17/Redis reais, seis contas, 51 streams HTTP e commits REST alternados entre réplicas.
- Carga cadenciada de 600 sinais/5.100 entregas, rajada de mil sinais com filas lentas de até 32, whitelist/owner, 429 local, slot reutilizado e revogação nas três APIs.
- Correção de vazamento de conexão PostgreSQL na revalidação SSE interrompida por disconnect; shield AnyIO preserva o prazo de cinco segundos e a finalização de recursos.
- Regressões determinísticas de cancelamento na leitura/close, propagação do cancelamento asyncio direto e módulo real exigido pela verificação central.

### Arquivos principais alterados
- `backend/app/services/events.py`, `backend/tests/test_events.py`
- `backend/tests/test_api_replicas.py`, `backend/tests/helpers/api_replica_process.py`
- `scripts/verify.ps1`, `backend/IMPLEMENTATION.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Uvicorn/HTTP/TCP/Redis/PG reais em portas/schemas próprios; telemetria do helper usa stdin, sem endpoint de produto. Gates false, nenhuma chamada de check externo.
- Cancelamento de nível AnyIO podia atingir rollback/check-in repetidamente. Proteção cobre somente a revalidação delimitada; não envolve yield de generator em cancel scope nem altera sessão/cadência.
- Filas lentas instrumentadas demonstram bounded Pub/Sub, sem alegar pressão física de socket. Sinais de carga são hints sintéticos; revisão autoritativa continua no REST.

### Estado atual
- Host passou em 35,72s, sem stderr/erro de pool após fix. Na carga local: p50 10,771ms/p95 15,839ms; 600 sinais/5.100 entregas em 3,126s; revogação nas três em 23,113s. Relatório `.cache/verification/api-replicas-host.xml`.
- Antes do fix, dois ensaios passaram funcionalmente, mas teardown detectou conexões não devolvidas e CancelledError/SAWarning. Falha foi corrigida, sem silenciar logs. Três testes de recurso/cancelamento passaram.
- Regressão central Linux passou: 386 backend/14 skips apenas SQLite em 211,15s, 64 tooling e 41 frontend; Ruff/TypeScript/build/Compose/firewall aprovados, zero skips obrigatórios. Módulo SSE final teve 59 passed no host, incluindo caso de cancelamento asyncio adicionado após coleta central. Linux mediu p50 4,863ms/p95 7,753ms, carga em 2,142s e revogação em 25,454s, sem stderr de réplicas.
- API Compose atualizada somente via build/api up --no-deps, sem recriar PG/Redis/web. Runtime confirmou shield carregado, gates false, CA de build ausente e readiness via Nginx8080. Smoke Edge real `VIGIL_UI_URL=http://127.0.0.1:8080 npm run test:live` passou: EventSource nativo, connected/project.updated/periodic, reconciliação REST e revogação voltando ao login, errors=[]. Relatório privado `frontend/.impeccable/review/live-smoke.json`; criada somente conta/projeto QA próprio no PG17, sem monitores/checks.
- Cota é de três conexões por owner/processo, podendo somar nove em três réplicas. Limites: carga local curta/cadenciada, sem SLA, balanceador, múltiplos hosts ou backpressure TCP físico. PG18 e runtime externo preservados.

### Próximos passos
- Comprovar transporte com pinning/TLS dentro do firewall e Neighbor Discovery entre namespaces, mantendo gates externos false.
- Exercitar backpressure físico de TCP e recuperação de réplica em ambiente exclusivo antes de implantação.


## 2026-10-04 — Firewall de worker com queda de privilégios

### Implementado
- Imagem Linux específica de worker, inicializador de firewall IPv4/IPv6 e perfil Compose opt-in separado da API, com gates false por padrão.
- Prova física em rede internal/containers UUID exclusivos, listeners positivos antes da política, destinos especiais bloqueados e entrypoint real sem privilégios.
- Testes de resolução mista/unsafe, falha antes do exec, regra DNS após DNAT e cleanup que recusa recursos alheios. Verificação central exige a prova física.

### Arquivos principais alterados
- `infra/worker/Dockerfile`, `infra/worker/.dockerignore`, `infra/worker/egress.py`, `infra/worker/qa_probe.py`
- `compose.worker.yaml`, `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`, `scripts/verify.ps1`
- `scripts/verify_backend_container.py`, `scripts/verify-backend-container.ps1`, `scripts/tests/test_verify_backend_container.py`
- `README.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- OUTPUT permite público TCP80/443, DNS Docker original 127.0.0.11:53 e PG5432/Redis6379 somente em IPs RFC1918 resolvidos na inicialização. IPv6 unicast e Neighbor Discovery têm regras próprias; faixas especiais são conservadoras.
- Docker faz DNAT do resolver antes de OUTPUT; matching conntrack do destino/porta originais preserva DNS sem permitir portas arbitrárias de loopback.
- Após instalar ambos os filtros, setpriv remove todas as capabilities e executa UID/GID10001 com no-new-privileges. Inicialização com falha não inicia worker.
- Somente namespaces exclusivos recebem regras/endereços; cleanup confere labels UUID e endpoints. Nenhuma alteração de firewall do host, gates ou processos compartilhados.
- Runner backend pode usar rede Compose interna guardada por labels/serviço/binding da URL nativa. Evita timeouts transitórios do gateway Docker Desktop sem alterar os testes; tooling nativo permanece na origem loopback.

### Estado atual
- Prova física final passou: seis conexões permitidas, 18 bloqueadas com 17 listeners negativos comprovadamente ativos, DNS interno, UID10001/capabilities zero e entrypoint da imagem sem privilégios. Relatório `.cache/egress-qa/c173df7a2c5e4ce280d97049037b83a8/report.json`, cleanup confirmado.
- Verificação central pela rede interna passou: 383 backend passed/14 skips apenas SQLite em 174,99s, 64 tooling e 41 frontend passed; Ruff/TypeScript/build/Compose/whitespace aprovados, zero integrações obrigatórias ignoradas. Stack atual continua gates false e worker opt-in não foi iniciado. PG18 preservado.
- Versão intermediária PowerShell de roteamento foi bloqueada e removida pelo antivírus. Substituída por wrapper simples e implementação Python com 13 testes de guards; proteção permaneceu ativa. Regressores backend por gateway tiveram timeouts de abertura de conexão em testes distintos, sem falha de lógica comprovada.
- Limites: destinos de socket com rotas locais ao namespace, sem HTTP externo, disponibilidade pública, NDP entre hosts ou implantação produtiva; controle DB/Redis TCP sintético. IPs de controle alterados exigem reiniciar worker; política conservadora pode bloquear exceções públicas especiais.

### Próximos passos
- Medir fanout, filas lentas e limites por owner com múltiplos processos API/Redis, mantendo runtime externo desligado.
- Ensaiar transporte runtime dentro da política e NDP entre namespaces antes de qualquer implantação externa.


## 2026-10-04 — Crash de workers nos limites de persistência e ACK

### Implementado
- Ensaio com subprocessos independentes, Receiver Taskiq e tarefa reais, PostgreSQL17 e Redis: crash após entrega, após claim, dentro da transação final e após commit antes do ACK.
- Reclaim de mensagem órfã, proteção da lease, retry pelo scheduler/publicador, replay sem duplicação e três crashes técnicos com esgotamento sem resultado de saúde/incidente.
- Módulo incluído entre as integrações obrigatórias da verificação central.

### Arquivos principais alterados
- `backend/tests/helpers/worker_crash_process.py`, `backend/tests/test_worker_process_recovery.py`
- `scripts/verify.ps1`, `backend/IMPLEMENTATION.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Somente filhos próprios recebem kill; schemas e streams UUID isolam dados. Não há sinais para servidores compartilhados, FLUSHDB, HTTP externo ou mudança de gates.
- Executor sintético e leases de 12s/2s são adapters exclusivos do teste; claim/finalize, transações, broker/ACK e processos são reais. Lease padrão de produção permanece 90s.
- Estado PostgreSQL é a autoridade: mensagem de job ocupado pode ser ACKada, e lease vencida volta pelo scheduler, sem exigir retenção eterna na PEL.

### Estado atual
- Cinco cenários passaram com PG17.11/Redis7.4.11 no host em 66,30s e no Linux, incluindo rollback após flush e commit antes do ACK. Regressão central final: 383 backend passed/14 skips apenas SQLite em 214,06s; 30 tooling e 41 frontend passed; Ruff/TypeScript/build/Compose/whitespace aprovados.
- Primeira regressão teve timeout transitório na abertura de conexão pelo gateway Docker Desktop, antes de executar o teste de concorrência de incidentes. Segunda execução integral passou, sem alteração de código para esconder a falha.
- Gates false e PG18/processos pendentes preservados. Especialistas Maestri continuam sem créditos; nenhuma disputa de arquivos.
- Limites: não cobre HTTP real, reinício de host/servidores ou egress físico. Lease acelerada não mede a latência operacional de 90s.

### Próximos passos
- Implementar prova de egress em rede isolada e medir fanout/backpressure com múltiplas réplicas, mantendo checks externos desligados.


## 2026-10-04 — Backup e restore PG17 com conteúdo equivalente

### Implementado
- Ensaio opt-in de backup PostgreSQL17 Compose, com snapshot readonly compartilhado entre manifesto da origem e pg_dump.
- Restore em banco UUID exclusivo, comparação de todas as linhas por SHA256 ordenado, revisão Alembic, colunas/defaults, índices e constraints; remoção do banco confirmada no catálogo.
- Testes de guards de alvo/cleanup, conteúdo diferente com mesma contagem, snapshot importado após commit concorrente, timeout e falha de cleanup sem falso sucesso.
- Tooling operacional integrado à verificação central com relatório próprio e duas provas PostgreSQL obrigatórias.

### Arquivos principais alterados
- `scripts/backup_restore_check.py`, `scripts/test-compose-backup-restore.ps1`
- `scripts/tests/test_backup_restore_check.py`, `scripts/verify.ps1`
- `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- URL explícita restrita a localhost/55433/vigil, PostgreSQL17, container Compose e system_identifier coincidentes. Origem não recebe gravações.
- Exportador REPEATABLE READ permanece aberto até pg_dump --snapshot terminar. Restore usa transação única; clean atua somente no novo banco.
- CHECKs comparados pela decompilação legível do próprio PG, eliminando diferença de agrupamento associativo introduzida pelo replay do dump.
- Timeout encerra apenas o cliente próprio, preserva banco/dump pendentes para revisão e não repete DROP nem usa FORCE. Falhas não publicam stderr com possíveis dados privados.

### Estado atual
- Ensaio real final no PG17.11 passou com conteúdo/schema equivalentes, dump de 42.302 bytes e cleanup confirmado em 3,149s. Comparadas sete tabelas mais Alembic, incluindo 76 jobs, 76 resultados e 38 incidentes sintéticos existentes.
- Trinta testes de tooling passaram sem skips, incluindo snapshots concorrentes PG17. Regressão central: 378 backend passed/14 skips apenas SQLite, 41 frontend passed; Ruff, TypeScript/build, Compose e whitespace aprovados. Nenhuma integração obrigatória ignorada.
- Dumps/relatórios privados em `.cache/backup-restore/<UUID>/`; JUnit operacional em `.cache/verification/scripts.xml`. PG18/processos pendentes e gates false preservados. Especialistas Maestri permanecem indisponíveis por limite de uso; etapa concluída na área de infraestrutura.
- Limites: somente public/dados, sem owners/ACLs, roles globais, WAL/PITR, recuperação de cluster inteiro ou RPO/RTO de produção. Este ensaio não habilita checks externos.

### Próximos passos
- Ensaiar crash/restart/reentrega de worker próprio em ambiente isolado, usando jobs exclusivos e sem HTTP externo.
- Implementar e comprovar restrição física de egress/firewall no ambiente de monitoramento.
- Medir fanout e limites com múltiplas réplicas antes de liberar gates externos; preservar pendências do PG18 para diagnóstico separado.


## 2026-10-04 — Integrações reais e regressão obrigatória concluídas

### Implementado
- Testes Redis Streams com PEL, reclaim ocioso em múltiplos lotes, ACK idempotente, envelope inválido e commit PostgreSQL antes do ACK; rollback mantém entrega recuperável.
- Pub/Sub com isolamento por owner, whitelist, eco/cleanup, processos independentes e recuperação após queda real de um proxy TCP exclusivo do teste.
- Sockets TLS/SNI/Host IPv4/IPv6, certificados rejeitados, headers-only e bloqueio SSRF antes do socket. Verificação obrigatória exige os três módulos sem skips de integração.
- Runner backend em container temporário com código readonly e dependências dev fixadas; frontend permanece verificado no host.

### Arquivos principais alterados
- `backend/tests/test_broker_integration.py`, `backend/tests/test_events_redis.py`, `backend/tests/helpers/redis_event_process.py`
- `backend/tests/test_transport_sockets.py`, `backend/tests/fixtures/tls/`, `backend/IMPLEMENTATION.md`
- `scripts/verify.ps1`, `scripts/verify-backend-container.ps1`, `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Testes usam schemas/streams UUID isolados e conexões próprias; nenhum FLUSHDB, shutdown Redis ou mudança na proteção SSRF/TLS do runtime.
- Avast substitui certificados até em loopback Windows; TLS positivo foi comprovado em container Linux mantendo CERT_REQUIRED/check_hostname. CA extra opcional serve apenas downloads no container descartável.
- Teste original de queda dependia de disconnect com endpoint ainda acessível. Proxy corrigido prova recusa real e fecha clientes antes de aguardar encerramento do servidor.

### Estado atual
- Verificação central obrigatória passou: **378 backend passed, 14 skips somente SQLite**, em 158,29s; zero skips obrigatórios PostgreSQL/Redis/PubSub/TLS. Ruff passou.
- **41 frontend passed**, TypeScript/build/Compose/whitespace aprovados. Smoke de observações já aprovado em Edge desktop/mobile e registrado no commit local `659a1b8`.
- Compose PostgreSQL17.11/55433, Redis7.4.11 e UI/API8080 ativos. Gates false; PG18 e suas pendências preservados. Test fixtures TLS são públicos e não têm autorização produtiva.
- Relatório JUnit em `.cache/verification/backend.xml`; credenciais de QA e capturas ignoradas. Nenhum push executado.

### Próximos passos
- Validar controles de egress/firewall em ambiente isolado antes de habilitar rede de monitoramento; comprovar bloqueios físicos além da validação runtime.
- Ensaiar recuperação operacional com reinício/crash controlado de processos próprios e backup/restauração no PG17, preservando pendências PG18.
- Definir e medir carga/limites de conexões e fanout com múltiplas réplicas; manter gates false até esses critérios serem atendidos.


## 2026-10-04 — Observações preenchidas validadas no Compose

### Implementado
- Seed opt-in PostgreSQL 17 com conta exclusiva, seis monitores, 76 ciclos e 38 incidentes sintéticos, manifesto privado e confronto de expectativas com SQL persistido.
- Smoke Playwright/Edge por rotas REST reais, cobrindo métricas/buckets, histórico/retries, paginação e incidentes privados/públicos em desktop/mobile.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`, `backend/tests/test_db_qa_seed.py`, `backend/app/db/IMPLEMENTATION.md`
- `frontend/scripts/observations-smoke.mjs`, `frontend/package.json`, `frontend/IMPLEMENTATION.md`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Seed restrito a PostgreSQL 17 local/55433/public, sem pipeline/network. Cada owner é novo, sem sobrescrever manifestos; nenhum HTTP executado.
- Dados administrativos são exemplos sintéticos de DTO. Manifesto/credenciais/capturas permanecem ignorados pelo Git/Docker; smoke exige fixture com menos de 45 minutos.

### Estado atual
- Dez testes QA passaram no PG17.11 e Ruff passou. Smoke final aprovado no Compose8080 em Edge1440/390, 14 verificações sem overflow e `errors=[]`; buckets UTC e apresentação America/Sao_Paulo conferidos.
- Se o manifesto não puder ser escrito após commit, pode restar owner QA isolado; sem cleanup automático. PG18/processos pendentes preservados.
- Integração Redis/TLS está em regressão central; nenhuma alteração de produto foi necessária no frontend neste marco.

### Próximos passos
- Concluir verificação obrigatória Redis/PubSub/TLS/PostgreSQL e registrar seu commit separado.
- Avançar controles de egress, recuperação operacional e carga antes de habilitar checks externos.


## 2026-10-04 — Build Docker e stack local comprovados

### Implementado
- Build opcional com CA pública confiável via BuildKit secret para uv/npm, sem desabilitar TLS nem persistir a CA no runtime.
- Removido segundo sync redundante do backend: projeto não empacotável já instala as dependências fixadas na camada inicial.
- Construídas imagens API/UI/migrate e iniciado stack Compose com Nginx, PostgreSQL 17.11 e Redis 7.4.11.

### Arquivos principais alterados
- `backend/Dockerfile`, `frontend/Dockerfile`, `compose.build-ca.yaml`
- `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- CA extra é fornecida explicitamente por arquivo PEM confiável somente no build; bundle temporário removido na mesma camada, sem alterar trust do transporte de monitoramento.
- PostgreSQL Compose publicado em 55433 nesta sessão para preservar o PostgreSQL nativo da porta 5432 e o cluster PG18 da porta 55432.
- Pipeline/network continuam false. Stack local serve cadastros/consultas; workers externos não foram iniciados.

### Estado atual
- Base funcional commitada localmente em `ac658b7` após 352 testes backend e confirmação direta de 41 frontend/build. Sem push.
- Build inicialmente falhou com UnknownIssuer; repetição com CA pública já validada pelo Windows passou nas três imagens. CA exportada em `.cache/build/`, fora do Git.
- Migration container terminou exit0; PostgreSQL/Redis/API saudáveis e `/health/ready` via Nginx8080 retorna ok. Ausência de `/run/secrets/build_ca`, `/tmp/vigil-build-ca.pem` e `SSL_CERT_FILE` confirmada no runtime; gates false confirmados.
- Broker existente executado pelo Maestro com Redis real: 3 passed em 0,53s, incluindo ACK/reclaim ocioso.
- Especialistas validam PG17/pipeline/retention, novos testes Redis/PubSub/sockets TLS e smoke de observações com fixture sintética persistida exclusiva PG17. Essas provas ainda estão em andamento neste marco.

### Próximos passos
- Integrar entregas dos especialistas, confirmar smoke de observações preenchidas e executar verificação obrigatória PostgreSQL/Redis reais.
- Registrar resultados e commitar separadamente cada unidade verificada.
- Preservar gates externos até controles egress/recuperação/carga restantes serem comprovados.

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
