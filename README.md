# Vigil

Plataforma web de monitoramento de APIs e serviços HTTP. O Vigil permitirá cadastrar endpoints, acompanhar disponibilidade e latência, identificar incidentes e publicar uma página de status por projeto.

**Status atual: desenvolvimento funcional em 2026-10-04.** Contas, projetos, monitores, histórico, métricas, incidentes e status pública estão integrados entre React, FastAPI e PostgreSQL. SSE e observações preenchidas passaram no navegador real. Retenção, Redis/PubSub, TLS/SNI/IPv6, crash/reentrega de worker e backup/restore PG17 foram validados com integrações reais controladas. Firewall de worker tem perfil opt-in e prova física em namespace isolado; checks externos permanecem desabilitados até validar implantação e carga. Consulte [DEVELOPMENT_LOG](docs/DEVELOPMENT_LOG.md) para resultados e limitações.

## Objetivo

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

## Arquitetura proposta

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

API, scheduler e workers compartilharão um backend modular, executado em processos separados. PostgreSQL será a fonte de verdade; Redis transportará jobs e sinais de atualização. Jobs terão identidade persistida para tolerar reentregas sem duplicar métricas ou incidentes.

## Stack planejada

| Área | Escolha |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| API | Python, FastAPI, Pydantic |
| Persistência | PostgreSQL, SQLAlchemy assíncrono, asyncpg; Alembic na implementação |
| Monitoramento | asyncio, HTTPX, Taskiq com taskiq-redis/RedisStreamBroker |
| Tempo real | SSE e Redis Pub/Sub; consultas REST para ressincronização |
| Autenticação | Sessões opacas em cookie e hash de senha Argon2id |
| Operação | Docker/Compose planejados; logs estruturados e métricas operacionais |
| Testes | pytest e testes de integração; testes de frontend e navegador nas fases correspondentes |

A integração da fila e do transporte HTTP seguro será validada antes de habilitar o pipeline. Dependências Python e JavaScript são registradas nos manifests/lockfiles dos respectivos diretórios.

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

O profile `app` contém build da API/UI, execução da migration e Nginx no mesmo origin (`docker compose --profile app up --build -d`). Imagens e startup foram validados localmente com PostgreSQL 17.11, Redis 7.4.11 e UI em `http://127.0.0.1:8080`; migration concluiu antes da API e readiness passou. Se 5432 estiver ocupada, configure `POSTGRES_PORT=55433`. Ambientes com inspeção HTTPS podem usar a CA pública aprovada somente como secret opcional de build, conforme [OPERATIONS](docs/OPERATIONS.md).

Verificação prevista após dependências instaladas:

```powershell
./scripts/verify.ps1 -TestDatabaseUrl 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil'
```

Git local foi autorizado e inicializado; nenhuma operação de push é automática.

Para exigir PostgreSQL/Redis/PubSub/sockets TLS, crash de worker e firewall físico, use `./scripts/verify.ps1 -RequireIntegration` com `-TestDatabaseUrl` e `-TestRedisUrl` (ou suas variáveis `VIGIL_TEST_*`). Requer Docker e imagem API construída. Em Windows com inspeção HTTPS de loopback, use `-BackendContainer -ContainerNetwork vigil_default` conforme [OPERATIONS](docs/OPERATIONS.md). O modo parcial avisa sobre integrações ausentes e registra os skips no relatório.

A retenção pode ser inspecionada com `./scripts/run-retention.ps1 -DatabaseUrl $env:VIGIL_DATABASE_URL`; o padrão faz rollback. Consulte [OPERATIONS](docs/OPERATIONS.md) para aplicar lotes e verificar backup/restore.

O ensaio PG17 Compose `./scripts/test-compose-backup-restore.ps1` exige `VIGIL_BACKUP_DATABASE_URL` explícita e comprova conteúdo/schema restaurados contra um snapshot consistente, com cleanup confirmado. Dumps privados permanecem fora do Git. Consulte [OPERATIONS](docs/OPERATIONS.md) para execução e limites.
