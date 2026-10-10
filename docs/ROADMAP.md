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

## Estado de continuidade em 2026-10-10

- As fases 0–6 possuem implementação e evidências históricas de aplicação, PostgreSQL, Redis e navegador no DEVELOPMENT_LOG/OPERATIONS. A retomada parte das fontes existentes, sem recriar os incrementos iniciais ou interpretar essas provas como validação de uma nova release.
- A fase 7 possui retenção, tooling de backup/restore, ensaios de carga/recovery/egress e diagnóstico implementados. Continua com pendências de validação no ambiente alvo; acessibilidade, capacidade sustentada e recuperação completa não estão certificadas globalmente.
- O ponto de retomada local `98414a5` contém políticas, aceites e página 404; Alembic possui head `0003_legal_acceptances`. O redesign seguinte possui implementação e requisito de fidelidade ainda aberto. `origin/main` local e registros de release são evidências históricas, sem consulta atual ao remoto/Render nesta retomada.
- Próxima unidade de interface: concluir o objetivo material de superfícies e hierarquia tonal do console contra o comp aprovado, preservando geometria e dados. O gate de fidelidade permanece aberto até nova medição aprovada ou decisão explícita do usuário; retomada não libera o requisito.
- Correção operacional desta retomada: incluir `legal_acceptances` no manifesto do backup Compose. Executar o ensaio físico com oito tabelas de produto em PG17/Compose quando disponível, sem apontar o helper para PG18 ou migrar a origem para passar a validação.
- Antes de publicação integrada, preencher as pendências de contato/conservação em LEGAL, executar os checks de release em ambiente capaz, aplicar a migration no destino correto e validar frontend/API juntos. Envio e publicação permanecem sujeitos a instrução explícita; não há push automático.
