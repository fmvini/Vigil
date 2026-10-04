# Roadmap de implementação

Cada etapa exige testes, atualização de `DEVELOPMENT_LOG.md` e commit local. Não há push automático.

| Fase | Entrega | Evidência de conclusão |
| --- | --- | --- |
| 0 | Contratos, estrutura, ambiente local e documentação | Dependências fixadas; comandos de execução e verificação documentados |
| 1 | Persistência e contas | Migration PostgreSQL; cadastro/login/logout; CSRF; testes de isolamento e sessão |
| 2 | Projetos, monitores e dashboard inicial | CRUD, cotas, configuração, pausa e arquivamento integrados à UI |
| 3 | Transporte HTTP seguro e regras puras | Testes de IP/DNS/rebinding/SNI/TLS, retries, orçamento e transições de saúde |
| 4 | Pipeline durável | Scheduler, publicação, lease, finalização e recuperação; testes reais PostgreSQL/Redis |
| 5 | Histórico, incidentes e métricas | Idempotência; recuperação; uptime e p95 verificáveis sem APIs externas |
| 6 | SSE e status pública | Autorização, reconciliação, polling e DTO público sem dados privados |
| 7 | Operação e revisão do MVP | Retenção, backup/restore, carga, acessibilidade e controles de egress |

Frontend, backend e banco trabalham em paralelo dentro de cada fase. Nenhuma fase é considerada concluída apenas porque arquivos foram gerados; limitações de infraestrutura e testes não executados ficam registradas.
