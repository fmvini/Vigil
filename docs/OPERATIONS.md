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

O tooling cria rede internal IPv4/IPv6 e containers UUID exclusivos, sem publicar portas ou usar servidores compartilhados. Atribui endereços de teste ao loopback daquele namespace e confirma listeners ativos antes do filtro; depois comprova seis conexões permitidas, 18 negativas, DNS interno, capabilities zero, socket raw negado e impossibilidade de alterar iptables. Também executa o entrypoint da imagem com comando sintético, sem iniciar Taskiq. Cleanup exige labels UUID e rede sem endpoints inesperados; falha fica `pending_review` e não produz sucesso. Relatório em `.cache/egress-qa/<UUID>/report.json`.

Uma terceira execução usa `CheckExecutor`, `SafeTransport` e o backend físico padrão sob o filtro, com sockets TLS próprios em IPv4/IPv6. Injeta somente respostas DNS e a CA de fixture no contexto explícito do teste: peer pinning, SNI/Host e verificação de certificado permanecem ativos. Dois GETs terminam após headers sem esperar o corpo; CA desconhecida e hostname incorreto falham sem retry/HTTP, enquanto respostas DNS privadas/mistas são recusadas antes do socket. Proxy e CA vindos do ambiente não substituem a configuração desse transporte. Os helpers/certificados de fixture são montados somente para leitura na prova, excluídos da imagem de worker.

O ensaio de NDP usa outra rede internal com prefixo global-unicast QA aleatório `/124` e dois namespaces próprios. Não afirma propriedade/disponibilidade desse prefixo na Internet; endereços são atribuídos somente à bridge descartável e não há forwarding externo. Bloquear NS/NA na OUTPUT do cliente produz timeout TCP e contadores de solicitações descartadas. Restaurar a política resolve o vizinho na eth0 e permite um GET TLS com executor/backend padrão, pinning, SNI/Host e fechamento após headers. Contadores aceitam solicitação ou anúncio, pois uma solicitação recebida também pode preencher o cache enquanto o cliente responde. Cliente e servidor aceitam tráfego somente após queda de capabilities/UID10001. Cleanup verifica ambos os nomes/labels antes de remover endpoints próprios; um endpoint inesperado preserva a rede para revisão.

`verify.ps1 -RequireIntegration` constrói e executa essas provas obrigatoriamente. O perfil de worker não foi iniciado; gates seguem false. Limites: kernel Docker Desktop local, controle TCP sintético e tráfego TLS entre fixtures, sem HTTP externo, conectividade pública real, Neighbor Discovery entre hosts ou política instalada no ambiente produtivo. Rede internal ainda pode alcançar o gateway/serviços adequadamente configurados no host; o filtro de destino é necessário além do isolamento Docker.

Referências: [rede internal Docker](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal), [iptables/ip6tables](https://www.netfilter.org/projects/iptables/index.html), [reservas IPv6 IANA](https://www.iana.org/assignments/iana-ipv6-special-registry/) e [Neighbor Discovery RFC4861](https://www.rfc-editor.org/rfc/rfc4861.html).

## Logs de atividade

A API e os entrypoints scheduler/worker configuram `vigil.activity` para JSON em stderr. O CMD da API usa `--no-access-log` para evitar a linha Uvicorn com URI/query; use também essa opção ao iniciar Uvicorn nativo. `request_headers` mede até o envio inicial; `request_finished` mede a duração do ASGI, portanto pode durar minutos no SSE e não representa latência REST. Um stream que falha depois dos headers conserva status200 e registra outcome=error/cancelled, em vez de fabricar outro status HTTP. Requisições recebem X-Request-ID UUID gerado no servidor; headers recebidos não determinam a correlação. O campo route vem do template declarado, com unmatched para rotas desconhecidas.

Jobs registram job_id/monitor_id, start_delay_ms no claim e duração/attempt_count/outcome somente depois do commit. job_not_claimed pode indicar estado terminal, lease ocupada ou inelegibilidade; não é contador específico de deduplicação. Scheduler registra scheduled_count/published_count por tick; essas contagens não substituem gauges de backlog/PEL/leases ou histogramas agregados.

Formatter usa allowlist de eventos/fields/códigos e ignora msg arbitrária, args, exc_info, body, headers, URL/query e parâmetros SQL. Um sink fechado/indisponível por OSError/ValueError não impede response/commit/ACK. Helpers QA desviam somente a atividade estruturada para arquivos privados, conservando stderr de erro Uvicorn. Logs de frameworks/terceiros continuam independentes; não há exporter, heartbeat persistido ou backend de logs nesta etapa. Base técnica: [logging Python](https://docs.python.org/3/library/logging.html#logrecord-objects) e [middleware ASGI puro Starlette](https://starlette.dev/middleware/#pure-asgi-middleware).

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
