# Contrato inicial de API

Base: `/api/v1`. JSON, UUIDs e datas ISO 8601 em UTC. O OpenAPI gerado em `/docs` descreverá os DTOs efetivamente implementados; este documento registra o acordo entre agentes. Regras e limites: [REQUIREMENTS](REQUIREMENTS.md).

## Convenções

- Listas retornam `{ "items": [...], "total": 0 }`; paginação por `limit` e `offset`.
- Erros retornam `{ "error": { "code": "...", "message": "...", "details": null } }`.
- Validação retorna 422 `validation_error` com `details` contendo somente `field` e `type`. Campos declarados e índices numéricos são preservados; chaves JSON extras são informadas pelo caminho do objeto pai (`body`, por exemplo), sem repetir o nome fornecido pelo cliente, valores ou contexto do validador.
- Respostas incluem `X-Request-ID` UUID gerado pela API para correlação com logs de atividade; um header de mesmo nome recebido do cliente é substituído. Não é credencial ou ID de sessão.
- Recursos de outro proprietário retornam 404. Dados de sessão/hash nunca integram DTOs públicos.
- Mutações do navegador enviam `X-Vigil-Request: browser` e Origin autorizado. Depois do login também enviam `X-CSRF-Token`.
- Frontend e API compartilham origin; em desenvolvimento o Vite encaminha `/api` ao FastAPI.
- Cookie de desenvolvimento `vigil_session`; em produção `__Host-vigil_session`, Secure, HttpOnly, SameSite=Lax, Path=/.

## Primeiro incremento

| Método | Rota | Resultado |
| --- | --- | --- |
| POST | `/auth/register` | 201; usuário criado, sem login automático |
| POST | `/auth/login` | 200; `{user, csrf_token}` e cookie de sessão |
| GET | `/auth/me` | 200; `{user, csrf_token}` ou 401 |
| POST | `/auth/logout` | 204; revogação da sessão e remoção do cookie |
| GET/POST | `/projects` | Lista / criação do projeto |
| GET/PATCH/DELETE | `/projects/{id}` | Consulta / edição / arquivamento lógico |
| GET/POST | `/projects/{id}/monitors` | Lista / criação de monitor |
| GET/PATCH/DELETE | `/monitors/{id}` | Consulta / edição / arquivamento lógico |
| POST | `/monitors/{id}/pause` | Pausa, preservando saúde e histórico |
| POST | `/monitors/{id}/resume` | Retomada e nova agenda |

Cadastro/login recebem `{email,password}`. Projeto recebe `name`, `description` opcional e `public_status_enabled` (false por padrão). Monitor recebe `name`, `url`, `interval_seconds`, `timeout_ms`, `expected_status`, `failure_threshold`, `retry_count`, `latency_threshold_ms` e `is_public`. O servidor define IDs, proprietário, método GET, versão e agenda.

Senha: 10–128 caracteres; e-mail normalizado por trim/lowercase. Listas: `limit=20` por padrão, máximo 100, `offset>=0`. Criações retornam 201; DELETE retorna 204 e é idempotente para recurso já arquivado. Pausa/retomada retornam o monitor atualizado (200).

Saúde (`null/online/degraded/offline`) e freshness (`no_data/fresh/stale/paused`) são campos separados. Sem medições reais, não exibir uptime/latência inventados.

Probes fora do prefixo: `GET /health/live` e `GET /health/ready`. Liveness não depende do banco. Readiness exige conexão e uma única revision em `alembic_version`, igual ao head resolvido dos arquivos de migration da aplicação; revision ausente, antiga, desconhecida ou múltipla resulta em `503 not_ready` sanitizado. A verificação respeita o deadline configurado, usa somente SELECT e nunca aplica migrations. Confirma a versão declarada, sem auditar a integridade global do schema. Somente engines SQLite injetadas explicitamente em testes dispensam Alembic.

## Histórico, métricas e incidentes

| Método | Rota | Resultado |
| --- | --- | --- |
| GET | `/monitors/{id}/checks` | `{items,total}` com ciclos finais, tentativas sanitizadas e saúde resultante |
| GET | `/monitors/{id}/metrics` | Agregação de amostras do monitor |
| GET | `/projects/{id}/metrics` | Agregação de todas as amostras dos monitores ativos |
| GET | `/projects/{id}/incidents` | `{items,total}` de incidentes privados, filtráveis por monitor e estado |

Checks/métricas aceitam `period=24h|7d|30d` (default 24h), ou `from` e `to` juntos com timezone explícito. Janela semiaberta `[from,to)`, dentro dos últimos 30 dias. Incidentes aceitam também `90d` (default 30d), `state=all|open|closed` e `monitor_id` opcional; incluem incidentes que se sobrepõem à janela, inclusive abertos iniciados antes dela. Listas usam `limit`/`offset`.

Nas quatro rotas privadas, `from`/`to` devem ser datas ISO 8601; valores epoch numéricos em segundos/milissegundos são rejeitados com422, sem inferir UTC. Offsets válidos e `Z` são normalizados para UTC; regras de timezone, retenção e intervalo continuam obrigatórias. Incidentes públicos usam `period`, sem parâmetros explícitos `from`/`to`.

Métricas retornam `from`, `to`, `computed_at`, `success_count`, `failure_count`, `sample_count`, `latency_sample_count`, `uptime_percent`, `average_latency_ms`, `p95_latency_ms`, `excluded_count`, `cancelled_count`, `pending_count`, `skipped_slots`, `health_status`, `data_complete`, `freshness_counts`, `bucket_seconds` e `series`.

- Sem ciclos avaliados: uptime/média/p95 nulos e contagens zero. Expired/exhausted são exclusões, não falhas do alvo; cancelled é separado.
- p95 PostgreSQL usa percentile_cont sobre latências finais de sucesso, inclusive no agregado do projeto. Não se faz média de percentis de monitores.
- Série: buckets UTC por hora para janelas até 24h, por dia nas demais. Cada ponto contém `bucket_start` e as mesmas estatísticas de amostras/latência, calculadas naquele bucket. Buckets vazios são omitidos, não preenchidos com sucesso.
- `health_status` e qualidade referem-se ao snapshot atual, independentemente da janela histórica selecionada.
- `skipped_slots`/contadores de jobs revelam algumas lacunas, sem prometer cobertura temporal completa.
- Leituras de observações usam snapshot PostgreSQL REPEATABLE READ/READ ONLY, mantendo resumo e série consistentes durante commits concorrentes. Autenticação/atividade termina antes desse snapshot; mutações continuam com seu isolamento próprio.

Check privado contém IDs, versão, timestamps, outcome, status HTTP, latência, duração do ciclo/fila, quantidade e resumo de tentativas, código sanitizado de erro, saúde e motivo de degradação. Incidente privado contém IDs/monitor_name, timestamps, end_reason, cause_code, threshold e referências de evidência. Nenhuma rota permite acesso cruzado entre proprietários.

`duration_ms` no resumo de tentativa pode ser nulo se não foi registrado; duração total do ciclo continua separada. Campos desconhecidos do JSON de tentativa não são expostos pelo DTO.

## Falhas do processamento

`GET /projects/{id}/jobs` oferece leitura privada de jobs terminais, separada de incidentes e de falhas do endpoint. A interface consulta somente ao expandir a seção Falhas do processamento do Vigil. API e componente estão implementados; as provas PostgreSQL 17 de leitura e migrations são registradas em [OPERATIONS](OPERATIONS.md), separadas dos ensaios visuais com API sintética.

- `status=all|exhausted|expired`, default `all`, inclui somente exhausted e expired. `monitor_id` é opcional; monitores pausados entram, arquivados não. Projeto/monitor alheio, arquivado ou inexistente retorna 404.
- `period=24h|7d|30d`, default 24h, ou `from`/`to` ISO com timezone explícito. Janela `[from,to)` sobre `scheduled_at`, dentro dos últimos 30 dias; reutiliza a validação das observações, inclusive rejeição de epoch.
- `limit=20` por padrão, máximo 100; `offset` entre 0 e 9223372036854775807 (inteiro representável em BIGINT). Valores superiores retornam 422 sanitizado; esse teto não limita o custo da consulta. Ordem `scheduled_at DESC, id DESC`. Contagem e itens usam a mesma população no snapshot da resposta.
- Envelope exato: `items`, `total`, `from`, `to`, `computed_at`, `retention_days` (30). Item: `job_id`, `monitor_id`, `config_version`, `status`, `scheduled_at`, `finished_at`, `execution_count`, `error_code`.
- Datas são UTC e `finished_at` não é nulo. `execution_count` conta claims do worker (0–3), não tentativas HTTP. Códigos permitidos: `internal_error`, `execution_crashed`, `pool_exhausted`, `blocked_destination`, `database_error`, `insufficient_budget`, `deadline_exceeded`, `execution_limit`; desconhecidos retornam null.
- A projeção exclui URL, configuração, credenciais, lease, consumer e erro bruto. Não há publicação, replay, retry, ACK ou mutação nesta rota; ela funciona com os gates de execução desligados.

Autenticação/atividade termina antes da leitura REPEATABLE READ/READ ONLY; proprietário e recursos são conferidos dentro desse snapshot. Alterações posteriores de autorização podem não invalidar uma resposta já em curso. `computed_at` é horário de cálculo, não token de snapshot.

A retenção remove jobs elegíveis por `finished_at`; a janela consultada usa `scheduled_at`. Uma lista vazia não comprova cobertura de monitoramento ou execução da retenção. O snapshot estabiliza uma resposta, sem garantir paginação consistente entre requests. COUNT e OFFSET altos podem exigir trabalho além do tamanho da página; escolha de índices e custo ainda dependem de planos PostgreSQL com volume representativo.

## Status pública

- `GET /public/status/{slug}`: `{name,slug,revision,computed_at,health_status,data_complete,freshness_counts,monitors}`.
- Monitor público: `{id,name,health_status,freshness,last_checked_at}`.
- `GET /public/status/{slug}/incidents`: lista paginada, `state` e `period` até 90 dias. Incidente público: `{id,monitor_id,monitor_name,started_at,detected_at,ended_at,end_reason}`.
- Projeto precisa estar ativo com publicação ligada; cada monitor também precisa optar pela publicação e estar ativo. Projeto desabilitado/arquivado retorna 404.
- DTOs públicos excluem URL, descrição privada, e-mail, configuração, erros, tentativas e evidências. Pausados continuam visíveis como pausados.
- Frontend público usa polling de 30 segundos; sem cookie obrigatório ou token em URL.

## SSE privado

- `GET /events`: `text/event-stream`, autenticado por cookie same-origin. Não aceita parâmetros de query; Origin presente deve ser autorizado. Não exige token em URL ou header customizado do EventSource.
- Eventos `project.updated`, `monitor.updated`, `incident.opened` e `incident.closed` contêm IDs e `revision`, sem URL, proprietário ou evidência privada. Só chegam às assinaturas do proprietário correspondente.
- `snapshot.required` solicita ressincronização REST ao conectar, a cada 30 segundos e após backpressure. Não há replay persistente, Last-Event-ID ou garantia de entrega de cada sinal.
- Heartbeat em comentário a cada 15 segundos. Sessão é revalidada antes do primeiro sinal e a cada 30 segundos; revogação, expiração, conta inativa ou falha de validação encerram o stream. SSE não renova continuamente a inatividade.
- Limite de três conexões por conta **por processo API**, fila de 32 sinais por conexão e deadline de dez segundos por envio. Limite retorna 429 `sse_connection_limit`; encerramento libera o slot.
- Autenticação/atividade termina e libera a conexão DB antes de reservar o stream; a conexão SSE não mantém uma transação de longa duração.
- Redis Pub/Sub transporta invalidações entre processos. Sem Redis, sinais locais e ressincronização periódica continuam disponíveis. Publicação ocorre somente depois do commit e sua falha não reverte a mutação confirmada.
- Frontend reconcilia via REST, agrupa sinais próximos e consulta a cada 30 segundos, inclusive para streams silenciosos ou EventSource indisponível. Reconexão/retorno à aba também pede snapshot.

Os dados de monitoramento continuam ausentes enquanto o pipeline estiver desabilitado. Testes de fan-out determinístico não comprovam Redis Pub/Sub real entre réplicas.
