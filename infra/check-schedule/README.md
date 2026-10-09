# Agenda externa do Vigil

Este Worker substitui a dependência exclusiva do evento `schedule` do GitHub.
Seu Cron Trigger UTC `2,17,32,47 * * * *` envia um `workflow_dispatch` a
`fmvini/Vigil/main`, workflow `free-checks.yml`. O runner Linux/Docker continua
responsável por DNS pinning, firewall, TLS, execução e persistência no Neon.
O Worker não acessa o banco nem recebe URLs de monitores.

A configuração versionada fica **desativada por padrão**. Não há rota HTTP,
workers.dev ou preview público; mesmo uma rota ativada por engano retorna 404
e não dispara jobs. O token não pertence ao frontend, Render ou Git.

## Publicação e ativação

1. Usar Workers Free, sem cartão/upgrade, e criar `vigil-check-schedule` na conta
   Cloudflare destinada ao Vigil. Não sobrescrever Workers de outros projetos.
2. Publicar `worker.mjs` como módulo principal, compatibility date `2026-10-09`,
   com `VIGIL_SCHEDULE_ENABLED=false`. Via Wrangler, usar `wrangler.jsonc` deste
   diretório. Via API, usar upload multipart com `main_module=worker.mjs`, parte
   JavaScript e `keep_bindings=["secret_text"]` em republicações para preservar
   o segredo existente. Manter observability habilitada e Logpush desligado.
3. Criar token GitHub fine-grained com somente repositório `fmvini/Vigil`,
   **Actions: Read and write** e Metadata read obrigatório. Não conceder
   Contents/Administration, outras contas ou todos os repositórios. O destino
   do código é fixo; Actions write ainda permite gerenciar outros workflows
   desse repositório, pois GitHub não oferece escopo de um único workflow.
4. Guardar o valor exclusivamente como **Secret**
   `VIGIL_GITHUB_ACTIONS_TOKEN` do Worker de produção. Renovar antes da expiração
   registrada no log de desenvolvimento. Não imprimir, salvar em arquivos,
   passar em argumentos de shell ou colocar no `wrangler.jsonc`.
5. Confirmar `VIGIL_FREE_CHECKS_ENABLED=true` e `free-checks.yml` ativo no GitHub,
   repository público, default branch `main`, runner padrão e secret de banco
   já configurado. O Cron Trigger não ignora essas guardas.
6. Definir `VIGIL_SCHEDULE_ENABLED=true` somente na produção, cadastrar o cron
   UTC e desativar workers.dev/previews. Alterações do cron podem demorar até
   15 minutos para propagar; confirmar uma invocação agendada real.
7. Localizar o `workflow_run_id` no recibo `dispatch_accepted` dos logs Workers.
   Conferir o run GitHub correspondente: `completed/success`, batch `status=ok`
   e cleanup confirmado. Conferir novo `last_checked_at`, histórico/métricas
   e status pela API/UI de um monitor próprio. HTTP 200 do dispatch comprova
   aceitação; não comprova medição ou persistência.

Se não houver acesso à conta/token, a configuração preparada não equivale a
agenda ativa. Não alterar o gate dos checks web para substituir o executor.
O `schedule` GitHub permanece fallback e a concorrência do workflow serializa
os disparos. As duas agendas ficam ativas em paralelo: não há detecção automática
de falha do Cloudflare antes de um disparo GitHub. Rodadas extras podem ocorrer,
mas a admissão pelo banco preserva o intervalo. Não criar outro workflow para
contornar essa concorrência.

## Intervalos e limites

São 96 disparos/dia, uma chamada GitHub por invocação e timeout de 10 segundos.
Esse número conta somente o Cron Trigger Cloudflare; eventos da agenda GitHub
ou disparos manuais aumentam o total de rodadas e o consumo de banco.
Não há retry automático de dispatch ambíguo, para evitar rodadas duplicadas.
Erros HTTP/recibos/fetch são sanitizados, sem response body, headers ou token.
O transporte usa `redirect=manual` e rejeita qualquer status diferente de200;
não segue Location. O runtime workerd rejeita `redirect=error` antes do I/O,
apesar do tipo Web padrão/documentação Request listar esse valor. Diagnóstico
registra somente fase, classe de erro permitida, abort, tempo e status numérico.

O banco admite somente monitores realmente devidos, com intervalo mínimo900s.
O batch pode aguardar **até30s acumulados**, sem conexão/lease durante a espera,
quando o próximo monitor estiver ligeiramente no futuro e ainda houver prazo
para o orçamento máximo do ciclo. Revalida admissão pelo relógio do banco após
acordar; não antecipa checks e não fabrica slots omitidos. Jitter maior ou
preflight lento ainda pode pular uma rodada. Cloudflare e GitHub não fornecem
SLA de15min nesse perfil, e a primeira medição aguarda um disparo.

Não aumentar para cron5min sem avaliar quotas:288 rodadas/dia podem manter o
Neon acordado com suspensão5min e esgotar CU-hours Free. A agenda não faz pings
de keep-alive no Render. Dados publicados continuam chegando pelo REST30s.

Para pausar, colocar `VIGIL_SCHEDULE_ENABLED=false` na produção. Para remover o
cron pelo Wrangler, definir `triggers.crons=[]` explicitamente; comentar a
propriedade não remove o cron remoto. Revogar o token somente depois de pausar
ou concluir sua substituição. Não remover banco, monitores ou históricos.

## Verificação local

```powershell
node --test --test-isolation=none infra/check-schedule/worker.test.mjs
```

Os testes usam fetch controlado; não demonstram a cadência cloud. O upload do
módulo no provedor valida sua sintaxe/runtime, mas a prova final é a sequência
Cron Trigger → run GitHub → check persistido.

O workflow manual `.github/workflows/verify-web.yml` executa estes testes e
`npm ci && npm test && npm run build` oficiais em Node24/Linux, sem secrets
de produção ou execução de monitores. Usar antes de publicar quando o ambiente
local bloquear subprocessos Vite/Vitest. A existência do workflow não equivale
a uma execução aprovada; conferir `completed/success` na revisão enviada.

Fontes: [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/),
[Workers Free limits](https://developers.cloudflare.com/workers/platform/limits/),
[GitHub dispatch API2026-03-10](https://docs.github.com/en/rest/actions/workflows?apiVersion=2026-03-10#create-a-workflow-dispatch-event),
[Cloudflare upload](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/update/),
[workerd Request redirect parser](https://github.com/cloudflare/workerd/blob/main/src/workerd/api/http.c%2B%2B).
