# Vigil

Plataforma web de monitoramento de APIs e serviços HTTP. O Vigil integra cadastro de endpoints, histórico de disponibilidade/latência, incidentes e página pública de status por projeto. Execução externa de checks permanece opt-in.

**Online: [abrir o Vigil](https://vigil-4q06.onrender.com).** Crie uma conta na página e cadastre seus endpoints públicos. O perfil gratuito verifica os monitores aproximadamente a cada 15 minutos; intervalos maiores são respeitados e a agenda pode atrasar. Os dados locais não foram transferidos para a nuvem.

**Status atual: publicado em 2026-10-06.** Contas, projetos, monitores, histórico, métricas, incidentes, falhas do processamento e status pública estão integrados entre React, FastAPI e PostgreSQL. SSE e observações preenchidas passaram no navegador real em etapas anteriores. Retenção, Redis/PubSub, TLS/SNI/IPv6, crash/reentrega de worker e backup/restore PG17 possuem provas reais controladas registradas.

A revisão atual exige a revision Alembic atual no readiness e inclui índices de evidência dos incidentes, corroborados por planos PG17. Campanhas de carga e coleta UI v2 anteriores estão registradas; a nova coleta auditável v3 ainda aguarda execução física. O ambiente local usa PostgreSQL 18 na porta 55432, API 8000 e frontend 5173. Checks externos permanecem desabilitados nesse ambiente local. Consulte [DEVELOPMENT_LOG](docs/DEVELOPMENT_LOG.md) para resultados e limites de cada etapa.

## Objetivo

O novo [perfil gratuito online](docs/FREE_CLOUD.md) usa Render Free, Neon separado
e GitHub Actions público, com checks aproximadamente a cada 15 minutos. A interface
e a API compartilham HTTPS, sem Redis neste perfil. O deploy está ativo, e uma
[execução real no GitHub](https://github.com/fmvini/Vigil/actions/runs/37505959414)
gravou um check HTTPS com resposta 200 no Neon e na interface pública. A agenda
está habilitada. O serviço gratuito pode levar cerca de um minuto para abrir após
ficar ocioso; consulte os [limites operacionais](docs/FREE_CLOUD.md).
O ambiente local foi atualizado para o novo build e permanece separado, com seus
gates desabilitados.

Oferecer monitoramento útil para desenvolvedores e pequenas equipes, demonstrando processamento assíncrono, filas, concorrência, scheduling, recuperação de falhas e comunicação em tempo real, com uma arquitetura simples de operar.

## Funcionalidades planejadas para o MVP

- Cadastro, login e isolamento dos dados de cada usuário.
- Projetos e monitores de endpoints públicos com método GET.
- Intervalo, timeout, status HTTP esperado e limite de falhas consecutivas configuráveis.
- Checks periódicos, retries limitados, latência e histórico.
- Status online, degradado ou offline, com indicação separada de dados ausentes ou antigos.
- Incidentes automáticos e histórico de recuperação.
- Uptime por amostras, latência média e p95.
- Dashboard atualizado por Server-Sent Events (SSE).
- Página pública de status opcional, sem exposição de URLs ou dados privados.

## Arquitetura

```mermaid
flowchart LR
    UI[React] --> API[FastAPI]
    API --> DB[(PostgreSQL)]
    S[Scheduler e publicador] --> DB
    S --> Q[(Redis Streams)]
    Q --> W[Workers assíncronos]
    W --> E[Endpoints públicos]
    W --> DB
    W -. sinal após commit .-> P[Redis Pub/Sub]
    P -.-> API
    API -. SSE .-> UI
```

API, scheduler e workers compartilham um backend modular e executam em processos separados. PostgreSQL é a fonte de verdade; Redis transporta jobs e sinais de atualização. Jobs têm identidade persistida para tolerar reentregas sem duplicar métricas ou incidentes. Scheduler e workers dependem da ativação explícita dos gates de execução.

## Stack

| Área | Escolha |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| API | Python, FastAPI, Pydantic |
| Persistência | PostgreSQL, SQLAlchemy assíncrono, asyncpg e Alembic |
| Monitoramento | asyncio, HTTPX, Taskiq com taskiq-redis/RedisStreamBroker |
| Tempo real | SSE e Redis Pub/Sub; consultas REST para ressincronização |
| Autenticação | Sessões opacas em cookie e hash de senha Argon2id |
| Operação | Docker/Compose, logs estruturados e diagnóstico operacional |
| Testes | pytest, Vitest, testes de integração e navegador com Playwright/Edge |

A integração da fila e do transporte HTTP seguro exige validação no ambiente alvo antes de habilitar o pipeline. Dependências Python e JavaScript são registradas nos manifests/lockfiles dos respectivos diretórios.

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [PROJECT_SCOPE](docs/PROJECT_SCOPE.md) | Visão, MVP, limites e evoluções |
| [REQUIREMENTS](docs/REQUIREMENTS.md) | Requisitos, regras e critérios de aceite |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Componentes, pipeline, falhas e segurança |
| [DATABASE](docs/DATABASE.md) | Entidades, relações, índices e retenção |
| [API](docs/API.md) | Contratos REST e SSE propostos |
| [ROADMAP](docs/ROADMAP.md) | Fases, dependências e resultados verificáveis |
| [DECISIONS](docs/DECISIONS.md) | Decisões, alternativas e pendências |
| [DEVELOPMENT_LOG](docs/DEVELOPMENT_LOG.md) | Estado atual e continuidade entre sessões |
| [OPERATIONS](docs/OPERATIONS.md) | Verificação de integrações, retenção e backup/restore |
| [AGENTS.md](AGENTS.md) | Instruções para agentes que trabalharão no projeto |

## Ambiente de desenvolvimento

Python 3.13, uv e Node 24 são usados na validação local. PostgreSQL é obrigatório no runtime; SQLite é restrito aos testes de aplicação.

O Compose inicial fornece PostgreSQL/Redis com portas vinculadas a localhost:

```powershell
docker compose up -d postgres redis
```

Inicie a API em um terminal e o frontend em outro, a partir da raiz:

```powershell
./scripts/start-local.ps1 api -Migrate
./scripts/start-local.ps1 frontend
```

Abra `http://127.0.0.1:5173`; OpenAPI em `http://127.0.0.1:8000/docs`. A API usa o banco local do Compose por padrão. O cluster PostgreSQL isolado desta sessão usa porta 55432; para reutilizá-lo:

```powershell
./scripts/start-local.ps1 api -Migrate -DatabaseUrl 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil'
```

Após o primeiro `uv sync`, mudanças de dependências exigem sincronizar novamente. Use Node 24 com certificados do sistema (`NODE_USE_SYSTEM_CA=1`) e `uv --system-certs` quando o ambiente exigir CA corporativa; não desabilite a verificação TLS.

Quando o ambiente restringir os subprocessos do esbuild/Vite, é possível servir um build já existente:

```powershell
./scripts/start-local.ps1 frontend -Preview
```

Esse modo usa Node 24, ocupa a mesma porta 5173 e mantém o proxy `/api` para a API. Exige `frontend/dist/index.html`; não recompila nem oferece hot reload. Após alterações no produto, execute `npm.cmd run build` em um ambiente que permita o build antes de usar o preview. Na execução de 2026-10-06, o build existente corresponde à entrega de branding anterior; as mudanças novas do frontend são tooling de QA.

O profile `app` contém build da API/UI, execução da migration e Nginx no mesmo origin (`docker compose --profile app up --build -d`). Imagens e startup foram validados localmente com PostgreSQL 17.11, Redis 7.4.11 e UI em `http://127.0.0.1:8080`; migration concluiu antes da API e readiness passou. Se 5432 estiver ocupada, configure `POSTGRES_PORT=55433`. Ambientes com inspeção HTTPS podem usar a CA pública aprovada somente como secret opcional de build, conforme [OPERATIONS](docs/OPERATIONS.md).

Verificação prevista após dependências instaladas:

```powershell
./scripts/verify.ps1 -TestDatabaseUrl 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil'
```

Git local foi autorizado e inicializado; nenhuma operação de push é automática.

Para exigir PostgreSQL/Redis/PubSub/sockets TLS, crash de worker e firewall físico, use `./scripts/verify.ps1 -RequireIntegration` com `-TestDatabaseUrl` e `-TestRedisUrl` (ou suas variáveis `VIGIL_TEST_*`). Requer Docker e imagem API construída. Em Windows com inspeção HTTPS de loopback, use `-BackendContainer -ContainerNetwork vigil_default` conforme [OPERATIONS](docs/OPERATIONS.md). O modo parcial avisa sobre integrações ausentes e registra os skips no relatório.

A retenção pode ser inspecionada com `./scripts/run-retention.ps1 -DatabaseUrl $env:VIGIL_DATABASE_URL`; o padrão faz rollback. Consulte [OPERATIONS](docs/OPERATIONS.md) para aplicar lotes e verificar backup/restore.

O ensaio PG17 Compose `./scripts/test-compose-backup-restore.ps1` exige `VIGIL_BACKUP_DATABASE_URL` explícita e comprova conteúdo/schema restaurados contra um snapshot consistente, com cleanup confirmado. Dumps privados permanecem fora do Git. Consulte [OPERATIONS](docs/OPERATIONS.md) para execução e limites.
