# Operação local e critérios de liberação

O PostgreSQL é a fonte de verdade. API, scheduler/publicador e worker são processos separados. A API pode servir cadastros e consultas com o pipeline desabilitado; isso não comprova execução de verificações externas.

## Stack Compose e CA de build

```powershell
# Quando 5432 já pertence ao PostgreSQL nativo, preserve-o.
$env:POSTGRES_PORT = '55433'
docker compose up -d postgres redis
docker compose --profile app build
docker compose --profile app up -d --no-build
```

UI local em `http://127.0.0.1:8080`, com API sob o mesmo origin via Nginx. O PostgreSQL continua na porta interna 5432. Migração precisa terminar com sucesso antes da API; Redis/PostgreSQL possuem healthchecks. Os gates de checks externos permanecem desligados.

Se o download de dependências falhar por uma CA de inspeção HTTPS já confiável no ambiente, forneça seu certificado público PEM aprovado apenas ao build:

```powershell
$env:VIGIL_BUILD_CA_FILE = (Resolve-Path '.cache/build/build-ca.pem').Path
docker compose -f compose.yaml -f compose.build-ca.yaml --profile app build
docker compose --profile app up -d --no-build
```

O override é opcional e restrito ao build. O backend combina a CA temporariamente com as raízes públicas para o uv; npm usa `NODE_EXTRA_CA_CERTS`. Não fornece chaves privadas, não desabilita TLS e não instala a CA no runtime. O certificado e o bundle temporário não integram o repositório/imagem final. Implementação baseada em [BuildKit secrets](https://docs.docker.com/build/building/secrets/), [certificados do uv](https://docs.astral.sh/uv/concepts/authentication/certificates/) e [configuração TLS do Node](https://nodejs.org/learn/http/enterprise-network-configuration).

## Verificação

`-RequireIntegration` verifica primeiro acesso ao daemon Docker. Docker Desktop aberto não basta se o terminal recebe `permission denied` no pipe. A recusa ocorre antes dos ensaios descartáveis; ajustar as permissões da sessão é uma operação do ambiente, sem relaxar TLS, testes ou gates. Commits locais exigem escrita em `.git`; nenhum push é automático.

Após instalar dependências, execute na raiz:

```powershell
./scripts/verify.ps1 -TestDatabaseUrl 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55432/vigil'
```

O comando executa pytest, Ruff, testes/build frontend, validação Compose e whitespace. Preserva relatório JUnit em `.cache/verification/backend.xml` e mostra motivos dos skips. Sem URLs de integração, informa explicitamente as verificações ausentes.

Para exigir PostgreSQL e Redis reais:

```powershell
./scripts/verify.ps1 -RequireIntegration `
  -TestDatabaseUrl $env:VIGIL_TEST_DATABASE_URL `
  -TestRedisUrl $env:VIGIL_TEST_REDIS_URL
```

Esse modo recusa URLs ausentes e testes de integração ignorados. Skips das variantes SQLite que exigem recursos PostgreSQL são esperados. Use um ambiente local isolado: os testes criam schemas PostgreSQL e streams Redis de nomes aleatórios; não devem ser apontados para produção.

Se o antivírus inspecionar também os certificados de loopback, use o backend em container temporário, com a imagem `vigil-api` já construída:

```powershell
./scripts/verify.ps1 -RequireIntegration -BackendContainer -ContainerNetwork vigil_default `
  -TestDatabaseUrl 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55433/vigil' `
  -TestRedisUrl 'redis://127.0.0.1:6379/0' `
  -TestBuildCaFile .cache/build/build-ca.pem
```

`TestBuildCaFile` é opcional, necessário somente quando os downloads exigem a CA pública confiável do ambiente. O helper Python instala dependências dev fixadas em `uv.lock` no container descartável, monta código somente para leitura e grava o mesmo relatório JUnit. `ContainerNetwork vigil_default` usa serviços internos postgres:5432/redis:6379 após confirmar labels Compose, serviço ativo, rede e binding loopback correspondentes às URLs fornecidas. Os testes operacionais nativos continuam nas URLs originais. Sem essa opção, URLs loopback usam o gateway Docker Desktop, que apresentou timeouts transitórios de conexão nesta máquina. Serviços existentes continuam ativos. O transporte mantém seu contexto TLS independente, sem a CA extra. O modo obrigatório exige Redis Streams, Pub/Sub, sockets TLS, crash de worker, snapshots PG17, réplicas/SSE sob pressão TCP e firewall/NDP físicos, recusando skips nessas provas.

Nesta sessão o Avast substituiu o certificado do socket local por uma cadeia emitida por `Avast Web/Mail Shield Untrusted Root`. Os testes positivos passaram em Linux/containers sem alterar validação TLS ou trust do produto. O proxy TCP do teste de Pub/Sub corta apenas suas conexões para provar fallback/reconexão; não há shutdown, FLUSHDB ou interrupção do Redis compartilhado.

Na sessão Windows de 2026-10-04, uma consulta de catálogo do SQLAlchemy ficou em `IPC/MessageQueueInternal` com plano paralelo. O cluster local recebeu `ALTER ROLE vigil IN DATABASE vigil SET max_parallel_workers_per_gather=0`; novas conexões dessa combinação passaram a usar plano serial, e a consulta terminou em 0,105s. A configuração também vale para novos pools API dessa role/banco; outras bases e conexões já abertas não mudaram. É um ajuste do cluster local, não uma migration ou requisito de produção. Para reverter quando o ambiente suportar paralelismo, usar `ALTER ROLE vigil IN DATABASE vigil RESET max_parallel_workers_per_gather`. A causa exata do bloqueio de IPC não foi comprovada; a consulta anterior PID 1968 foi preservada sem sinais e continua pendente de diagnóstico operacional.

Para reproduzir o smoke com API/Vite/PostgreSQL ativos e Edge instalado, executar em `frontend/`: `npm.cmd run test:browser` e `npm.cmd run test:live`. Criam contas/projetos locais de QA. O segundo valida SSE e consultas REST reais, reconciliação após mutação externa à aba, snapshot periódico e revogação. Relatórios/capturas ficam em `.impeccable/review/`, excluídos de Git/Docker.

## Campanha de carga QA e coleta de atualização

O runner `scripts/pipeline_load_check.py` prepara PostgreSQL17.11, Redis7.4.11 e worker/TLS em rede internal UUID própria, sem portas publicadas ou volumes persistentes. Requer imagem `vigil-worker-egress:qa` construída pelo ensaio egress e Docker acessível. Código/testes/CA são montados readonly; instalação do firewall é seguida de UID/GID10001/caps0. Gates compartilhados permanecem false e nenhum endpoint externo é consultado.

```powershell
$env:UV_CACHE_DIR = (Resolve-Path '.cache/uv').Path
uv run --project backend --system-certs --frozen python scripts/pipeline_load_check.py --jobs 100 --duration-seconds 60
```

Relatório privado: `.cache/pipeline-load/<UUID>/report.json`. Exit0 exige contagens completas, commit visível por conexão PostgreSQL distinta antes do XACK, ordem/13 medições completas, backlog final zero e cleanup confirmado. Quantis são interpolados. CPU Docker é percentual por CPU lógico; memória é working set amostrado do container, incluindo setup e servidor TLS. RSS/CPU do helper têm escopo separado. Callback50 não significa50 HTTP simultâneos: limite por host continua5. Transação de agenda pode ser repetida por job do lote; percentis de fases não devem ser somados. Metadata da fixture não comprova migration/head.

Em 2026-10-05, Docker disponível permitiu duas campanhas físicas isoladas, com PG17.11/Redis7.4.11/Taskiq/TLS local e cleanup confirmado:

| Cenário | Jobs/resultados/ACK confirmados | Agenda commit→XACK p50/p95/p99 (ms) | Máximo callbacks/HTTP observado |
| --- | --- | --- | --- |
| 100 jobs em 60s | 100/100/100; zero erros | 89,29 / 99,31 / 122,41 | 1 / 1 |
| Rajada100, `--duration-seconds 0` | 100/100/100; zero erros | 2559,43 / 4198,21 / 4234,19 | 15 / 4 |

Relatórios: `.cache/pipeline-load/31315bf2092c4c75923cfa9c98769b9b/report.json` e `.cache/pipeline-load/2d39277258f64df6b1e2a9f5aacb9a86/report.json`. Todas as13 fases têm100 amostras; ordem, commit por conexão/PID distinto e backlog final zero foram verificados. A rajada manteve limite configurado50 e host5, sem saturar50 callbacks. Um projeto serializa locks; probes por ACK e sampler acrescentam overhead. Esses ensaios locais não estabelecem capacidade sustentada, SLA ou cumprimento global dos RNF007/RNF008, nem medem UI/SSE.

Em QA separado do Backend, token `2c11a939f92546d0aeeae1f50bd7dac1`, foram executados52 casos jobs/helper (`-k not sqlite`) e29 de `test_db_postgresql.py`, todos sem skips/falhas. Os52 incluem sete casos jobsPG reais, um caso enum/UTC offline e44 casos helper mistos, dos quais quatro PG e um Redis reais; não são52 provas físicas. O runner verificou PG170011 antes de cada grupo DDL; fontes readonly, UID10001/caps0, gates false e CA extra somente no build. Jobs provaram RR/RO, recusa de UPDATE25006 e consistência COUNT/página durante commits de writer distinto. Helper executou guardas reais PG e reserva Redis. Migrations exercitaram Alembic real upgrade/downgrade, tipos, constraints, identidade composta e SET NULL nas duas evidências de Incident. A fixture de migrations usa CREATE exclusivo/created flag, sem COMMENT de ownership; compare_metadata cobre as opções existentes do teste, sem paridade global ou plano/desempenho. APIjobs usa metadata em schema separado, sem provar execução da rota no mesmo schema Alembic. Schemas/keys ficaram vazios antes/depois dos grupos, e containers/rede/imagem QA próprios foram removidos conforme `cleanup.json`. JUnits e inspects ficam em `.cache/verification/backend-qa-<token>/`. `verify.ps1 -RequireIntegration` passa a exigir a presença dos testes PG de jobs e recusar seus skips.

Para coleta **separada** no navegador, somente após readiness e janela liberada pelo Maestro:

```powershell
$env:VIGIL_LATENCY_ALLOW_RUN = '1'
$env:VIGIL_UI_URL = 'http://127.0.0.1:8080'
npm.cmd run test:latency --prefix frontend
```

Cria owner/projeto privado vazio exclusivo, sem monitores/checks; prepara 240 REST e 25 PATCH-start→DOM em desktop/mobile. CDP observa EventSource e GET do produto, usando requestId/revisão/nome. PATCH-start→DOM é limite superior ao trecho após commit, não cronômetro de commit; polling pode tornar causalidade ambígua. Quantis nearest-rank não são os quantis interpolados da campanha. Archive/logout/revogação confirmam cleanup no escopo API, conservando owner/projeto arquivado e sessão revogada. Relatório privado `frontend/.impeccable/review/live-latency/<UUID>/report.json`. `test:latency:unit` e `test:latency:observer` verificam tooling; o segundo usa fixture Edge sintética, sem capacidade/latência do produto. A coleta física abaixo foi executada separadamente.

Coleta real em2026-10-05: `29b74cc0-09f0-406a-a5bf-232df865f8c6`, servindo build `e52dd02` em origem loopback própria, PG170011/Alembic0001_initial, Redis e API reais. Passed:240 REST medidos+24 warmups e25 PATCH→DOM+4 warmups, erros0. PATCH-start→DOM p50/p95/p99:245,70/264,30/265,40ms; SSE nativo→início GET produto:205,93/216,70/216,88ms. Todas as25 atualizações foram correlacionadas por revisão, GET posterior com requestId CDP e nome no DOM; nenhuma sobreposição periódica foi observada nesse subconjunto, sem provar causalidade exclusiva. Uma API/projeto vazio, sem monitores/checks: não prova fanout Redis, pipeline, capacidade ou tempo exato commit→DOM.

Archive404/lista vazia e revogação atual/antiga confirmaram cleanup API, sem commit desconhecido. Depois, o ambiente inteiro descartável foi removido por IDs/labels. Preflight conferiu JSON de readiness, head e Redis separadamente; readiness sozinho só consulta o banco. Dois preflights anteriores falharam no binding host de rede internal e foram limpos antes de criar owner. O ambiente aprovado manteve API/PG/Redis na rede internal e acrescentou bridge própria somente ao web para publicar127.0.0.1; não usou Compose compartilhado nem8080. Inspects/logs/cleanup: `.cache/verification/ui-real-e481d12e845740a58c5f8f0833bc2e08/report.json`; relatório de medição em `.impeccable/review/live-latency/<UUID>/report.json` dentro de frontend.

Frontend revisou fontes e relatório readonly, recalculando independentemente contagens e todos os quantis, sem divergência. Limite de replay: JSONv2 persiste flags de correlação e deltas, mas não requestIds/nome/timestamps CDP brutos; o artefato sozinho não permite reconstruir cada pareamento. A aprovação inclui revisão do observador. REST por rota p95: projetos15,4/monitores19,9/métricas22,9/incidentes18,8ms; pooled20,6ms mistura quatro populações. Com25 atualizações, p99 é o máximo observado.

## Auditoria offline de evidências da retenção

De `backend/`, execute `uv run --system-certs --frozen python -m app.db.audit_retention_contract`. Não lê DSN runtime nem conecta ao banco. O JSON compara somente nullable/alvo/SET NULL das duas evidências de Incident e seus índices declarados com o SQL offline Alembic. Recusa ALTER/DROP conservadoramente. Candidato de índice não demonstra uso pelo planner ou ganho; catálogo, SET NULL real e planos dependem do ensaio em [RETENTION_QA_CONTRACT](../backend/app/db/RETENTION_QA_CONTRACT.md). Models/migrations atuais permanecem preservados.

## Smoke de observações com dados sintéticos

Com o Compose PostgreSQL 17 em 55433 e a UI/API em 8080, mantendo ambos os gates false:

```powershell
cd backend
$env:VIGIL_QA_DATABASE_URL = 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55433/vigil'
./.venv/Scripts/python.exe -m app.db.seed_observations_qa seed-synthetic-qa `
  --manifest ../frontend/.impeccable/review/observations-fixture.json
cd ../frontend
$env:VIGIL_UI_URL = 'http://127.0.0.1:8080'
npm.cmd run test:observations
```

Seed cria uma conta/projeto exclusivos com snapshots explicitamente sintéticos; não executa HTTP, não inicia jobs nem habilita gates. Exige PostgreSQL 17 local/public e recusa 55432, produção e manifesto existente. Login e expectativas ficam no manifesto privado ignorado pelo Git/Docker. O teste consulta as rotas reais e verifica desktop/mobile, métricas/buckets, histórico/retries, paginação, incidentes e ausência de dados privados na página pública.

Execute o smoke até 45 minutos após o seed. Para repetir mais tarde, use novo caminho de manifesto e informe-o por `VIGIL_OBSERVATIONS_FIXTURE` no frontend. Falha ao gravar o manifesto após commit pode deixar a conta QA isolada no banco; não há limpeza automática. Relatórios/capturas ficam em `frontend/.impeccable/review/`.

## Retenção

Com as migrations aplicadas e uma URL PostgreSQL explícita:

```powershell
./scripts/run-retention.ps1 -DatabaseUrl $env:VIGIL_DATABASE_URL
```

Por padrão, executa um lote de até 100 registros por entidade e desfaz a transação. A saída JSON informa `committed=false` e contagens elegíveis; esse preview adquire locks breves e não promete que uma execução posterior encontrará as mesmas linhas.

Para aplicar a limpeza já revisada:

```powershell
./scripts/run-retention.ps1 -DatabaseUrl $env:VIGIL_DATABASE_URL -Apply -BatchSize 100 -MaxBatches 10
```

Cada lote tem commit separado, `lock_timeout=1s` e `statement_timeout=10s`. Resultados/jobs terminais são retidos por 30 dias, incidentes fechados por 90 dias e sessões por sete dias após invalidação. Jobs ativos, incidentes abertos e snapshots dos monitores permanecem. Evidências de resultados removidos tornam-se nulas nos incidentes. Se um lote falhar, lotes anteriores já confirmados permanecem; o lote atual é revertido. Execute em processo dedicado, sem vincular à inicialização de cada réplica API.

## Backup e restauração

Para o stack Compose PG17 local em 55433, use o ensaio com verificação de conteúdo:

```powershell
$env:VIGIL_BACKUP_DATABASE_URL = 'postgresql+asyncpg://vigil:vigil_local_only@127.0.0.1:55433/vigil'
./scripts/test-compose-backup-restore.ps1
```

Requer dependências backend e Docker Desktop ativos. O tooling confere PostgreSQL17, labels do container e identidade do cluster antes de usar os utilitários PG17 do próprio container. Mantém uma transação readonly REPEATABLE READ aberta, exporta seu snapshot e passa o mesmo snapshot ao `pg_dump`. Isso permite comparar o backup com a mesma visão da origem mesmo durante commits concorrentes, conforme [snapshots sincronizados](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION) e [`pg_dump --snapshot`](https://www.postgresql.org/docs/17/app-pgdump.html).

Restaura em `vigil_restore_qa_<UUID>` novo, compara todas as linhas das sete tabelas e Alembic via SHA256 ordenado por PK, além de colunas/defaults, índices e constraints. Usa a decompilação legível do PostgreSQL para comparar CHECKs sem diferenças de agrupamento associativo. `--clean --if-exists` atua apenas no banco novo, incluindo o schema public padrão. Origem é somente lida; pipeline/network não são habilitados.

Sucesso exige conteúdo equivalente e ausência do banco temporário confirmada no catálogo após DROP. Timeouts encerram apenas o cliente próprio, deixam `cleanup=pending_review` e não repetem DROP nem usam FORCE; o resultado é falha até revisão operacional. Dumps e relatórios privados ficam em `.cache/backup-restore/<UUID>/`. Stderr nativo não é publicado porque pode conter dados privados; o relatório registra tipo da falha e etapa.

Este ensaio cobre schema public/dados locais, sem owners/ACLs, roles globais, WAL/PITR, recuperação de cluster inteiro ou RPO/RTO de produção. Schemas efêmeros dos testes ficam excluídos. O script recusa outros hosts/portas/bancos e não toca as pendências do PG18.

O script anterior para o cluster nativo permanece disponível:

```powershell
./scripts/test-backup-restore.ps1
```

O script usa o PostgreSQL 18 local na porta 55432 por padrão. Ajuste `PostgresBin`, `HostName`, `Port`, `UserName`, `Database` e `Password` para outro ambiente. Faz backup somente do schema `public`, restaura em um banco novo com nome aleatório, verifica a revisão Alembic e consulta as sete tabelas; remove apenas esse banco temporário. O dump permanece em `.cache/backup-restore/` e contém dados privados. Essa prova não compara cada linha com a origem nem demonstra recuperação operacional completa.

O cliente de cleanup tem limite externo de 15 segundos (`CleanupTimeoutSeconds`). Se exceder esse limite, o script encerra apenas seu cliente `dropdb` e informa o banco pendente; isso não confirma cancelamento do `DROP` no servidor. Inspecione `pg_stat_activity` antes de repetir a remoção. Na sessão Windows de 2026-10-04, o restore foi verificado, mas seu cleanup ficou em `IPC/ProcSignalBarrier`; nenhum walwriter ou processo do servidor foi encerrado. Uma advertência de cleanup precisa ser resolvida operacionalmente mesmo que a validação do dump tenha passado.

## Réplicas e carga SSE

`backend/tests/test_api_replicas.py` sobe três Uvicorn próprios em portas loopback efêmeras, usando um schema PG17 UUID e Redis reais. Exercita login/commits REST alternados, 51 streams HTTP de seis owners, 600 sinais cadenciados com 5.100 entregas, rajada de mil sinais, whitelist/isolamento, 429 por owner/processo, reutilização do slot e revogação compartilhada com cadência real de 30s. Fecha clientes antes de parar somente seus próprios filhos e remover o schema. `verify.ps1 -RequireIntegration` exige o módulo sem skips; métricas locais ficam nas properties do JUnit.

Três assinaturas lentas instrumentadas confirmam fila de 32 e indicação de reconciliação, sem simular pressão física da janela TCP. Sinais de carga não alteram o estado persistido; GET REST continua sendo a autoridade. O limite SSE é local a cada processo: três réplicas podem admitir nove streams da mesma conta. Essas medidas locais não são SLA, capacidade sustentada ou prova de balanceador/múltiplos hosts.

`backend/tests/test_events_tcp.py` acrescenta pressão física: cliente TCP real deixa de ler após headers, com buffers reduzidos somente no helper. Telemetria privada confirma pausa de escrita/bytes acumulados; sinais adicionais garantem envio pendente, cujo prazo de dez segundos libera o slot e fecha o TCP. Outra conta mantém SSE e commit REST, e o slot é reutilizado. O diagnóstico ASGI `TimeoutError` é esperado para esse cliente deliberadamente travado: o teste valida tipo/traceback de `EventResponse`, conserva stderr em `.cache/verification/replica-stderr-<PID>.log` e rejeita outros erros/avisos de pool. O runner monta `/reports` para preservar também os logs Linux; não altera logging ou buffers do produto.

O caso de recuperação em `test_api_replicas.py` derruba apenas uma API filha e confirma que a sobrevivente continua atendendo. Um commit feito com stream perdido é recuperado por `snapshot.required/connected` seguido de GET REST, sem replay. Uma nova API filha, em porta efêmera, reutiliza o schema/sessão e retorna ao fanout Redis. Reconexão é explícita no cliente do teste: não demonstra retry automático de navegador ou roteamento de balanceador.

`scripts/tests/test_api_browser_reconnect.py` acrescenta o produto no Edge com EventSource nativo, Vite/proxy próprios e duas APIs filhas. Crash produz HTTP503 no proxy e estado CLOSED; frontend recria somente fontes terminais com espera crescente de 2s até 30s. Recupera pelo REST o commit feito no intervalo, retoma fanout da substituta e cancela retries no logout. Isso corrige o comportamento observado antes do ajuste: conforme o [HTML Standard](https://html.spec.whatwg.org/multipage/server-sent-events.html#the-eventsource-interface), resposta HTTP diferente de 200 pode falhar o EventSource sem reconexão automática. Fontes CONNECTING preservam o retry do navegador.

O ensaio exige dependências frontend, Node, Playwright e Edge instalados no host, além de PG17/Redis. `verify.ps1 -RequireIntegration` exige este caso sem skip, mesmo com backend em container. Tooling cria portas/schema exclusivos e serve o código atual sem alterar Vite compartilhado ou depender de dist antigo. Cookies, senhas e CSRF não vão aos relatórios; evidências ficam em `frontend/.impeccable/review/reconnect-smoke.json`, ignorado. HTTP503 e perda de transporte induzidos ficam separados de erros inesperados. Limites: proxy QA com troca explícita do destino, sem prova de balanceador produtivo ou failover entre hosts.

Disconnect durante a revalidação podia interromper a devolução da conexão PostgreSQL sob cancelamento repetido do AnyIO. A leitura e fechamento usam shield com o prazo asyncio existente de cinco segundos, sem estender atividade da sessão. Testes determinísticos e o ensaio HTTP real preservam cancelamento e conferem ausência de stderr/avisos de conexões não devolvidas. Baseado na orientação de [finalização protegida do AnyIO](https://anyio.readthedocs.io/en/stable/cancellation.html#shielding).

## Controle de egress do worker

O perfil opt-in `compose.worker.yaml` adiciona um worker Linux separado com firewall de OUTPUT IPv4/IPv6. A API normal não recebe NET_ADMIN. O inicializador instala as regras, então executa Taskiq como UID/GID 10001, sem grupos suplementares, capabilities herdadas/efetivas/bounding/ambient e com no-new-privileges. Falha de resolução, configuração, iptables ou ip6tables impede iniciar o comando.

Permite somente TCP 80/443 para destinos públicos após excluir faixas especiais, DNS para o resolver Docker `127.0.0.11:53` e os IPs RFC1918 exatos resolvidos na inicialização de PostgreSQL:5432/Redis:6379. O DNS usa destino original conntrack, pois Docker traduz a porta antes do filtro OUTPUT. IPv6 permite apenas unicast `2000::/3` após excluir faixas especiais e Neighbor Discovery em eth0 com hop limit 255. Destinos privados em 80/443, metadata/link-local, loopback, CGNAT, documentação, transição IPv6 e outras portas/protocolos são rejeitados. A whitelist de controle não permite HTTP nesses IPs.

O filtro complementa a validação SSRF e o transporte com pinning/TLS; não substitui autenticação ou a verificação do peer. Reservas são conservadoras e incluem algumas exceções públicas de faixas especiais. A política exige Docker Linux com bridge própria e resolver interno, controle IPv4 RFC1918 nas portas padrão e namespace exclusivo: nunca use host networking, `network_mode: container/...`, Docker socket montado ou namespace compartilhado. Mudança do IP de PG/Redis exige reinicializar esse worker para recompor a whitelist; falha nesse intervalo fecha o acesso.

Para construir e executar somente a prova física, com a imagem API já construída:

```powershell
backend/.venv/Scripts/python.exe scripts/egress_check.py --build
docker compose -f compose.yaml -f compose.worker.yaml --profile app --profile workers config --quiet
```

O tooling cria rede internal IPv4/IPv6 e containers UUID exclusivos, sem publicar portas ou usar servidores compartilhados. Atribui endereços de teste ao loopback daquele namespace e confirma listeners ativos antes do filtro; depois comprova seis conexões permitidas, 18 negativas, DNS interno, capabilities zero, socket raw negado e impossibilidade de alterar iptables. Também executa o entrypoint da imagem com comando sintético, sem iniciar Taskiq. Antes da primeira remoção, cleanup valida rede internal/UUID, identidades Docker, labels e interfaces exclusivamente nessa rede de todos os containers conhecidos, além da ausência de endpoints inesperados. Revalida cada container e remove por ID; revalida identidade/rede/endpoints antes de remover a rede por ID. Divergência fica `pending_review` e não produz sucesso. Não existe transação Docker: mudança tardia pode deixar containers próprios já removidos e rede preservada para revisão. Relatório em `.cache/egress-qa/<UUID>/report.json`.

Uma terceira execução usa `CheckExecutor`, `SafeTransport` e o backend físico padrão sob o filtro, com sockets TLS próprios em IPv4/IPv6. Injeta somente respostas DNS e a CA de fixture no contexto explícito do teste: peer pinning, SNI/Host e verificação de certificado permanecem ativos. Dois GETs terminam após headers sem esperar o corpo; CA desconhecida e hostname incorreto falham sem retry/HTTP, enquanto respostas DNS privadas/mistas são recusadas antes do socket. Proxy e CA vindos do ambiente não substituem a configuração desse transporte. Os helpers/certificados de fixture são montados somente para leitura na prova, excluídos da imagem de worker.

O ensaio de NDP usa outra rede internal com prefixo global-unicast QA aleatório `/124` e dois namespaces próprios. Não afirma propriedade/disponibilidade desse prefixo na Internet; endereços são atribuídos somente à bridge descartável e não há forwarding externo. Bloquear NS/NA na OUTPUT do cliente produz timeout TCP e contadores de solicitações descartadas. Restaurar a política resolve o vizinho na eth0 e permite um GET TLS com executor/backend padrão, pinning, SNI/Host e fechamento após headers. Contadores aceitam solicitação ou anúncio, pois uma solicitação recebida também pode preencher o cache enquanto o cliente responde. Cliente e servidor aceitam tráfego somente após queda de capabilities/UID10001. Cleanup aplica a mesma validação prévia a ambos os containers: endpoint inesperado já presente preserva todos os recursos; alteração posterior preserva os recursos divergentes ainda existentes para revisão.

`verify.ps1 -RequireIntegration` constrói e executa essas provas obrigatoriamente. O perfil de worker não foi iniciado; gates seguem false. Limites: kernel Docker Desktop local, controle TCP sintético e tráfego TLS entre fixtures, sem HTTP externo, conectividade pública real, Neighbor Discovery entre hosts ou política instalada no ambiente produtivo. Rede internal ainda pode alcançar o gateway/serviços adequadamente configurados no host; o filtro de destino é necessário além do isolamento Docker.

Referências: [rede internal Docker](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal), [iptables/ip6tables](https://www.netfilter.org/projects/iptables/index.html), [reservas IPv6 IANA](https://www.iana.org/assignments/iana-ipv6-special-registry/) e [Neighbor Discovery RFC4861](https://www.rfc-editor.org/rfc/rfc4861.html).

## Revalidação do upstream web

Nginx usa `upstream vigil_api` com zone64k, `server api:8000 resolve`, DNS Docker127.0.0.11, valid5s e resolver_timeout2s. `/api/` e `/health/` usam esse grupo; SSE conserva HTTP1.1/buffering off/read timeout75s. O [resolve com shared zone](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server) acompanha IPs sem reiniciar Nginx e está disponível no Nginx open source usado (1.28); [valid/resolver](https://nginx.org/en/docs/http/ngx_http_core_module.html#resolver) controla cache de respostas DNS. Não remove a janela de atualização ou garante disponibilidade de uma API única.

`backend/.venv/Scripts/python.exe scripts/proxy_recovery_check.py` cria bridge internal e três containers UUID, sem portas publicadas. Dois listeners sintéticos permanecem vivos: o tooling move só o alias api, conserva IPs distintos, confirma novo DNS e exige que o proxy passe à substituta sem mudar master/workers. Confere `/api/` e `/health/`, além de receber primeiro frame SSE antes do término do corpo. `verify.ps1 -RequireIntegration` exige essa prova; requer imagens locais vigil-api/vigil-web construídas. Relatório em `.cache/proxy-qa/<UUID>/report.json`.

Antes de mutações/cleanup, confere label UUID e redes de cada container; endpoints inesperados preservam recursos para revisão. Desconexão parcial própria permite cleanup, sem aceitar rede estrangeira. Limites: fixture HTTP/SSE sintética em Docker local, sem banco, autenticação, TLS externo, medição de balanceamento ou migração de streams já abertos. Smoke separado do produto verifica sessão/REST/SSE reais no Compose.

## Logs de atividade

A API e os entrypoints scheduler/worker configuram `vigil.activity` para JSON em stderr. O CMD da API usa `--no-access-log` para evitar a linha Uvicorn com URI/query; use também essa opção ao iniciar Uvicorn nativo. `request_headers` mede até o envio inicial; `request_finished` mede a duração do ASGI, portanto pode durar minutos no SSE e não representa latência REST. Um stream que falha depois dos headers conserva status200 e registra outcome=error/cancelled, em vez de fabricar outro status HTTP. Requisições recebem X-Request-ID UUID gerado no servidor; headers recebidos não determinam a correlação. O campo route vem do template declarado, com unmatched para rotas desconhecidas.

Jobs registram job_id/monitor_id, start_delay_ms no claim e duração/attempt_count/outcome somente depois do commit. job_not_claimed pode indicar estado terminal, lease ocupada ou inelegibilidade; não é contador específico de deduplicação. Scheduler registra scheduled_count/published_count por tick; essas contagens não substituem gauges de backlog/PEL/leases ou histogramas agregados.

Formatter usa allowlist de eventos/fields/códigos e ignora msg arbitrária, args, exc_info, body, headers, URL/query e parâmetros SQL. Um sink fechado/indisponível por OSError/ValueError não impede response/commit/ACK. Helpers QA desviam somente a atividade estruturada para arquivos privados, conservando stderr de erro Uvicorn. Logs de frameworks/terceiros continuam independentes; não há exporter ou backend de logs nesta etapa. Base técnica: [logging Python](https://docs.python.org/3/library/logging.html#logrecord-objects) e [middleware ASGI puro Starlette](https://starlette.dev/middleware/#pure-asgi-middleware).

## Diagnóstico privado do pipeline

No diretório `backend/`, execute `.venv/Scripts/python.exe -m app.monitoring.status` com VIGIL_DATABASE_URL/VIGIL_REDIS_URL do alvo. Em Linux, `python -m app.monitoring.status`. O comando lê Settings do ambiente, não importa tasks, não inicializa grupo/stream, não faz ACK/reclaim, não reconcilia jobs e não habilita gates. Não é endpoint HTTP; os flags emitidos refletem a configuração deste processo diagnóstico, sem inspecionar flags de outros processos.

`database` agrega somente pending/running em transação PostgreSQL REPEATABLE READ/READ ONLY, com clock do banco, statement_timeout3s e lock_timeout1s locais. `pending_due` é elegibilidade temporal (slot/retry vencidos e expiry futuro), sem prometer claim válido contra orçamento/configuração/pausa. Counts de publicação distinguem nunca publicado e republicação após30s; leases <=clock estão expiradas. Ages são null quando a população não existe. Não acessa snapshots/URLs/identidades de jobs.

`queue` lê XLEN/XINFO GROUPS/XPENDING em uma transação Redis sem alterar dados. Stream/group ausentes são estados explícitos, não falha de conectividade. `stream_length` inclui mensagens já ACKadas; `undelivered_lag` cobre apenas mensagens não entregues e mantém null quando Redis não consegue calculá-lo, conforme [XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/). `pending_ack` é o total da PEL. Amostra dos100 menores IDs informa max_idle/redelivery/reclaimable120s exclusivamente da amostra, não o máximo global; truncamento é explícito. Evita filtro IDLE, que pode percorrer toda PEL, conforme [XPENDING](https://redis.io/docs/latest/commands/xpending/). Registered consumers não prova processos vivos.

Exit0/status ok significa fontes consultadas, incluindo fila não inicializada; não significa pipeline saudável. Falha de uma dependência preserva as demais, retorna partial/exit1 e código sanitizado sem erro SQL/DSN/senha. Operações têm prazo3s por fonte; fechamento de conexão pode somar tempo. Não há snapshot atômico entre PG e Redis, benchmark de volume, exporter ou histogramas. Não use como liveness/readiness da API. A proteção SQL segue [transações read-only PostgreSQL](https://www.postgresql.org/docs/17/sql-set-transaction.html).

## Heartbeat do scheduler/publicador

`app.monitoring.run` grava observação após concluir o tick do banco e as publicações; falha de tick grava outcome error sem apagar último sucesso. Uma chave hash por par stream/group usa namespace `vigil:heartbeat:scheduler:<SHA256>` da identidade JSON, sem nomes/IDs por processo no relatório. Clock [TIME do Redis](https://redis.io/docs/latest/commands/time/), HSET e [EXPIRE120s](https://redis.io/docs/latest/commands/expire/) executam em [script Lua atômico](https://redis.io/docs/latest/develop/programmability/eval-intro/). Leitura HMGET/TIME/PTTL é atômica e não renova TTL; o diagnóstico continua read-only.

`scheduler` informa last_tick_age_seconds do último sucesso e last_attempt_age_seconds da tentativa mais recente, duração da tentativa, contagens do último sucesso e TTL. Estados: fresh (sucesso até5s), stale (sucesso mais antigo), tick_failed (última tentativa falhou), missing (nunca observado ou TTL expirado) e clock_skew (timestamps no futuro/incoerentes com clock Redis). Dados malformados/sem TTL geram código sanitizado/partial; ausência mantém idade null. Uma tentativa falha renova TTL e conserva idade do último sucesso enquanto continua tentando.

Telemetria tem deadline1s/client sem retry; falha/timeout registra scheduler_heartbeat_failed e permite próximo tick. Cancelamento externo propaga. Pode adicionar até1s ao ciclo em falha de Redis; stale é indicação de cadência observada, não prova de processo morto/SLA. Vários schedulers do mesmo par compartilham último tick concluído: não mede saúde de cada processo, workers nem integridade completa do pipeline. Gate false impede criação do cliente no entrypoint; não ligue pipeline só para preencher heartbeat. API probes não dependem dessa chave. Não substitui métricas históricas/alertas/exporter ou teste de carga.

## Pipeline

`VIGIL_PIPELINE_ENABLED` e `VIGIL_MONITORING_NETWORK_ENABLED` permanecem `false` por padrão. Antes de habilitar execução externa, validar ACK/reclaim no Redis real, TLS/SNI/IPv6 com sockets reais em ambiente controlado, controles de egress e recuperação operacional.

O ensaio `backend/tests/test_worker_process_recovery.py` usa PostgreSQL17 e Redis reais com schemas/streams UUID exclusivos. Interrompe abruptamente apenas subprocessos criados pelo próprio teste nos limites de entrega, claim, transação final e commit antes do ACK. Comprova reclaim, rollback, proteção da lease, retry pelo scheduler, ausência de resultados/incidentes duplicados e esgotamento após três crashes sem classificar falha do alvo. `verify.ps1 -RequireIntegration` exige sua execução sem skips.

O executor é sintético e não abre HTTP; leases de 12s/2s aceleram somente esse ensaio, sem alterar os 90s de produção. Essa prova cobre recuperação de processos de trabalho, sem representar reinício de infraestrutura inteira, durabilidade após perda de host ou liberação de egress.

Com esses critérios atendidos no ambiente isolado, os comandos implementados são:

```powershell
cd backend
uv run --frozen python -m app.monitoring.run
uv run --frozen taskiq worker app.monitoring.tasks:broker --workers 1 --max-async-tasks 50 --max-prefetch 50 --ack-type manual
```

São processos de longa duração em terminais separados. As flags devem ser configuradas explicitamente nesse ambiente. Testes determinísticos do transporte e mocks do broker não substituem as provas reais acima.
