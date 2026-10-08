# Vigil online no plano gratuito

O perfil gratuito combina uma página web no Render Free, um projeto Neon separado
e um workflow público do GitHub Actions com agenda configurada a cada
15 minutos, sem prazo garantido de execução. As contas e os dados locais continuam separados; não existe migração
automática dos monitores locais para a nuvem.

## Instância publicada

**[https://vigil-4q06.onrender.com](https://vigil-4q06.onrender.com)** está publicada
desde 2026-10-06. Crie uma conta e cadastre seus endpoints na página; a conta e os
monitores do ambiente local não aparecem automaticamente nesta instância.

O Render usa Free/Hobby, sem cartão cadastrado, e auto deploy desativado. O Neon
usa projeto exclusivo `vigil`, schema privado `vigil`, compute 0.25 CU e suspensão
após cinco minutos. O repositório GitHub é público e a variável de agenda
`VIGIL_FREE_CHECKS_ENABLED` está `true`. Nenhum plano pago foi contratado.

Release de implementação: `6e6c87b`. Live e ready retornaram 200, runtime-config
confirmou 900/900, e o site carregou o novo bundle `index-Q0hhzUNE.js`.
A [execução manual 37505959414](https://github.com/fmvini/Vigil/actions/runs/37505959414)
concluiu em 40 segundos, com um job completed, backlog zero, status ok e cleanup
confirmado. O check HTTPS público retornou 200 e foi persistido em
`2026-10-06T17:45:36.478157Z`, com saúde online na página. Isso comprova a execução
no runner remoto; a cadência continua best-effort, sem garantia de 15 minutos.
Em 2026-10-08, a [rodada automática 37785218408](https://github.com/fmvini/Vigil/actions/runs/37785218408)
foi conferida: evento `schedule`, success em 32 segundos, status ok e cleanup
confirmado; nenhum monitor elegível nessa rodada. Os dois últimos eventos schedule
observados começaram às 06:09 e 13:32 UTC, separados por cerca de 7h23. A agenda
de 15 minutos não representa a frequência efetivamente demonstrada; atrasos de
horas foram observados e o perfil gratuito não oferece monitoramento pontual.
A [rodada manual 37792782610](https://github.com/fmvini/Vigil/actions/runs/37792782610)
validou novamente cadastro/login/projeto/monitor próprios e persistiu um check
HTTPS200 em `2026-10-08T14:29:15.031193Z`, latência82ms e saúde online no dashboard
e na status pública. Histórico e métricas retornaram uma amostra real; runner
success40s, um job completed, backlog zero e cleanup confirmado.
O projeto QA foi arquivado (privado/público404), lista própria vazia e logout
confirmado; conta/histórico permanecem sujeitos à retenção normal. Essas provas
usam o release publicado `6e6c87b`, sem o novo modo escuro ainda local.

## Componentes

- `infra/free-cloud/Dockerfile`: recompila React e serve frontend/API na mesma
  origem HTTPS, com sessões Secure/HttpOnly e CSRF.
- `scripts/free_cloud_start.py`: bootstrap explícito do schema privado `vigil` e
  `alembic upgrade head` antes de iniciar a API. Não usa stamp ou create_all.
- `.github/workflows/free-checks.yml`: agenda UTC `2,17,32,47 * * * *` e execução
  manual, somente no branch principal de repositório público não fork.
- `scripts/free_cloud_checks.py`: bridge Docker exclusiva e recursos identificados
  por UUID/labels, relay TCP e executor protegido com cleanup verificado.
- `backend/app/monitoring/batch.py`: rodada durável sem Redis, até 90 segundos,
  cinco execuções simultâneas e cem jobs por padrão. Não reserva leases enquanto
  aguarda capacidade; reutiliza claims, retries e finalização transacional.

O relay só conecta aos IPs públicos resolvidos do endpoint Neon. O executor mantém
o hostname original para TLS com CA e hostname verificados, mas acessa o relay
privado na porta 5432. Firewall IPv4/IPv6, UID/GID 10001, capabilities zeradas e
no-new-privileges permanecem obrigatórios. Alvos são HTTP/HTTPS públicos nas portas
80/443; DNS privado, redirects e proxy de ambiente não são atalhos suportados.

## Configuração

No Render, usar `render.yaml` ou criar um Web Service Docker Free com contexto na
raiz e Dockerfile `infra/free-cloud/Dockerfile`. Health check `/health/live`; conferir
`/health/ready` depois do deploy. Não usar probes frequentes de readiness para
manter o Neon acordado. O bootstrap obtém a origem HTTPS de `RENDER_EXTERNAL_URL`.

Guardar `VIGIL_DATABASE_URL` apenas nos secrets do Render e GitHub Actions:

```text
postgresql+asyncpg://ROLE:SENHA_PERCENTENCODE@ep-ENDPOINT.REGIAO.aws.neon.tech:5432/neondb
```

Usar o endpoint **direto**, com Connection pooling desativado. Remover a query
libpq (`sslmode`/`channel_binding`); a aplicação configura SSLContext explicitamente.
Não imprimir a DSN, enviá-la ao frontend ou salvá-la no Git. O perfil recusa endpoints
`-pooler`: configuração de sessão não é contrato de pool em modo transaction.

Configuração aplicada pelo bootstrap/runner:

| Configuração | Nuvem | Padrão local |
| --- | --- | --- |
| `VIGIL_DATABASE_SCHEMA` | `vigil` | não definido |
| `VIGIL_DATABASE_SSL` | `true` | `false` |
| `VIGIL_DATABASE_POOL_SIZE` / `MAX_OVERFLOW` | `2` / `0` | `5` / `5` |
| `VIGIL_READINESS_TIMEOUT_SECONDS` | `10` | `3` |
| `VIGIL_REDIS_ENABLED` | `false` | `true` |
| `VIGIL_MINIMUM_INTERVAL_SECONDS` | `900` | `60` |
| `VIGIL_SCHEDULED_CHECKS_INTERVAL_SECONDS` | `900` | não definido |
| `VIGIL_PIPELINE_ENABLED` / `MONITORING_NETWORK_ENABLED` | API: `false`; runner: `true` | `false` |

A factory seleciona o schema também por SQL de sessão na conexão física, para
proxies que descartam parâmetros do startup. Não cria schema, não inclui fallback
`public`, e o ajuste permanece após rollback. Alembic usa version_table_schema e
SET LOCAL dentro da transação; apenas o bootstrap cria o schema privado.

Após validar o deploy e uma rodada real, definir a variável de repositório
`VIGIL_FREE_CHECKS_ENABLED=true`. Para suspender os checks, usar `false` sem apagar
dados. O workflow não roda em PRs, usa runner Linux padrão e permissões contents:read.
CA adicional, quando necessária e aprovada, pode ser secret `VIGIL_DATABASE_CA_PEM`;
a verificação TLS permanece ativa. Não configurar credenciais nos comandos.

## Comportamento e limites

A UI lê `/api/v1/runtime-config` ao abrir o formulário. Exige intervalo mínimo de
900 segundos e informa que a agenda pode atrasar. Monitores legados abaixo do
mínimo permanecem legíveis, mas não são agendados; a edição exige ajuste explícito.
Os slots omitidos não recebem checks fabricados. O batch usa o instante real de
admissão e respeita intervalos maiores, leases e orçamento restante.

Sem Redis, sinais de mutação são locais à instância web. Resultados do runner
aparecem pela leitura REST e polling de 30 segundos; não há fanout entre réplicas.
O relatório distingue tentativas, estados persistidos, backlog, retenção e fase de
falha. Timeout de preflight/consulta não equivale ao prazo global. Retenção tem até
dez segundos por batch dentro do mesmo prazo global, statement/lock timeout de um
segundo e contagens somente depois do commit. Rodada parcial retorna exit 1.

Retenção: resultados/jobs 30 dias, incidentes encerrados 90 dias e sessões inválidas
há mais de sete dias. Sem apagar snapshots, jobs ativos ou incidentes abertos.

Os limites oficiais consultados em 2026-10-06:

- [Render Free](https://render.com/docs/free): dorme após 15 minutos sem tráfego;
  reativação pode levar cerca de um minuto. Há cotas de horas, banda e builds.
  Manter Free e não adicionar cartão/upgrade; ultrapassar cotas pode suspender o serviço.
- [Neon Free](https://neon.com/blog/neon-free-plan-1-gb-per-project): 1 GB e
  100 CU-hours por projeto/mês. Compute 0.25 CU e scale-to-zero ajudam a economizar;
  UI aberta, polling, retries e migrações também consomem compute. Uso contínuo pode
  esgotar a cota; não há capacidade garantida de monitores sem medir bytes reais.
- [GitHub Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions):
  runners padrão são gratuitos para repositórios públicos. Não mudar este perfil
  para runner maior ou repositório privado sem reavaliar custo.
- [Agenda GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule):
  pode atrasar ou perder rodadas; agendas públicas podem ser desativadas após
  60 dias sem atividade no repositório. Não oferece SLA nem monitoramento de um minuto.

## Verificação operacional

1. Confirmar live/ready 200, runtime-config 900/900 e assets do novo build.
2. Cadastrar um monitor próprio de endpoint público, executar o workflow manual e
   conferir resultado persistido/último check na UI. Readiness não comprova escrita
   disponível sob quota e `consumers_registered` não comprova executor ativo.
3. Conferir `completed=true`, status ok e cleanup confirmado na saída do runner.
   Em falha, verificar stage/error_code e backlog sem copiar DSNs ou logs privados.
4. Conferir uma execução agendada e as cotas nos portais. Para QA, arquivar somente
   projeto próprio e fazer logout; não purgar dados de outros usuários.

As provas de publicação e execução estão no [DEVELOPMENT_LOG](DEVELOPMENT_LOG.md).
Para conferir a agenda atual, abrir as [execuções do workflow](https://github.com/fmvini/Vigil/actions/workflows/free-checks.yml)
e filtrar pelo evento schedule; uma execução manual não comprova a cadência.
