# Relatório auditável de latência UI/SSE — v3

Unidade de tooling: `scripts/live-latency-smoke.mjs`, observador CDP e replay offline. Nenhuma mudança no produto, transporte, jobs ou marca. A coleta física v2 já concluída permanece histórica; seus bytes não são reescritos e não se fabricam evidências para convertê-la a v3. A primeira coleta física v3 aguarda outra janela própria do Maestro.

## Envelope e evidência por atualização

`report_version` passa de 2 para 3. Campos v2 de amostras, resumos, erros, rede, metodologia e cleanup permanecem. Adições: `identities.initial_project_revision`, descrição da evidência em `methodology.evidence` e `updates[].evidence`.

Há no máximo 29 atualizações, incluindo quatro warmups. Uma atualização sem testemunho completo mantém `evidence: null`; o diagnóstico continua em códigos estáticos, sem copiar nomes inesperados ou erros brutos. Um relatório failed pode conter testemunhos válidos das etapas anteriores, mas não é aprovado pelo replay.

| Campo em `updates[].evidence` | Fonte e unidade |
| --- | --- |
| `run_id`, `project_id` | UUID do run e do projeto privado singleton já capturados no setup |
| `expected.revision`, `expected.name` | Revisão esperada e `QA latency <run UUID> #001` até `#029`, igualdade exata com `nameFor(ordinal)` |
| `cdp.sse.request_id` | ID CDP do stream EventSource nativo; normalmente se repete entre atualizações |
| `cdp.sse.project_id`, `revision`, `timestamp_s` | Projeto/revisão do sinal próprio e timestamp monotônico CDP em segundos |
| `cdp.product_get.request_id` | ID CDP do GET do produto que terminou; o mesmo ID indexa request, response e corpo JSON |
| `cdp.product_get.started_s`, `completed_s` | Timestamps monotônicos de início e conclusão do GET, em segundos |
| `cdp.product_get.project_id`, `revision`, `name` | Projeção do único projeto próprio no snapshot GET; nome QA observado deve ser exatamente o esperado |
| `browser.viewport`, `viewport_width`, `viewport_height` | Desktop1440×900 ou mobile390×844; dimensões observadas no navegador |
| `browser.realm_time_origin_ms` | `performance.timeOrigin` observado identifica o realm da página, estável entre viewports; não é clock CDP nem assinatura |
| `browser.patch_started_ms`, `dom_observed_ms`, `dom_name` | `performance.now()` antes do PATCH e no MutationObserver; nome lido efetivamente do heading no instante observado |

O requestId do GET deve ser único entre as 29 atualizações e distinto dos IDs de streams SSE. Não se exige unicidade do stream nem se afirma que SSE e GET são a mesma requisição. IDs devem ser strings CDP limitadas a 128 caracteres (`A–Z`, `a–z`, dígitos, `_`, `.`, `:`, `-`). UUIDs de run/projeto também exigem strings primitivas; arrays e objetos que convertam para UUID não podem entrar na projeção.

O serializador projeta somente esses campos, sem spreads de payloads. Não persiste corpo GET/SSE, query, headers, cookies, CSRF, credenciais, e-mail ou URL privada. Nomes observados fora do nome QA exato são recusados antes da serialização. O observador rejeita snapshots sem o singleton próprio; requisições marcadas de medição não provam reconciliação. A origem loopback e caminhos de assets públicos existentes no envelope v2 continuam como metadados locais.

## Replay offline

Da pasta `frontend`, com Node e sem serviços:

```powershell
node scripts/live-latency-replay.mjs .impeccable/review/live-latency/<run-UUID>/report.json
```

O CLI só lê o arquivo e emite um resultado compacto. `passed_replay` retorna exit0; `failed_replay`, entrada inválida ou `unsupported_report_version` retornam exit1. v2 recebe `unsupported_report_version` com código estático `UNSUPPORTED_REPORT_VERSION`; nenhuma migração ou escrita ocorre. O arquivo failed v3 e seus diagnósticos são preservados; a saída do CLI não ecoa dados arbitrários da entrada.

O replay verifica:

- 29 ordinais/revisões consecutivos desde `initial_project_revision`; desktop com dois warmups/13 medidos, mobile com dois warmups/12 medidos. Identidade/run/nome/projeto/status/flags devem corresponder ao testemunho.
- Ordem `SSE.timestamp_s ≤ GET.started_s ≤ GET.completed_s`, deltas CDP válidos e requestIds dos GETs únicos. Ordem de atualizações também é verificada dentro de cada clock, sem cruzar clocks.
- `PATCH.started_ms ≤ DOM.observed_ms`, realm estável, viewport correto e nome DOM igual ao nome QA esperado. Recalcula `(DOM - PATCH)` em milissegundos e `(GET - SSE) × 1000` a partir dos respectivos clocks; tolerância apenas aritmética de 0,000001ms.
- 264 REST: quatro rotas `projects`, `monitors`, `metrics`, `incidents`, cada uma com 30 medidos e três warmups por viewport. Ordinais, sucesso200, números finitos/não negativos e contagens são validados.
- Todos os resumos nearest-rank: rota/viewport, pooled identificado como mistura, PATCH RTT, PATCH→DOM, SSE→GET e subconjunto sem sobreposição periódica observada. Nenhum warmup entra nos quantis.
- Erros/statuses inesperados vazios, gates/checks inalterados, um owner/projeto e zero monitores/checks; guards de owner/singleton/archive, logout e revogação confirmados, sem commit desconhecido. Esses registros não substituem inspeção da infraestrutura.

Metadados adicionais compatíveis com v2 podem permanecer no envelope/resumos; o replay compara os campos conhecidos sem copiá-los para a saída. A evidência nova tem whitelist estrita, recusando campos adicionais. Ao terminar uma coleta v3 que seria passed, o runner executa esse replay em memória após o cleanup; inconsistência muda o resultado para failed com o código estático correspondente.

## Metodologia e limites preservados

240 REST e 25 PATCH medidos, mais 24 REST/quatro PATCH de aquecimento; mínimo100ms entre inícios REST e1000ms entre PATCHs, deadline10s. Setup, leituras do produto, polling e cleanup acrescentam requisições fora das amostras. Owner/projeto próprios, vazio, privado, sem monitores; gates false e nenhuma alteração de seed/runtime alheio. Archive/logout/token antigo são confirmados pela API; o tooling não faz purge de banco. Logs de remoção dos containers/redes pertencem à campanha do Maestro.

EventSource/fetch do produto permanecem nativos e polling/periodic ativos. O replay permite reconstruir a consistência do pareamento selecionado e dos deltas, mas não é trace bruto, assinatura criptográfica ou prova de autenticidade de um arquivo adulterado. A observação de DOM não comprova paint. PATCH-start→DOM é limite superior para a parcela após commit; não mede o instante exato de commit. Nenhuma comparação de timestamp CDP com `performance.now()` ou `performance.timeOrigin` é feita. Mesmo sem periodic_overlap observado não se demonstra causalidade exclusiva de SSE.

Uma API/projeto vazio não comprova fanout Redis entre réplicas, pipeline, capacidade sustentada ou SLA. Com 25 amostras p99 coincide com o máximo; com13/12 por viewport p95/p99 coincidem com o máximo. Fixtures dos testes exercitam tooling e não fornecem latências reais para a campanha.

## Validação desta unidade

- Sete testes Node ampliados: replay completo/summaries, corruptions de clocks/revisão/requestIds/run/ordinal/DOM, requests simultâneos com conclusão inversa, tag/status/abort/foreign-singleton, projeção de campos privados e v2/failed/cleanup recusados.
- Um teste Edge real contra fixture HTTP/SSE efêmera própria observa requestIds CDP, tempos de conclusão, nome DOM efetivamente lido e projeção sem sentinelas. Nenhum serviço/produto compartilhado é usado.
- Typecheck e build local aprovados. A validação física v3 permanece pendente de nova janela do root; os testes não reexecutam nem alteram o relatório real v2.

Revisão de 2026-10-06: corrigida coerção do UUID de projeto no builder, com regressão de array e String encapsulada nos mesmos testes. Sete testes Node sem isolamento, typecheck e sintaxe passaram novamente. Nesta sessão, build/esbuild e launch Edge estão bloqueados por `spawn EPERM`; a aprovação anterior de build/fixture não equivale a nova execução física. Nenhuma campanha v3 foi executada nessa revisão. Smoke jobsUI/API real foi realizado separadamente pelo portal com projeto QA vazio, conforme `IMPLEMENTATION.md`; não fornece evidência para a campanha de latência v3.
