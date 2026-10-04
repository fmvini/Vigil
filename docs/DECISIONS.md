# Decisões de implementação

## 2026-10-04 — Primeiro incremento e divisão de propriedade

- O usuário autorizou iniciar desenvolvimento e coordenar os três agentes existentes no Maestri.
- Backend implementa API/domínio/configuração/testes; Banco de Dados implementa `backend/app/db`, migrations e testes de persistência; Frontend implementa `frontend`; Maestro integra, mantém documentação e infraestrutura.
- Git local foi autorizado explicitamente e inicializado na branch `main`; commits ficam centralizados no Maestro para não misturar staging de agentes concorrentes.
- API sob `/api/v1`, listas `{items,total}`, sessões opacas e CSRF sincronizado. OpenAPI documenta os DTOs executáveis.
- PostgreSQL é runtime. SQLite pode apoiar testes de aplicação, sem servir como evidência das garantias PostgreSQL.
- O primeiro dashboard informa ausência de dados até existir pipeline real.
- Redis Streams/Taskiq e transporte resistente a SSRF permanecem condicionados a prova técnica. Não habilitar chamadas arbitrárias antes de validar o destino na conexão efetiva.

## Fontes de infraestrutura

A ordem de subida será governada por probes e dependências Compose conforme a [documentação oficial](https://docs.docker.com/compose/how-tos/startup-order/). As imagens de [PostgreSQL](https://hub.docker.com/_/postgres) e [Redis](https://hub.docker.com/_/redis) serão fixadas e verificadas na execução local.
