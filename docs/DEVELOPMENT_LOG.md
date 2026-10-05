# Registro de desenvolvimento

## 2026-10-04 — SSE retoma após falha HTTP temporária no navegador

### Implementado
- Corrigida fonte EventSource permanentemente CLOSED após HTTP503: recriação com espera 2/4/8/16/30s, limitada a 30s e reiniciada na abertura. CONNECTING preserva retry nativo.
- Identidade da fonte/cancelamento de probe descartam callbacks e 401 antigos; revogação confirmada/unmount cancelam retry. REST/polling permanecem autoridade.
- Ensaio Edge do produto com Vite/proxy/APIs exclusivos, PG17 UUID e Redis reais: crash, commit durante gap, recuperação por REST, nova réplica/fanout e logout. Verificação obrigatória recusa caso ausente/skip.

### Arquivos principais alterados
- `frontend/src/live.ts`, `frontend/src/test/live.test.tsx`, `frontend/scripts/reconnect-browser-process.mjs`, `frontend/IMPLEMENTATION.md`
- `backend/tests/helpers/api_replica_process.py`, `backend/tests/test_api_replicas.py`, `backend/IMPLEMENTATION.md`
- `scripts/tests/test_api_browser_reconnect.py`, `scripts/verify.ps1`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Navegador falhou antes do ajuste em restore, com readyState=2 e sem fonte substituta. O comportamento terminal HTTP é previsto no HTML Standard; polling sozinho não recuperava o indicador/conexão SSE.
- Proxy troca somente seu upstream e só encerra streams próprios. Senhas/cookies/CSRF ficam na memória; 503/transporte deliberados são correlacionados ao proxy e separados de erros inesperados.
- Origin adicional do helper é estritamente HTTP/127.0.0.1/porta alta, sem path/credenciais/query; configuração/contrato backend de produto não mudou.

### Estado atual
- Edge corrigido passed em 21,22s: revisão 1 via REST, revisão 2 via SSE da substituta, logout sem retry e errors=[]. Relatórios privados `frontend/.impeccable/review/reconnect-{before-fix,smoke}.json`.
- Central final: 389 backend/14 skips apenas SQLite em 257,42s, 77 tooling e 44 frontend; Ruff/TypeScript/build/Compose/whitespace aprovados, zero skips obrigatórios. Firewall/TLS/NDP/cleanup confirmados em `.cache/egress-qa/bf151de5cbf34447aea19b3ae2e1a53f/report.json`.
- Web local reconstruído/atualizado isoladamente; smoke EventSource no Edge8080 passou com connected/project.updated/periodic, REST e revogação, errors=[]. API/PG17/Redis permaneceram ativos. Gates false, PG18 preservado. Limites: Edge/proxy QA local, sem balanceador produtivo/failover de host ou SLA.

### Próximos passos
- Avançar observabilidade mínima de requisições/jobs, com logs estruturados e campos sanitizados; métricas/heartbeats de pipeline continuam pendentes.

## 2026-10-04 — Recuperação de stream após crash e substituição de API

### Implementado
- Ensaio real com duas APIs filhas: crash de uma, continuidade da sobrevivente e commit persistido durante a perda do stream.
- Reconexão explícita recebe snapshot inicial e recupera revisão perdida pelo REST sem replay; nova API retorna ao fanout Redis usando o mesmo schema/sessão.
- Fixture centraliza startup/crash/reposição e cleanup de pipes/readers/filhos; saída inesperada é falha e mantém stderr privado.

### Arquivos principais alterados
- `backend/tests/test_api_replicas.py`, `backend/IMPLEMENTATION.md`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Kill usa somente o objeto de subprocesso criado pelo próprio teste, sem PID de runtime/servidores. API substituta recebe porta efêmera nova, evitando rebinding ou interferência em listeners alheios.
- SSE é efêmero: revisão 1 commitada no gap vem do REST, e revisão 2 posterior chega ao stream reaberto e à nova réplica. Sessão persiste no PostgreSQL, sem novo login.
- ReadError/RemoteProtocolError são aceitos somente para reader cuja API foi deliberadamente encerrada; assertions de owner/DTO e erros de outros readers continuam falhando.

### Estado atual
- Três testes reais de recuperação, carga e TCP passaram juntos: host 58,08s/Linux 58,66s. Recuperação manual medida em 1,702s/1,947s, sem stderr inesperado; quotas locais voltaram a um stream na substituta/dois na sobrevivente.
- Relatórios `.cache/verification/replica-recovery-host.xml` e `.cache/verification/events-tcp-linux.xml`; Ruff aprovado. Aplicação/infra não foram alteradas: central anterior permanece 388 backend/14 skips apenas SQLite e 41 frontend; tooling atual tem 76 passed.
- Gates false; PG18 e serviços compartilhados preservados. Limites: reconexão HTTP explícita para porta conhecida, sem retry automático do navegador, balanceador ou recuperação de host/infra.

### Próximos passos
- Provar EventSource nativo reconectando automaticamente e reconciliando o produto por REST, com UI/proxy/API QA exclusivos e nenhum restart compartilhado.
- Incluir evidência reproduzível de navegador na verificação operacional, preservando cookies/credenciais fora dos relatórios.


## 2026-10-04 — Prefixo IPv6 canônico no verificador NDP

### Implementado
- Geração do prefixo QA usa IPv6Address.compressed, incluindo hextets zero adjacentes ao sufixo, para coincidir com a representação retornada pelo Docker.
- Guard parametrizado cobre zeros à esquerda, hextet final zero e prefixo com os três hextets zero.

### Arquivos principais alterados
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Remover zeros à esquerda de cada hextet isoladamente não comprimia a sequência completa; endereços válidos eram recusados antes do peer. Normalização usa parser IPv6 padrão, sem relaxar ownership/isolation guards.

### Estado atual
- Dois novos casos falharam antes da correção. Após fix: 76 testes operacionais passaram com PG17 e Ruff aprovou.
- Prova física com prefixo `3000::/124`, peer `3000::1` e token de recurso aleatório passou: timeout com NDP bloqueado, TLS padrão após restauração e cleanup confirmado. Relatório `.cache/egress-qa/00000000000042dbba8096840331b83f/report.json`.
- Aplicações não foram alteradas; última central continua 388 backend/14 skips apenas SQLite e 41 frontend. Gates false e serviços compartilhados preservados.

### Próximos passos
- Provar reconexão/snapshot REST após queda e retorno de réplica própria, sem parar servidores compartilhados.


## 2026-10-04 — Ensaio de pressão TCP física de SSE

### Implementado
- Cliente TCP real deixa de ler após headers; API Uvicorn filha e buffers de fixture pequenos permitem observar pausa de escrita e backlog físico.
- Prazo de envio real de dez segundos libera slot/gerador e encerra o transporte; outra conta mantém SSE/commit REST e o slot é reutilizado.
- Helper observa diagnóstico exato de timeout de EventResponse sem suprimir stderr; outros erros/avisos de pool continuam falhando. Runner conserva logs Linux no mount privado `/reports`.
- Módulo TCP integrado às provas obrigatórias, recusando skips em verificação completa.

### Arquivos principais alterados
- `backend/tests/test_events_tcp.py`, `backend/tests/test_api_replicas.py`, `backend/tests/helpers/api_replica_process.py`
- `scripts/verify.ps1`, `scripts/verify_backend_container.py`, `scripts/tests/test_verify_backend_container.py`
- `backend/IMPLEMENTATION.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Nenhum send double, mudança de prazo do produto ou alteração de buffers/gates da API compartilhada; dados ficam em schema/owners UUID de PG17 e processos próprios.
- Escrita que cruza high-water mark pode concluir. Após detectar pausa, 16 sinais adicionais garantem envio pendente; isso corrigiu uma sincronização insuficiente do ensaio exposta na primeira regressão central.
- Uvicorn registra TimeoutError deliberado como erro ASGI e fecha o TCP. Teste valida tipo/traceback e count esperados, preservando o diagnóstico original em vez de mascarar exceções.

### Estado atual
- Host final: passed em 15,73s. Linux: TCP e três réplicas passed em 53,26s, buffer pausado em 65.541 bytes, 688 sinais +16 pendentes, liberação em 9,994s e 71.192 bytes drenados até EOF. Relatórios `.cache/verification/events-tcp-{host,linux}.xml`.
- Primeira central teve 387 passed/14 skips SQLite e falhou somente no ensaio TCP ainda sem envio pendente garantido. Segunda central final passou: 388 backend/14 skips apenas SQLite em 250,59s, 74 tooling e 41 frontend, zero skips obrigatórios; Ruff/TypeScript/build/Compose/whitespace aprovados.
- Prova física firewall/TLS/NDP aprovada e cleanup confirmado: `.cache/egress-qa/1d06aae65a5e4776957a2e8a8abe94b8/report.json`. Diagnóstico de timeout esperado preservado também no mount de relatórios Linux.
- Gates false e PG18 preservado. Limites: loopback local, buffers artificiais de fixture e um cliente travado; não mede SLA/capacidade sustentada de produção.

### Próximos passos
- Provar reconexão/snapshot REST após queda e retorno de réplica própria, preservando API/Redis/PG compartilhados.
- Normalizar integralmente prefixos IPv6 de QA quando hextets do UUID forem zero; expandir o guard de endereço canônico antes do próximo ensaio NDP.


## 2026-10-04 — Neighbor Discovery e TLS entre namespaces exclusivos

### Implementado
- Prova física obrigatória entre servidor e cliente em dois containers QA, com IPv6 na eth0, política real de OUTPUT e executor/transporte padrão.
- Controle negativo bloqueia NS/NA somente no cliente descartável: TCP expira e solicitações descartadas são contadas. Política restaurada resolve o vizinho e permite TLS verificado/headers-only.
- Guards de prefixo canônico, endereço/namespace do peer, evidência incompleta, erro/timeout de servidor e cleanup de ambos os endpoints com labels UUID.

### Arquivos principais alterados
- `infra/worker/qa_ndp_probe.py`, `infra/worker/qa_tls_probe.py`, `infra/worker/.dockerignore`
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Prefixo global-unicast QA aleatório /124 fica somente em bridge internal descartável, sem forwarding externo ou portas publicadas; não representa propriedade/conectividade pública do endereço.
- Prefixos externos à bridge internal impediram o primeiro protótipo de alcançar aliases do peer. O novo desenho usa endereços atribuídos à própria interface, preservando isolamento Docker.
- Kernel pode aprender o vizinho de uma solicitação recebida e responder com anúncio. Medição conta ambos os tipos após restaurar a política, sem exigir ordem de timers; cache precisa estar resolvido na eth0.
- Helpers/CA de fixture são mounts readonly de QA, fora da imagem de worker; nenhum ajuste de SSRF, gates, firewall do host ou servidores compartilhados.

### Estado atual
- Prova completa build/firewall/TLS/NDP passou: timeout com NDP negado, duas solicitações descartadas, um anúncio aceito, vizinho resolvido e GET TLS padrão. Ambos os cleanups confirmados; nenhuma rede QA remanescente. Relatório `.cache/egress-qa/a1af1fd82e0e4361a5f0f9afdd5981ff/report.json`.
- 74 testes operacionais passaram com PG17; Ruff passou. Backend/frontend não foram alterados nesta etapa: regressão central anterior permanece 387 backend/14 skips apenas SQLite, 41 frontend e zero skips obrigatórios.
- Gates false; PG18 preservado. Limites: dois namespaces na mesma bridge Docker Desktop, sem NDP entre hosts, conectividade externa ou implantação produtiva.

### Próximos passos
- Exercitar pressão física do socket SSE com cliente sem leitura, confirmando prazo de envio, liberação de slot/recursos e continuidade para cliente saudável.
- Provar reconexão e reconciliação REST após queda de uma réplica própria; não reiniciar API/Redis/PG compartilhados.


## 2026-10-04 — Transporte TLS padrão sob o firewall do worker

### Implementado
- Prova obrigatória com CheckExecutor/SafeTransport/backend físico padrão, sockets TLS IPv4/IPv6 próprios e filtro de OUTPUT ativo, após queda para UID10001.
- Peer pinning, SNI/Host, encerramento após headers e negativos de CA desconhecida, hostname incorreto e respostas DNS privadas/mistas.
- Verificador recusa evidência TLS incompleta mesmo quando o cleanup foi bem-sucedido; helpers/fixtures não entram na imagem de worker.

### Arquivos principais alterados
- `infra/worker/qa_tls_probe.py`, `infra/worker/.dockerignore`
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Somente respostas DNS e CA de fixture são injetadas. Não há adapter de roteamento físico nem desativação de CERT_REQUIRED/hostname; proxy e CA do ambiente não substituem o transporte.
- Servidor anuncia corpo extenso sem enviar bytes: executor precisa fechar após headers. Negativos TLS não fazem HTTP nem retry; DNS inseguro é bloqueado antes do socket.
- Rede internal e containers UUID exclusivos, sem portas publicadas ou checks externos; cleanup verifica labels e endpoints antes de remover recursos próprios.

### Estado atual
- Regressão central final passou: 387 backend/14 skips apenas SQLite em 215,90s, 65 tooling, 41 frontend; Ruff/TypeScript/build/Compose/whitespace aprovados, zero skips obrigatórios.
- Prova física: seis sockets permitidos/18 bloqueados, entrypoint sem privilégios e seis casos TLS aprovados, dois GETs de headers, cleanup confirmado. Relatório `.cache/egress-qa/640f13b7725540ed85ff49ef665567dc/report.json`.
- Gates false e PG18 preservado. Limites: endereços públicos de fixture têm rotas locais ao namespace; não comprova NDP entre namespaces, disponibilidade pública, HTTP externo ou implantação produtiva.

### Próximos passos
- Provar NDP/TLS entre dois namespaces exclusivos em rede internal com prefixo QA próprio; destinos fora do prefixo são bloqueados pelo isolamento Docker antes de alcançar o peer.
- Exercitar backpressure TCP físico e recuperação de réplica, mantendo controles compartilhados intactos.


## 2026-10-04 — Réplicas SSE reais e conexão devolvida após disconnect

### Implementado
- Três APIs Uvicorn próprias com PostgreSQL17/Redis reais, seis contas, 51 streams HTTP e commits REST alternados entre réplicas.
- Carga cadenciada de 600 sinais/5.100 entregas, rajada de mil sinais com filas lentas de até 32, whitelist/owner, 429 local, slot reutilizado e revogação nas três APIs.
- Correção de vazamento de conexão PostgreSQL na revalidação SSE interrompida por disconnect; shield AnyIO preserva o prazo de cinco segundos e a finalização de recursos.
- Regressões determinísticas de cancelamento na leitura/close, propagação do cancelamento asyncio direto e módulo real exigido pela verificação central.

### Arquivos principais alterados
- `backend/app/services/events.py`, `backend/tests/test_events.py`
- `backend/tests/test_api_replicas.py`, `backend/tests/helpers/api_replica_process.py`
- `scripts/verify.ps1`, `backend/IMPLEMENTATION.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Uvicorn/HTTP/TCP/Redis/PG reais em portas/schemas próprios; telemetria do helper usa stdin, sem endpoint de produto. Gates false, nenhuma chamada de check externo.
- Cancelamento de nível AnyIO podia atingir rollback/check-in repetidamente. Proteção cobre somente a revalidação delimitada; não envolve yield de generator em cancel scope nem altera sessão/cadência.
- Filas lentas instrumentadas demonstram bounded Pub/Sub, sem alegar pressão física de socket. Sinais de carga são hints sintéticos; revisão autoritativa continua no REST.

### Estado atual
- Host passou em 35,72s, sem stderr/erro de pool após fix. Na carga local: p50 10,771ms/p95 15,839ms; 600 sinais/5.100 entregas em 3,126s; revogação nas três em 23,113s. Relatório `.cache/verification/api-replicas-host.xml`.
- Antes do fix, dois ensaios passaram funcionalmente, mas teardown detectou conexões não devolvidas e CancelledError/SAWarning. Falha foi corrigida, sem silenciar logs. Três testes de recurso/cancelamento passaram.
- Regressão central Linux passou: 386 backend/14 skips apenas SQLite em 211,15s, 64 tooling e 41 frontend; Ruff/TypeScript/build/Compose/firewall aprovados, zero skips obrigatórios. Módulo SSE final teve 59 passed no host, incluindo caso de cancelamento asyncio adicionado após coleta central. Linux mediu p50 4,863ms/p95 7,753ms, carga em 2,142s e revogação em 25,454s, sem stderr de réplicas.
- API Compose atualizada somente via build/api up --no-deps, sem recriar PG/Redis/web. Runtime confirmou shield carregado, gates false, CA de build ausente e readiness via Nginx8080. Smoke Edge real `VIGIL_UI_URL=http://127.0.0.1:8080 npm run test:live` passou: EventSource nativo, connected/project.updated/periodic, reconciliação REST e revogação voltando ao login, errors=[]. Relatório privado `frontend/.impeccable/review/live-smoke.json`; criada somente conta/projeto QA próprio no PG17, sem monitores/checks.
- Cota é de três conexões por owner/processo, podendo somar nove em três réplicas. Limites: carga local curta/cadenciada, sem SLA, balanceador, múltiplos hosts ou backpressure TCP físico. PG18 e runtime externo preservados.

### Próximos passos
- Comprovar transporte com pinning/TLS dentro do firewall e Neighbor Discovery entre namespaces, mantendo gates externos false.
- Exercitar backpressure físico de TCP e recuperação de réplica em ambiente exclusivo antes de implantação.


## 2026-10-04 — Firewall de worker com queda de privilégios

### Implementado
- Imagem Linux específica de worker, inicializador de firewall IPv4/IPv6 e perfil Compose opt-in separado da API, com gates false por padrão.
- Prova física em rede internal/containers UUID exclusivos, listeners positivos antes da política, destinos especiais bloqueados e entrypoint real sem privilégios.
- Testes de resolução mista/unsafe, falha antes do exec, regra DNS após DNAT e cleanup que recusa recursos alheios. Verificação central exige a prova física.

### Arquivos principais alterados
- `infra/worker/Dockerfile`, `infra/worker/.dockerignore`, `infra/worker/egress.py`, `infra/worker/qa_probe.py`
- `compose.worker.yaml`, `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`, `scripts/verify.ps1`
- `scripts/verify_backend_container.py`, `scripts/verify-backend-container.ps1`, `scripts/tests/test_verify_backend_container.py`
- `README.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- OUTPUT permite público TCP80/443, DNS Docker original 127.0.0.11:53 e PG5432/Redis6379 somente em IPs RFC1918 resolvidos na inicialização. IPv6 unicast e Neighbor Discovery têm regras próprias; faixas especiais são conservadoras.
- Docker faz DNAT do resolver antes de OUTPUT; matching conntrack do destino/porta originais preserva DNS sem permitir portas arbitrárias de loopback.
- Após instalar ambos os filtros, setpriv remove todas as capabilities e executa UID/GID10001 com no-new-privileges. Inicialização com falha não inicia worker.
- Somente namespaces exclusivos recebem regras/endereços; cleanup confere labels UUID e endpoints. Nenhuma alteração de firewall do host, gates ou processos compartilhados.
- Runner backend pode usar rede Compose interna guardada por labels/serviço/binding da URL nativa. Evita timeouts transitórios do gateway Docker Desktop sem alterar os testes; tooling nativo permanece na origem loopback.

### Estado atual
- Prova física final passou: seis conexões permitidas, 18 bloqueadas com 17 listeners negativos comprovadamente ativos, DNS interno, UID10001/capabilities zero e entrypoint da imagem sem privilégios. Relatório `.cache/egress-qa/c173df7a2c5e4ce280d97049037b83a8/report.json`, cleanup confirmado.
- Verificação central pela rede interna passou: 383 backend passed/14 skips apenas SQLite em 174,99s, 64 tooling e 41 frontend passed; Ruff/TypeScript/build/Compose/whitespace aprovados, zero integrações obrigatórias ignoradas. Stack atual continua gates false e worker opt-in não foi iniciado. PG18 preservado.
- Versão intermediária PowerShell de roteamento foi bloqueada e removida pelo antivírus. Substituída por wrapper simples e implementação Python com 13 testes de guards; proteção permaneceu ativa. Regressores backend por gateway tiveram timeouts de abertura de conexão em testes distintos, sem falha de lógica comprovada.
- Limites: destinos de socket com rotas locais ao namespace, sem HTTP externo, disponibilidade pública, NDP entre hosts ou implantação produtiva; controle DB/Redis TCP sintético. IPs de controle alterados exigem reiniciar worker; política conservadora pode bloquear exceções públicas especiais.

### Próximos passos
- Medir fanout, filas lentas e limites por owner com múltiplos processos API/Redis, mantendo runtime externo desligado.
- Ensaiar transporte runtime dentro da política e NDP entre namespaces antes de qualquer implantação externa.


## 2026-10-04 — Crash de workers nos limites de persistência e ACK

### Implementado
- Ensaio com subprocessos independentes, Receiver Taskiq e tarefa reais, PostgreSQL17 e Redis: crash após entrega, após claim, dentro da transação final e após commit antes do ACK.
- Reclaim de mensagem órfã, proteção da lease, retry pelo scheduler/publicador, replay sem duplicação e três crashes técnicos com esgotamento sem resultado de saúde/incidente.
- Módulo incluído entre as integrações obrigatórias da verificação central.

### Arquivos principais alterados
- `backend/tests/helpers/worker_crash_process.py`, `backend/tests/test_worker_process_recovery.py`
- `scripts/verify.ps1`, `backend/IMPLEMENTATION.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Somente filhos próprios recebem kill; schemas e streams UUID isolam dados. Não há sinais para servidores compartilhados, FLUSHDB, HTTP externo ou mudança de gates.
- Executor sintético e leases de 12s/2s são adapters exclusivos do teste; claim/finalize, transações, broker/ACK e processos são reais. Lease padrão de produção permanece 90s.
- Estado PostgreSQL é a autoridade: mensagem de job ocupado pode ser ACKada, e lease vencida volta pelo scheduler, sem exigir retenção eterna na PEL.

### Estado atual
- Cinco cenários passaram com PG17.11/Redis7.4.11 no host em 66,30s e no Linux, incluindo rollback após flush e commit antes do ACK. Regressão central final: 383 backend passed/14 skips apenas SQLite em 214,06s; 30 tooling e 41 frontend passed; Ruff/TypeScript/build/Compose/whitespace aprovados.
- Primeira regressão teve timeout transitório na abertura de conexão pelo gateway Docker Desktop, antes de executar o teste de concorrência de incidentes. Segunda execução integral passou, sem alteração de código para esconder a falha.
- Gates false e PG18/processos pendentes preservados. Especialistas Maestri continuam sem créditos; nenhuma disputa de arquivos.
- Limites: não cobre HTTP real, reinício de host/servidores ou egress físico. Lease acelerada não mede a latência operacional de 90s.

### Próximos passos
- Implementar prova de egress em rede isolada e medir fanout/backpressure com múltiplas réplicas, mantendo checks externos desligados.


## 2026-10-04 — Backup e restore PG17 com conteúdo equivalente

### Implementado
- Ensaio opt-in de backup PostgreSQL17 Compose, com snapshot readonly compartilhado entre manifesto da origem e pg_dump.
- Restore em banco UUID exclusivo, comparação de todas as linhas por SHA256 ordenado, revisão Alembic, colunas/defaults, índices e constraints; remoção do banco confirmada no catálogo.
- Testes de guards de alvo/cleanup, conteúdo diferente com mesma contagem, snapshot importado após commit concorrente, timeout e falha de cleanup sem falso sucesso.
- Tooling operacional integrado à verificação central com relatório próprio e duas provas PostgreSQL obrigatórias.

### Arquivos principais alterados
- `scripts/backup_restore_check.py`, `scripts/test-compose-backup-restore.ps1`
- `scripts/tests/test_backup_restore_check.py`, `scripts/verify.ps1`
- `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- URL explícita restrita a localhost/55433/vigil, PostgreSQL17, container Compose e system_identifier coincidentes. Origem não recebe gravações.
- Exportador REPEATABLE READ permanece aberto até pg_dump --snapshot terminar. Restore usa transação única; clean atua somente no novo banco.
- CHECKs comparados pela decompilação legível do próprio PG, eliminando diferença de agrupamento associativo introduzida pelo replay do dump.
- Timeout encerra apenas o cliente próprio, preserva banco/dump pendentes para revisão e não repete DROP nem usa FORCE. Falhas não publicam stderr com possíveis dados privados.

### Estado atual
- Ensaio real final no PG17.11 passou com conteúdo/schema equivalentes, dump de 42.302 bytes e cleanup confirmado em 3,149s. Comparadas sete tabelas mais Alembic, incluindo 76 jobs, 76 resultados e 38 incidentes sintéticos existentes.
- Trinta testes de tooling passaram sem skips, incluindo snapshots concorrentes PG17. Regressão central: 378 backend passed/14 skips apenas SQLite, 41 frontend passed; Ruff, TypeScript/build, Compose e whitespace aprovados. Nenhuma integração obrigatória ignorada.
- Dumps/relatórios privados em `.cache/backup-restore/<UUID>/`; JUnit operacional em `.cache/verification/scripts.xml`. PG18/processos pendentes e gates false preservados. Especialistas Maestri permanecem indisponíveis por limite de uso; etapa concluída na área de infraestrutura.
- Limites: somente public/dados, sem owners/ACLs, roles globais, WAL/PITR, recuperação de cluster inteiro ou RPO/RTO de produção. Este ensaio não habilita checks externos.

### Próximos passos
- Ensaiar crash/restart/reentrega de worker próprio em ambiente isolado, usando jobs exclusivos e sem HTTP externo.
- Implementar e comprovar restrição física de egress/firewall no ambiente de monitoramento.
- Medir fanout e limites com múltiplas réplicas antes de liberar gates externos; preservar pendências do PG18 para diagnóstico separado.


## 2026-10-04 — Integrações reais e regressão obrigatória concluídas

### Implementado
- Testes Redis Streams com PEL, reclaim ocioso em múltiplos lotes, ACK idempotente, envelope inválido e commit PostgreSQL antes do ACK; rollback mantém entrega recuperável.
- Pub/Sub com isolamento por owner, whitelist, eco/cleanup, processos independentes e recuperação após queda real de um proxy TCP exclusivo do teste.
- Sockets TLS/SNI/Host IPv4/IPv6, certificados rejeitados, headers-only e bloqueio SSRF antes do socket. Verificação obrigatória exige os três módulos sem skips de integração.
- Runner backend em container temporário com código readonly e dependências dev fixadas; frontend permanece verificado no host.

### Arquivos principais alterados
- `backend/tests/test_broker_integration.py`, `backend/tests/test_events_redis.py`, `backend/tests/helpers/redis_event_process.py`
- `backend/tests/test_transport_sockets.py`, `backend/tests/fixtures/tls/`, `backend/IMPLEMENTATION.md`
- `scripts/verify.ps1`, `scripts/verify-backend-container.ps1`, `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Testes usam schemas/streams UUID isolados e conexões próprias; nenhum FLUSHDB, shutdown Redis ou mudança na proteção SSRF/TLS do runtime.
- Avast substitui certificados até em loopback Windows; TLS positivo foi comprovado em container Linux mantendo CERT_REQUIRED/check_hostname. CA extra opcional serve apenas downloads no container descartável.
- Teste original de queda dependia de disconnect com endpoint ainda acessível. Proxy corrigido prova recusa real e fecha clientes antes de aguardar encerramento do servidor.

### Estado atual
- Verificação central obrigatória passou: **378 backend passed, 14 skips somente SQLite**, em 158,29s; zero skips obrigatórios PostgreSQL/Redis/PubSub/TLS. Ruff passou.
- **41 frontend passed**, TypeScript/build/Compose/whitespace aprovados. Smoke de observações já aprovado em Edge desktop/mobile e registrado no commit local `659a1b8`.
- Compose PostgreSQL17.11/55433, Redis7.4.11 e UI/API8080 ativos. Gates false; PG18 e suas pendências preservados. Test fixtures TLS são públicos e não têm autorização produtiva.
- Relatório JUnit em `.cache/verification/backend.xml`; credenciais de QA e capturas ignoradas. Nenhum push executado.

### Próximos passos
- Validar controles de egress/firewall em ambiente isolado antes de habilitar rede de monitoramento; comprovar bloqueios físicos além da validação runtime.
- Ensaiar recuperação operacional com reinício/crash controlado de processos próprios e backup/restauração no PG17, preservando pendências PG18.
- Definir e medir carga/limites de conexões e fanout com múltiplas réplicas; manter gates false até esses critérios serem atendidos.


## 2026-10-04 — Observações preenchidas validadas no Compose

### Implementado
- Seed opt-in PostgreSQL 17 com conta exclusiva, seis monitores, 76 ciclos e 38 incidentes sintéticos, manifesto privado e confronto de expectativas com SQL persistido.
- Smoke Playwright/Edge por rotas REST reais, cobrindo métricas/buckets, histórico/retries, paginação e incidentes privados/públicos em desktop/mobile.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`, `backend/tests/test_db_qa_seed.py`, `backend/app/db/IMPLEMENTATION.md`
- `frontend/scripts/observations-smoke.mjs`, `frontend/package.json`, `frontend/IMPLEMENTATION.md`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Seed restrito a PostgreSQL 17 local/55433/public, sem pipeline/network. Cada owner é novo, sem sobrescrever manifestos; nenhum HTTP executado.
- Dados administrativos são exemplos sintéticos de DTO. Manifesto/credenciais/capturas permanecem ignorados pelo Git/Docker; smoke exige fixture com menos de 45 minutos.

### Estado atual
- Dez testes QA passaram no PG17.11 e Ruff passou. Smoke final aprovado no Compose8080 em Edge1440/390, 14 verificações sem overflow e `errors=[]`; buckets UTC e apresentação America/Sao_Paulo conferidos.
- Se o manifesto não puder ser escrito após commit, pode restar owner QA isolado; sem cleanup automático. PG18/processos pendentes preservados.
- Integração Redis/TLS está em regressão central; nenhuma alteração de produto foi necessária no frontend neste marco.

### Próximos passos
- Concluir verificação obrigatória Redis/PubSub/TLS/PostgreSQL e registrar seu commit separado.
- Avançar controles de egress, recuperação operacional e carga antes de habilitar checks externos.


## 2026-10-04 — Build Docker e stack local comprovados

### Implementado
- Build opcional com CA pública confiável via BuildKit secret para uv/npm, sem desabilitar TLS nem persistir a CA no runtime.
- Removido segundo sync redundante do backend: projeto não empacotável já instala as dependências fixadas na camada inicial.
- Construídas imagens API/UI/migrate e iniciado stack Compose com Nginx, PostgreSQL 17.11 e Redis 7.4.11.

### Arquivos principais alterados
- `backend/Dockerfile`, `frontend/Dockerfile`, `compose.build-ca.yaml`
- `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- CA extra é fornecida explicitamente por arquivo PEM confiável somente no build; bundle temporário removido na mesma camada, sem alterar trust do transporte de monitoramento.
- PostgreSQL Compose publicado em 55433 nesta sessão para preservar o PostgreSQL nativo da porta 5432 e o cluster PG18 da porta 55432.
- Pipeline/network continuam false. Stack local serve cadastros/consultas; workers externos não foram iniciados.

### Estado atual
- Base funcional commitada localmente em `ac658b7` após 352 testes backend e confirmação direta de 41 frontend/build. Sem push.
- Build inicialmente falhou com UnknownIssuer; repetição com CA pública já validada pelo Windows passou nas três imagens. CA exportada em `.cache/build/`, fora do Git.
- Migration container terminou exit0; PostgreSQL/Redis/API saudáveis e `/health/ready` via Nginx8080 retorna ok. Ausência de `/run/secrets/build_ca`, `/tmp/vigil-build-ca.pem` e `SSL_CERT_FILE` confirmada no runtime; gates false confirmados.
- Broker existente executado pelo Maestro com Redis real: 3 passed em 0,53s, incluindo ACK/reclaim ocioso.
- Especialistas validam PG17/pipeline/retention, novos testes Redis/PubSub/sockets TLS e smoke de observações com fixture sintética persistida exclusiva PG17. Essas provas ainda estão em andamento neste marco.

### Próximos passos
- Integrar entregas dos especialistas, confirmar smoke de observações preenchidas e executar verificação obrigatória PostgreSQL/Redis reais.
- Registrar resultados e commitar separadamente cada unidade verificada.
- Preservar gates externos até controles egress/recuperação/carga restantes serem comprovados.

## 2026-10-04 — Verificação central do frontend e base para commits

### Implementado
- Concluída verificação direta do frontend pelo Maestro em execução autorizada para subprocessos locais: 41 testes Vitest e build TypeScript/Vite passaram.
- Revisada a lista completa de arquivos da base funcional; caches, dumps, credenciais de QA e evidências de navegador permanecem excluídos de Git.

### Arquivos principais alterados
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Consolidar primeiro a base funcional já validada em um commit local coerente antes de novas entregas de transporte/operação.
- Usar a distribuição WSL/Docker já instalada para investigar Redis real; nenhuma flag de execução externa foi habilitada.

### Estado atual
- Backend da base: 352 testes aprovados, 13 skips documentados; frontend confirmado diretamente com 41 testes, sem skips, e build aprovado.
- Remoto `origin` configurado; staging dos 110 arquivos revisados foi autorizado e concluído. Base pronta para commit local; sem push automático.
- WSL Ubuntu disponível; Docker Desktop solicitado em segundo plano, Redis ainda não validado.

### Próximos passos
- Consolidar commit local da base e iniciar testes de transporte com sockets reais em ambiente controlado.
- Disponibilizar Redis isolado, validar ACK/reclaim/PubSub reais e repetir modo obrigatório de verificação.
- Manter gates desligados até concluir egress e os critérios operacionais restantes.

## 2026-10-04 — SSE e observações integrados ao navegador

### Implementado
- SSE privado com autenticação concluída antes de reservar conexão, revalidação de sessão, isolamento por proprietário, filas limitadas e cleanup em desconexão/cancelamento/envio lento.
- Frontend integrado a métricas, histórico, incidentes e página pública; SSE invalida consultas REST, com snapshots serializados, reconciliação pendente e polling de 30s.
- Corridas de troca/edição de projeto, leitura lenta e 401 atrasado corrigidas; paginação se ajusta quando retenção reduz os resultados.
- Smokes reproduzíveis de CRUD/status pública e SSE real, incluindo mutação fora da aba, snapshot periódico e revogação de sessão.

### Arquivos principais alterados
- `backend/app/api/events.py`, `backend/app/services/events.py`, `backend/tests/test_events.py`, `backend/IMPLEMENTATION.md`
- `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/Observations.tsx`, `frontend/src/live.ts`
- `frontend/src/test/App.test.tsx`, `frontend/src/test/Observations.test.tsx`, `frontend/src/test/api.test.ts`, `frontend/src/test/live.test.tsx`
- `frontend/scripts/browser-smoke.mjs`, `frontend/scripts/live-smoke.mjs`, `frontend/package.json`, `frontend/IMPLEMENTATION.md`
- `docs/API.md`, `docs/OPERATIONS.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- SSE transporta invalidações efêmeras, sem replay; os dados exibidos vêm das consultas REST. Redis indisponível não impede sinais locais, snapshots e polling.
- Três streams por conta por processo, fila de 32 sinais, envio limitado a 10s, heartbeat 15s e revalidação/snapshot 30s. Produtores atuais invalidam projeto/monitor; incidentes são reconciliados pelo REST.
- Mantidos gates pipeline/network desligados. Smokes criam somente cadastros de QA e não executam URLs monitoradas.
- Cluster local recebeu `ALTER ROLE vigil IN DATABASE vigil SET max_parallel_workers_per_gather=0` após introspecção ficar em IPC com plano paralelo. Nova conexão executou plano serial em 0,105s; também afeta novos pools API dessa role/banco. Sem migration, restart ou sinal ao servidor. Reversão: `ALTER ROLE vigil IN DATABASE vigil RESET max_parallel_workers_per_gather` quando o ambiente suportar paralelismo.

### Estado atual
- Backend: 117 passed/8 skipped na regressão events/auth/resources/worker com PostgreSQL real e SQLite; 56 casos SSE. Ruff passou.
- Frontend reportou 41 testes aprovados, typecheck/build e smokes reais desktop/mobile de CRUD/status pública/SSE. Relatórios em `frontend/.impeccable/review/`, fora de Git/Docker.
- Maestro confirmou 42 passed/1 skipped em observações/health e, depois, backend completo **352 passed/13 skipped em 359,23s**, com PostgreSQL real. Doze skips são variantes SQLite e um é Redis ausente. Ruff de `app/tests` passou; relatório `.cache/verification/backend.xml` contém 365 casos. A primeira rodada foi interrompida ao travar em introspecção PostgreSQL; a repetição com novas conexões passou após ajuste local do paralelismo.
- Verificação central parou no frontend por `spawn EPERM` ao iniciar esbuild, antes de executar os testes JS nessa rodada; não é falha de assertion. Evidência frontend válida é a suíte/build/smokes de 41 testes reportados pelo especialista. Maestro confirmou também typecheck diretamente; Compose e whitespace passaram separadamente.
- Gate `RequireIntegration` executado sobre o relatório real rejeitou exatamente o skip Redis, aceitando a cobertura PostgreSQL e os skips SQLite esperados. Ausência de URLs obrigatórias também foi rejeitada antes de rodar a suíte.
- API 8000, Vite 5173 e PostgreSQL 55432 ativos. Redis real/PubSub entre réplicas, execução externa do pipeline e deploy continuam sem validação.
- Backends locais anteriores PID 1968 (introspecção IPC) e PID 34620 (DROP do banco temporário de restore) preservados e pendentes de diagnóstico operacional; novos testes usam conexões próprias.
- Git: `origin` configurado, mas staging recusado por permissão de `.git/index.lock`; nenhum commit ou push realizado nesta sessão.

### Próximos passos
- Criar commits locais das entregas verificadas quando o índice Git permitir escrita. Reexecutar `scripts/verify.ps1` integralmente quando o ambiente permitir subprocessos esbuild; preservar o relatório backend e evidências frontend existentes.
- Disponibilizar Redis real e executar modo obrigatório de `scripts/verify.ps1`; validar ACK/reclaim e fan-out Pub/Sub entre processos.
- Resolver backends/banco temporário pendentes em ambiente operacional adequado; não repetir DROP nem encerrar walwriter para contornar a restrição.
- Validar sockets TLS/SNI/IPv6, egress, recuperação/carga e PostgreSQL 17 do Compose antes de habilitar pipeline ou publicar deploy.

## 2026-10-04 — Verificação de integrações e operação local

### Implementado
- Verificação com URLs PostgreSQL/Redis explícitas, relatório JUnit, motivos dos skips e modo `RequireIntegration` que recusa ausência/skip das integrações reais.
- Wrapper PowerShell de retenção com banco obrigatório, limites de lotes e rollback por padrão; aplicação exige `-Apply`.
- Deadline externo de cleanup do teste de backup/restore: encerra apenas o cliente criado pelo script e informa pendência, sem sinalizar backends PostgreSQL.
- Runbook de operação e exclusão de temporários pytest, cache npm e evidências privadas de QA dos contextos Git/Docker apropriados.

### Arquivos principais alterados
- `scripts/verify.ps1`, `scripts/run-retention.ps1`, `scripts/test-backup-restore.ps1`
- `.gitignore`, `README.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`
- `frontend/.dockerignore`, `backend/.dockerignore`
- `backend/app/db/IMPLEMENTATION.md` (validação de retenção pelo especialista).

### Decisões técnicas
- Não considerar configuração de URL como prova de integração: o modo obrigatório também confere os testes executados no relatório.
- Preview de retenção executa somente um lote real e reverte; não estima backlog completo nem altera gates do pipeline.
- Não repetir DROP nem encerrar walwriter para resolver um cleanup preso no ambiente restrito.

### Estado atual
- PostgreSQL 18.6 retomado no cluster existente, porta 55432, migration `0001_initial`; retenção passou em 29 testes reais sem skips.
- Maestro confirmou wrapper de retenção com `committed=false`, sintaxe dos três scripts, rejeição de URLs obrigatórias ausentes, gate de skips sobre relatório JUnit real e configuração Compose.
- Cleanup validado com executável controlado: sucesso, exit 7 e cliente travado encerrado em aproximadamente 1,05s com timeout de 1s; nenhum banco envolvido nesse teste.
- Backup/restore verificou migration e sete tabelas no banco novo; cleanup real ficou em `IPC/ProcSignalBarrier`. Banco `vigil_restore_test_2b30885f075f4396bd10830998d66b7b` e backend DROP PID 34620 permanecem pendentes; walwriter PID 27364 preservado. O cliente original foi interrompido, sem confirmação de cancelamento da query no servidor.
- Docker/Redis reais indisponíveis. SSE/frontend ainda em conclusão pelos agentes neste marco.
- Remoto `origin` configurado pelo usuário; staging tentado e recusado com `.git/index.lock: Permission denied`. Nenhum commit ou push realizado.

### Próximos passos
- Concluir entregas SSE/frontend e rodar verificação central com PostgreSQL real.
- Executar `scripts/verify.ps1 -RequireIntegration` quando Redis real estiver disponível; validar ACK/reclaim e Pub/Sub entre processos antes de liberar pipeline.
- Inspecionar cleanup pendente do banco de restore em ambiente que permita operação PostgreSQL normal; não repetir DROP sem diagnóstico.
- Criar commits locais das unidades verificadas quando escrita no índice Git estiver disponível; não fazer push automático.

## 2026-10-04 — Pipeline transacional e consultas de observação

### Implementado
- Agendamento por slot recente, intenção persistida e avanço atômico da agenda, SKIP LOCKED, lease/versionamento e finalização idempotente de resultado/saúde/incidente/revisão.
- Reconciliação e até três execuções técnicas com retry de 1s/2s; exclusões internas não fabricam indisponibilidade do alvo.
- Consultas privadas de checks, métricas por monitor/projeto, série UTC e incidentes com janelas/paginação/isolamento.
- Status pública com opt-in duplo e DTOs explícitos sem dados privados.
- Frontend base validado em navegador real (cadastro/login, CRUD, pausa/retomada, sessão após reload, archive/logout), com correção de corrida ao salvar e trocar de projeto.

### Arquivos principais alterados
- `backend/app/services/check_jobs.py`, `backend/app/monitoring/scheduler.py`, `backend/tests/test_pipeline_db.py`
- `backend/app/api/observations.py`, `backend/app/services/observations.py`, `backend/tests/test_observations.py`
- `backend/app/main.py`, `frontend/src/App.tsx`, `frontend/src/Forms.tsx`
- `frontend/IMPLEMENTATION.md`, `backend/app/db/IMPLEMENTATION.md`, `docs/API.md`

### Decisões técnicas
- Caller controla transação/commit dos jobs; HTTP e publicação não podem ocorrer segurando locks.
- p95/contagens/média calculados no PostgreSQL sobre amostras brutas; adapter SQLite de teste usa percentil interpolado equivalente.
- Métricas/checks têm retenção consultável de 30 dias; incidentes até 90 dias, com filtro por sobreposição para não esconder incidente aberto antigo.
- RedisStreamBroker terá reclaim em ticks mesmo sem mensagens novas; experimento real continua pendente por ausência de Redis acessível.

### Estado atual
- Banco/pipeline: 61 testes reais passaram (37 de base/migrations e 24 de pipeline), com reentrega, rollback, concorrência e lease antigo.
- Observações: 24 testes passaram nos adapters SQLite/PostgreSQL, usando router integrado ao app.main; Ruff passou. API local reiniciada com as novas rotas.
- Frontend base: 18 testes Vitest e build passaram; smoke desktop/mobile sem overflow ou erros inesperados. Capturas em `frontend/.impeccable/review/`.
- Backend reportou 41 testes de transporte determinístico e 10 de worker/publicação/ACK passando; experimento Redis real ainda não executado. Gates pipeline/network permanecem false.
- Retenção e SSE estão em implementação; frontend integra métricas/histórico/status pública. Commit continua impedido pela sandbox Git de Maestro.

### Próximos passos
- Concluir revisão de consultas e testes de retenção por lotes no PostgreSQL.
- Integrar SSE com verificação de sessão, sinais por proprietário e reconciliação/polling no frontend.
- Disponibilizar Redis real para `test_broker.py`, validar reclaim/ACK/falhas do broker e somente então avaliar habilitar runtime do pipeline.
- Verificar TLS/SNI/IPv6/egress e backup/restore antes de deploy público; não há deploy realizado.

## 2026-10-04 — API e persistência integradas ao frontend real

### Implementado
- Cadastro, login/logout, sessões opacas revogáveis, Argon2id, CSRF e validação de Origin.
- CRUD, arquivamento lógico e isolamento por proprietário de projetos/monitores; cotas com locks PostgreSQL, pausa/retomada e invalidação de jobs por versão.
- Sete entidades SQLAlchemy e migration Alembic inicial congelada, com FK composta para identidade do resultado, índices parciais e retenção de evidências por SET NULL.
- React/TypeScript/Vite com autenticação, gestão de projetos/monitores e dashboard que distingue saúde de freshness.
- Scripts de execução/verificação local e infraestrutura Compose com migration antes da API e Nginx no mesmo origin.

### Arquivos principais alterados
- `backend/app/main.py`, `backend/app/config.py`, `backend/app/security.py`
- `backend/app/api/auth.py`, `backend/app/api/dependencies.py`, `backend/app/api/resources.py`, `backend/app/api/schemas.py`, `backend/app/api/errors.py`
- `backend/app/services/resources.py`, `backend/app/domain/monitors.py`
- `backend/app/db/base.py`, `backend/app/db/models.py`, `backend/app/db/session.py`
- `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_initial.py`
- `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json`
- `frontend/src/App.tsx`, `frontend/src/Forms.tsx`, `frontend/src/api.ts`, `frontend/src/domain.ts`, `frontend/src/styles.css`
- `scripts/start-local.ps1`, `scripts/verify.ps1`, `compose.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`

### Decisões técnicas
- API `/api/v1` com cookie same-origin e CSRF em memória no frontend; sem JWT/localStorage.
- Transação da API usa dependency scope=function para terminar antes de enviar resposta. Updated_at de ORM é atualizado explicitamente antes de serializar para evitar MissingGreenlet.
- API local roda sem reload porque multiprocessing/named pipes são restritos nesta sessão Windows.
- Dependências instaladas com certificados do sistema, mantendo TLS verificado.

### Estado atual
- Suite backend completa reportada pelo especialista: 156 passed, 2 skips de concorrência somente SQLite; dois casos adicionais de multicast passaram depois. Maestro confirmou independentemente 107 testes API/validação e 49 testes persistência/health.
- Build/TypeScript frontend e 16 testes Vitest passaram, executados pelo especialista em seu fluxo autorizado de subprocessos.
- API em `127.0.0.1:8000`, frontend em `127.0.0.1:5173`, PostgreSQL real 18.6 isolado em `127.0.0.1:55432`. Migration aplicada ao runtime; readiness OK. Smoke de navegador em andamento.
- Docker Compose valida configuração, mas daemon/imagens não foram executados. Runtime Compose PG17 ainda não foi testado; integração real desta sessão usa PG18.6.
- Pipeline/HTTP seguro, métricas REST, SSE e status pública ainda não estão concluídos; cadastros não executam chamadas externas nesta etapa.
- Git local inicializado com autorização; staging/commit seguem impedidos pela sandbox de Maestro ao escrever `.git/index.lock`. Nenhum push.

### Próximos passos
- Banco de Dados: concluir e validar `backend/app/services/check_jobs.py`, `backend/app/monitoring/scheduler.py` e `backend/tests/test_pipeline_db.py` no PostgreSQL real.
- Backend: transporte HTTP resistente a SSRF, broker/worker/publicador com ACK após commit; depois histórico, métricas, incidentes e DTO público separado.
- Frontend: concluir smoke desktop/mobile; integrar próximos contratos REST apenas após dados reais disponíveis.

## 2026-10-04 — Regras de saúde e métricas verificadas

### Implementado
- Regras puras de transição online/degraded/offline, com threshold, retries recuperados, limiar de latência e sinalização de abertura/encerramento de incidente.
- Lacunas e pausa interrompem sequência de falhas sem recuperar monitor offline.
- Freshness independente da saúde; resumo de projeto exclui leituras antigas e monitores pausados.
- Uptime por ciclos e média/p95 interpolado apenas de latências de sucesso, em janela semiaberta limitada a 30 dias.

### Arquivos principais alterados
- `backend/app/domain/health.py`
- `backend/tests/test_health.py`
- `scripts/verify.ps1`

### Decisões técnicas
- As regras não conhecem ORM, HTTP ou filas; o pipeline deve validar identidade, versão, prazo e lease antes de aplicá-las.
- Resultados não avaliados não entram nas métricas e não fabricam falhas do alvo.

### Estado atual
- 13 testes pytest passaram; Ruff passou para os dois arquivos de regras/testes.
- PostgreSQL 18.6 real está ativo em cluster isolado local, porta 55432; migrations e testes de persistência seguem com o especialista.
- UI/API estão em validação; pipeline ainda em implementação. Commit continua impedido pela restrição de escrita no índice Git desta sessão.

### Próximos passos
- Integrar regras à finalização transacional de jobs em `backend/app/services/check_jobs.py`.
- Validar reentrega, lease antigo e concorrência no PostgreSQL; integrar transporte HTTP seguro e workers.
- Verificar cadastro/projetos/monitores no Portal `Vigil Preview` em desktop e mobile.

## 2026-10-04 — Início coordenado do projeto

### Implementado
- Analisados os quatro documentos de planejamento e o README.
- Definidos contratos iniciais de API, roadmap e divisão de propriedade entre os três agentes Maestri.
- Inicializado Git local na branch `main`, após autorização explícita do usuário.
- Criada configuração Compose inicial de PostgreSQL e Redis com portas locais e persistência.

### Arquivos principais alterados
- `.gitignore`, `.env.example`, `compose.yaml`
- `docs/API.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Commits e integração centralizados no Maestro, com agentes implementando em diretórios próprios.
- Entrega inicial cobre persistência, autenticação, projetos, monitores e dashboard sem medições fictícias.
- PostgreSQL segue como fonte de verdade; testes SQLite não substituem integração real.

### Estado atual
- Backend, frontend e migrations estão em implementação pelos agentes; ainda não são entregas validadas.
- Docker CLI está instalado, mas o daemon não estava ativo na inspeção inicial; tentativa de inicialização em andamento.
- PostgreSQL instalado foi identificado pelo especialista de banco; validação real em cluster isolado está em andamento.
- Git foi inicializado com autorização, mas a sandbox desta sessão nega escrita em `.git/index.lock`; staging e commits estão tecnicamente impedidos, sem push realizado.

### Próximos passos
- Validar e integrar entregas dos três agentes; rodar suites, build e migration PostgreSQL.
- Completar execução local e atualizar o README com comandos comprovados.
- Implementar transporte HTTP seguro e pipeline durável após a base estar validada.
