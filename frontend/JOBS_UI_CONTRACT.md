# Contrato — Falhas do processamento do Vigil

Estado: DTO e fontes da API congelados com Backend/Banco em 2026-10-05.
Componente readonly implementado, com testes/build e revisão visual finais
aprovados. A API passou em PostgreSQL real; a seção no navegador foi validada
com transporte sintético, conforme os limites descritos abaixo.

## Leitura privada

`GET /api/v1/projects/{id}/jobs`, autenticado, somente leitura.

- `status=all|exhausted|expired`, default `all`: inclui somente os dois estados terminais.
- `monitor_id` opcional: pausados incluídos, arquivados excluídos. Monitor alheio,
  arquivado ou inexistente retorna o mesmo 404; projeto de outro owner também retorna 404.
- `period=24h|7d|30d`, default `24h`, ou janela ISO `from`/`to`.
- Janela `[from,to)` sobre `scheduled_at`, até 30 dias; futuro/faixa fora de 30 dias
  são recusados, sem clamp. Resposta conserva a faixa pedida em UTC.
- `limit` default 20/máximo 100; `offset >= 0`.
- Ordem `scheduled_at DESC, id DESC` estável dentro do snapshot. Offset entre
  requests pode repetir/omitir linhas com novas entradas ou retenção; não é cursor persistido.

Envelope exato: `items`, `total`, `from`, `to`, `computed_at`, `retention_days` (30).
Os três timestamps do envelope usam ISO UTC.

Item exato:

| Campo | Contrato |
| --- | --- |
| `job_id`, `monitor_id` | UUID |
| `config_version` | inteiro >= 1 |
| `status` | `exhausted` ou `expired` |
| `scheduled_at`, `finished_at` | ISO UTC não nulo |
| `execution_count` | inteiro 0..3; claims técnicos do worker, não retries HTTP |
| `error_code` | allowlist abaixo ou null; demais códigos viram null no backend |

Sem URL/config snapshot/lease/erro bruto. Consulta de dados usa snapshot RR/RO;
isso não representa prova física de PostgreSQL/índices. A retenção de 30 dias usa
`finished_at` e elegibilidade: janela pedida ou lista vazia não comprova cobertura.

## Léxico estático proposto

| Código recebido | Texto público |
| --- | --- |
| `internal_error` | Falha interna do processamento |
| `execution_crashed` | Execução do processamento interrompida |
| `pool_exhausted` | Recursos de execução indisponíveis |
| `blocked_destination` | Destino bloqueado pela política de acesso |
| `database_error` | Falha no acesso ao banco de dados |
| `insufficient_budget` | Tempo disponível insuficiente para executar |
| `deadline_exceeded` | Prazo de processamento excedido |
| `execution_limit` | Limite de execuções de processamento atingido |
| null ou desconhecido | Não informado |

Não usar o fallback genérico `reason()` que imprime códigos desconhecidos.
Situações propostas: `exhausted` = Execuções esgotadas; `expired` = Prazo encerrado.

## Composição e validação

- Componente novo independente; `App` limitado a import/mount. Preservar unidades
  estáveis de auth, sincronização e filtro de qualidade.
- Seção discreta intitulada **Falhas do processamento do Vigil**, separada de
  incidentes; expandir para consultar, sem requisitar dados quando fechada.
- Filtros situação/período/monitor e paginação somente leitura. Recarregar lista
  significa GET; não oferecer execução, retry ou mutação de jobs.
- Monitor identificado pelo nome do snapshot corrente, sem URL; fallback estático
  para nome indisponível. Horários podem ser formatados no fuso local com indicação
  explícita, mantendo os timestamps UTC recebidos.
- Mostrar faixa/retention/computed_at; explicar retenção e possível mudança entre
  páginas. Vazio não confirma cobertura. Erros de consulta não declaram offline ou
  saúde do alvo; não duplicar indicadores de saúde nesta seção.
- Validar allowlist/null/desconhecido sem raw code/segredos, somente GET autenticado,
  filtros/paginação/reset, carregamento/erro/retentativa de leitura, cancelamento ao
  trocar projeto/fechar seção e nenhuma leitura enquanto fechada.
- Verificar teclado e layout desktop/mobile em fixture própria; manter evidência
  sintética separada de integração API/PG real e de qualquer campanha de latência.

Implementação atual: `src/ProcessingFailures.tsx`, CSS próprio e oito regressões
em `src/test/ProcessingFailures.test.tsx`; `App` contém somente import/mount novo.
O hook `useResource` já exportado em `Observations.tsx` foi reutilizado sem alteração:
revisões enquanto uma leitura está pendente agrupam uma nova consulta, sem prometer
limite de frequência global. Fechar/trocar projeto/remover monitor aborta leituras
antigas, incluindo proteção dos callbacks401 existentes. Monitor removido reinicia
Todos/offset0. Validação central final:72 Vitest passed/zero skips e build aprovado
após CSS44px, UUID da fixture e mounts Brand. Edge verificou seis estados lista/vazio/
erro em1440/390, sem overflow/erros e controles44px; relatório
`.impeccable/review/processing-failures/report.json` passed. A API congelada foi
validada separadamente por sete casos PG reais, incluindo RR/RO e COUNT/página
durante commits concorrentes, no QA Backend descartável. As capturas da seção
usam API sintética: não demonstram integração da seção no navegador com PG real.

Em 2026-10-06 a seção foi exercitada pelo portal `Frontend QA` contra API real
em8000, com Vite preview do dist existente em5173 e PG18/head0002 informado pelo
Maestro. Conta/projeto QA privados próprios vazios:17 consultas do produto200,
situações all/exhausted/expired e períodos24h/7d/30d, reload, fechamento por40s
sem nova consulta e reabertura nos defaults. Desktop1440/mobile390 sem overflow,
controles44px e mensagens de vazio/retention corretas. Archive404/lista vazia e
logout204/me401 confirmados; owner/projeto arquivado retidos pela API. Evidência
`.impeccable/review/live-latency-resume-20261006/jobs-api-real.json` e duas capturas.
Esse smoke comprova leitura integrada do dataset vazio; não demonstra linhas,
paginação populada, monitor específico, planos PG17, keyboard nativo ou token
antigo revogado. Nenhum dado do usuário, seed histórico ou gate foi alterado.
