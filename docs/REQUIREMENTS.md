# Requisitos e regras de negócio

Versão inicial planejada em 2026-10-04. Os identificadores são estáveis; mudanças de comportamento devem atualizar este documento, os contratos afetados e o registro de decisões.

## Requisitos funcionais

| ID | Requisito |
| --- | --- |
| RF001 | Cadastrar usuário com e-mail único normalizado e senha; não retornar hash ou dados de sessão sensíveis. |
| RF002 | Autenticar, consultar conta atual e encerrar sessão; sessões devem ser revogáveis. |
| RF003 | Criar, listar, consultar, editar e arquivar projetos próprios. |
| RF004 | Criar, listar, consultar, editar e arquivar monitores de um projeto próprio. |
| RF005 | Configurar URL, intervalo, timeout, status esperado, falhas consecutivas para offline, retries e limiar de latência. |
| RF006 | Pausar/retomar monitores sem apagar histórico; não executar checks durante a pausa. |
| RF007 | Agendar verificações de monitores ativos sem depender de requisições à API. |
| RF008 | Executar GET com limites de tempo, concorrência e destino de rede; persistir resultado e resumo das tentativas. |
| RF009 | Consolidar um resultado por ciclo e tolerar publicação/reentrega duplicadas. |
| RF010 | Classificar saúde como online, degradado ou offline e informar ausência/desatualização dos dados separadamente. |
| RF011 | Aplicar retries de rede limitados sem contar cada tentativa como novo ciclo. |
| RF012 | Consultar histórico paginado por monitor e período. |
| RF013 | Abrir e encerrar incidentes automaticamente, preservando início observado e momento de detecção. |
| RF014 | Listar incidentes por projeto, monitor, período e condição aberto/encerrado. |
| RF015 | Calcular uptime por amostras, média e p95; retornar contadores e informações de qualidade dos dados. |
| RF016 | Exibir dashboard de projetos/monitores com métricas e incidentes. |
| RF017 | Enviar sinais SSE de alteração autorizados e ressincronizar o dashboard via REST. |
| RF018 | Habilitar/desabilitar página pública do projeto e selecionar monitores públicos. |
| RF019 | Consultar página pública e histórico público de incidentes sem expor URLs/configurações privadas. |
| RF020 | Aplicar retenção e arquivamento preservando integridade referencial. |

## Requisitos não funcionais

| ID | Requisito e verificação prevista |
| --- | --- |
| RNF001 | Isolamento por proprietário em todas as consultas, mutações e conexões SSE; testes devem tentar acesso cruzado. |
| RNF002 | HTTPS na exposição pública, cookies seguros, Argon2id, proteção CSRF e ausência de secrets em Git/logs. |
| RNF003 | Proteção SSRF na conexão real, IPv4/IPv6, redirects desativados e bloqueio de saída a redes internas/metadados. É condição para deploy público. |
| RNF004 | I/O de worker assíncrono, concorrência limitada, pools limitados e nenhuma transação/row lock mantida durante HTTP. |
| RNF005 | Jobs recuperáveis e commits idempotentes; testes com queda antes/depois do commit e reentrega devem preservar um resultado e um incidente aberto. |
| RNF006 | REST paginado, janelas limitadas e cache apenas de dados derivados; indisponibilidade do cache deve permitir leitura do PostgreSQL. |
| RNF007 | Baseline a validar: 100 monitores/minuto, um worker com até 50 ciclos concorrentes; medir também backlog e p95 do atraso de início. Não é capacidade garantida. |
| RNF008 | Meta inicial em ambiente de carga documentado: início de 95% dos ciclos em até 5 s após agendamento; leituras REST usuais p95 até 500 ms; sinal no dashboard até 3 s após commit. |
| RNF009 | UTC, `timestamptz`, relógio monotônico para durações e sincronização do relógio dos processos. |
| RNF010 | Logs estruturados, correlação por request/job, métricas de fila/scheduler/worker e probes separadas de liveness/readiness. |
| RNF011 | Testes de regras, contratos, integração PostgreSQL/Redis e fluxos de navegador; não depender de APIs externas nos testes determinísticos. |
| RNF012 | Componentes modulares com contratos explícitos; regras de negócio compartilhadas por API/worker sem duplicação. |
| RNF013 | Execução futura reproduzível com Docker/Compose, versões fixadas e configurações por ambiente. |
| RNF014 | Dashboard responsivo, navegação por teclado e estados claros de loading, erro, ausência de dados e conexão perdida. |
| RNF015 | Retenção, backup e restore testados antes do deploy; degradação do Vigil deve ser observável sem produzir falsa falha do endpoint. |

As metas de RNF007/RNF008 só se tornam resultados após teste de carga registrado com CPU/RAM, versões, tamanho do banco e distribuição de latência. PostgreSQL, Redis ou scheduler únicos podem interromper medições no MVP.

## Regras de negócio

| ID | Regra |
| --- | --- |
| RN001 | Um usuário possui projetos; cada projeto possui monitores. Não existem membros/RBAC no MVP. IDs UUID não substituem autorização. |
| RN002 | Limites: 5 projetos e 100 monitores ativos por usuário, 20 monitores ativos por projeto. Pausados contam no limite; arquivados não. Validar cotas em transação para evitar corrida. |
| RN003 | Método fixo GET. URL até 2.048 caracteres; somente HTTP/HTTPS, portas 80/443, sem credenciais, fragmento ou secrets. Não seguir redirects; status 3xx pode ser o status final esperado. |
| RN004 | `interval_seconds`: 60–3.600, default 60; `timeout_ms`: 1.000–15.000, default 5.000; `expected_status`: 200–599, default 200. Respostas intermediárias 1xx não são resultado final. |
| RN005 | `failure_threshold`: 1–10, default 3; `retry_count`: 0–2, default 1; `latency_threshold_ms`: nulo ou 100–15.000, default 1.000. Limiar não nulo deve ser menor ou igual ao timeout. |
| RN006 | Um ciclo inclui uma tentativa inicial e até `retry_count` tentativas extras. Após falha transitória, esperar 0,5 s e depois 1 s, com jitter de ±20%. Orçamento `B = (retries+1)*timeout + backoffs máximos + 3 s` deve ser ≤50 s e menor que o intervalo. |
| RN007 | Retentar timeout, erro de conexão/DNS transitório e resposta HTTP 5xx inesperada. Não retentar status 4xx/3xx inesperado, TLS inválido ou destino bloqueado. Se 5xx for o status esperado, é sucesso e não dispara retry. |
| RN008 | Sucesso é obter o status final exato esperado. Erro de rede, TLS inválido, timeout ou status diferente é falha do alvo. Bloqueio de política, pool local esgotado, crash e banco indisponível são problemas do Vigil, excluídos da disponibilidade. |
| RN009 | Falha final incrementa a sequência uma vez. Sucesso a zera. Tentativas e jobs duplicados não incrementam a sequência. Ciclos não avaliados interrompem a sequência de falhas, mas não recuperam um monitor offline nem encerram incidente. |
| RN010 | Offline tem prioridade quando uma sequência de falhas atinge o threshold. Antes disso, uma falha gera degradado. Um sucesso é degradado se precisou de retry ou se sua latência ≥ limiar; caso contrário é online. |
| RN011 | Antes do primeiro ciclo avaliado, `health_status=null`. `freshness`: `no_data`, `fresh`, `stale` ou `paused`; `stale` se a última medição é anterior a `max(2*interval_seconds, 120 s)`. Pausa prevalece. Dados stale não autorizam afirmar disponibilidade atual. |
| RN012 | Incidente abre apenas na transição para offline: `started_at` é início da primeira falha da sequência; `detected_at` é conclusão do ciclo que atingiu o threshold. Há no máximo um aberto por monitor. Lentidão e retries recuperados não abrem incidente no MVP. |
| RN013 | Primeiro sucesso após offline encerra incidente com `end_reason=recovered`, mesmo se a saúde resultante for degradada. Pausa e falta de dados não encerram incidentes nem aumentam indisponibilidade medida. |
| RN014 | Alterar configuração de check cancela jobs anteriores por versão, reinicia sequência/saúde e encerra incidente com `end_reason=configuration_changed`. Alterar apenas nome/visibilidade não faz isso. Arquivar encerra com `end_reason=archived`; nenhum desses encerramentos significa recuperação. |
| RN015 | Pausar cancela jobs em aberto e invalida o lease; mantém última saúde/incidente, mas reinicia sequência de falhas. Retomar agenda um novo ciclo e exige nova sequência para um novo incidente. Se já offline, permanece offline até sucesso. |
| RN016 | Uptime = `100 * success_count / (success_count + failure_count)`, sobre ciclos avaliados na janela `[from,to)` por `scheduled_at`. Um sucesso após retry conta uma vez. Zero ciclos → `null`, nunca 100%. Não representa uptime exato ponderado por tempo. |
| RN017 | Latência mede do início da tentativa até recebimento dos headers finais, incluindo conexão/DNS/TLS quando necessários, sem body. Média e p95 usam somente a última tentativa dos ciclos de sucesso. Fila, backoff e outras tentativas ficam em campos separados. |
| RN018 | p95 é o percentil contínuo interpolado sobre as latências elegíveis; retornar `latency_sample_count`. Nunca calcular p95 de um conjunto fazendo média dos p95 dos subconjuntos. |
| RN019 | Agregação do projeto soma sucessos/falhas dos monitores ativos; portanto é ponderada por número de ciclos. Latência usa todas as amostras elegíveis. O resumo não promete disponibilidade ponta a ponta da aplicação. |
| RN020 | Monitores pausados não entram no status agregado. Sem monitores fresh elegíveis, saúde agregada é nula. Entre fresh: qualquer offline → offline; senão degradado → degradado; senão online. Havendo ativos sem dados/stale, `data_complete=false`; a UI deve sinalizar o resumo parcial. |
| RN021 | Página pública e monitores públicos são opt-in independentes. Publicar exige projeto ativo e monitor ativo; pausados aparecem como pausados. Respostas públicas nunca incluem URL, e-mail, configuração, erro bruto ou tentativas. |
| RN022 | CheckJob e CheckResult: 30 dias após término. Incidentes encerrados: 90 dias após encerramento; abertos não expiram. `Monitor` preserva snapshot atual mesmo após remoção de checks antigos. |
| RN023 | Arquivamento lógico cancela jobs, encerra incidentes administrativamente e remove recursos das listagens normais/página pública; DELETE repetido é idempotente. Hard delete não integra o MVP. |
| RN024 | Jobs não executados e problemas internos não criam falhas do alvo. Métricas incluem `excluded_count` e jobs vencidos/em aberto; lacunas de scheduler podem nem gerar job, por isso esses contadores não são cobertura temporal completa. |

## Critérios importantes de funcionamento

| Cenário | Resultado esperado |
| --- | --- |
| Threshold 3; três ciclos falham | Degradado, degradado, offline; um incidente iniciado no primeiro ciclo e detectado no terceiro. |
| Threshold 1; primeiro ciclo falha | Offline e incidente no mesmo ciclo. |
| Timeout seguido de sucesso no retry | Um ciclo de sucesso, duas tentativas, uptime positivo e saúde degradada. |
| Monitor offline volta a responder, com alta latência | Incidente encerrado por recuperação; saúde degradada por latência. |
| Falha, job interno não avaliado, falha; threshold 2 | Sequência reiniciada na lacuna; não confirmar offline a partir dessas duas falhas separadas. |
| Worker repete job depois do commit | Nenhum novo CheckResult, contador ou incidente; job já concluído é reconhecido. |
| Lease expira enquanto worker antigo está ativo | Novo token invalida o antigo; somente o dono atual pode finalizar. GET duplicado ainda pode ocorrer. |
| Redis ou PostgreSQL indisponível | Recuperar jobs quando possível, registrar problema interno e sinalizar stale; não marcar todos os alvos offline. |
| Dashboard perde eventos SSE | Refazer snapshot REST ao reconectar e periodicamente; não depender de replay. |
| HTTP aponta para localhost ou redirect interno | Destino bloqueado/redirect não seguido; testar também IPv6, DNS rebinding e IPs especiais. |
| Nenhum resultado na janela | Uptime/média/p95 nulos e contagem zero, com estado sem dados. |
| Dez ciclos avaliados: nove sucessos, uma falha | Uptime 90%, independentemente do threshold de incidente. |

## Autoridade dos contratos

Este documento define semântica e limites; [DATABASE](DATABASE.md) define persistência; [API](API.md) define exposição; [ARCHITECTURE](ARCHITECTURE.md) define execução. Se houver conflito, resolvê-lo explicitamente e atualizar todos os documentos envolvidos antes de implementar.
