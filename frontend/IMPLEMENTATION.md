# Implementação do frontend Vigil

## 2026-10-04 — Observações REST, SSE e status pública integrados

### Implementado

- Métricas por projeto/monitor em 24h, 7d e 30d, uptime por amostras, média/p95 fornecidos pelo backend, contadores operacionais e série temporal. Valores null permanecem “Sem dados”; lacunas não geram uptime fictício.
- Detalhe de monitor com histórico paginado, um registro por ciclo, tentativas/duração, saúde após o ciclo e degradação. Incidentes por projeto/monitor, filtros de situação/janela e encerramento administrativo separado de recuperação.
- Publicação por opt-in de projeto e monitor, link público e rota `/status/:slug` sem consultas de autenticação/SSE. Polling público de 30s; 404 remove o snapshot e os incidentes quando a publicação é desativada.
- Dashboard usa REST inicialmente e após invalidações SSE, reconexão, retorno à aba visível e polling fixo de 30s. `snapshot.required` reconcilia projetos, monitores e observações; atualização de projeto selecionado também atualiza nome/configuração/link público. Projeto não selecionado invalida a lista de projetos.
- Eventos são somente sinais de invalidação. O payload não modifica saúde, checks, métricas ou incidentes diretamente, nem exige owner_id/source.
- Invalidações agrupadas em 200ms e retidas durante edição/confirmação/mutação. Fechar/salvar/cancelar o editor retoma a reconciliação, preservando o formulário enquanto estiver aberto.
- Leituras do mesmo recurso são serializadas: sinais recebidos durante uma consulta lenta geram uma nova leitura pendente, sem reiniciar indefinidamente a consulta. Troca de projeto, monitor, período, pausa para edição e desmontagem cancelam a leitura antiga.
- Leituras de listas anteriores à mutação não sobrescrevem o DTO salvo. Respostas/corpos cancelados e 401 de sessão anterior não invalidam uma sessão nova. Erro de stream consulta `/auth/me`; 401 fecha o stream e retorna ao login. Cleanup cancela timers, probes e EventSource.
- Paginação retorna à última página válida quando retenção reduz o total.

### Contrato alinhado com Backend

- `GET /api/v1/events`: cookie HttpOnly same-origin; nenhuma query ou credencial na URL.
- `snapshot.required`: `{reason: connected|periodic|backpressure}`.
- `project.updated`, `monitor.updated`, `incident.opened`, `incident.closed`: `{project_id, monitor_id?, incident_id?, revision}`. Revisão invalida REST; não há replay obrigatório nem resultados SSE.
- Backend confirma heartbeat de 15s e revalidação de sessão inicial/até 30s. Produtores atuais de projeto/monitor também invalidam consultas de incidentes.
- DTOs REST de `observations.py`, checks e `attempts.duration_ms` permanecem compatíveis, sem mudanças solicitadas ao Backend neste incremento.

### Arquivos principais alterados neste fechamento

- `src/App.tsx`, `src/Observations.tsx`, `src/live.ts`, `src/api.ts`.
- `src/test/App.test.tsx`, `src/test/Observations.test.tsx`, `src/test/live.test.tsx`, `src/test/api.test.ts`.
- `scripts/live-smoke.mjs`, `package.json`, `IMPLEMENTATION.md`.
- Integração já existente retomada em `src/Forms.tsx`, `src/types.ts`, `src/styles.css`, `src/test/fixtures.ts` e `scripts/browser-smoke.mjs`; estes arquivos não receberam novas edições neste fechamento.

### Evidências finais

- `npm.cmd test`: **41 passed em 5 arquivos**, sem skips. Cobre observações, contratos HTTP, filtros/paginação, publicação, snapshots lentos, cancelamento, sinais acumulados, polling, reconexão, cleanup e proteção de sessão.
- `npm.cmd run typecheck`: passou. `npm.cmd run build`: passou com TypeScript e Vite; JS 265,71 kB (gzip 81,83 kB), CSS 19,96 kB (gzip 4,54 kB).
- `npm.cmd run test:browser`: passou com Edge headless, API FastAPI real e PostgreSQL 18.6 local em 55432. Cadastro/login, CRUD, pausa/retomada, sessão após reload, histórico/métricas sem amostras, status pública anônima e desativação retornando 404. Todas as mutações 2xx; sem erros inesperados. Desktop 1440×900 e mobile 390×844 sem overflow, incluindo detalhes e página pública.
- `npm.cmd run test:live`: passou com EventSource nativo observado, sem mocks de rede. Recebeu snapshot connected, alteração de projeto externa à aba e snapshot periodic; a alteração e o período provocaram novas leituras REST. Logout externo retornou a UI ao login e fechou o stream. URL exatamente `/api/v1/events`; payloads observados sem owner_id/source; sem erros inesperados.
- Artefatos locais gitignored: `.impeccable/review/browser-smoke.json`, `.impeccable/review/live-smoke.json`, screenshots `desktop`, `mobile`, `mobile-editor`, `mobile-login`, `monitor-detail-desktop`, `monitor-detail-mobile`, `public-desktop` e `public-mobile` (`.png`). O relatório browser-smoke contém credenciais exclusivamente QA e não deve ser publicado.
- API iniciada sem reload em 127.0.0.1:8000; Vite em 127.0.0.1:5173. Gates pipeline/network explicitamente false. Nenhuma alteração em backend, infraestrutura, documentação raiz ou Git. Maestro consolida documentação/commit.

### Limites e próximos passos

- Redis/PubSub real e múltiplas réplicas ainda dependem da validação de Backend/Maestro; o smoke verifica SSE local e reconciliação REST, com Redis indisponível.
- Pipeline/network permanecem desativados. Não foram gerados checks externos: medições reais, incidentes abertos/recuperados e métricas não vazias foram validados com fixtures determinísticas, não de ponta a ponta. Retomar smoke desses estados após a habilitação validada do pipeline.
- Reconexão e falta de EventSource têm cobertura determinística; o smoke real verifica conexão, sinal externo, período e revogação, sem induzir queda física de rede/backpressure. A volta ao login pode ser detectada pelo stream/probe ou pelo polling REST; não prova isoladamente qual deles detectou primeiro.
- Sinais são efêmeros, sem replay. Polling continua mesmo com stream conectado, mas reconciliação de listas é adiada durante formulário/confirmação/mutação; consultas lentas concluem antes da leitura pendente.
- Freshness privada envelhece localmente a cada 15s; a pública usa o snapshot do backend a cada 30s. Não há sincronização dedicada de relógio.
- Reproduzir: API/Vite/PostgreSQL ativos, Edge instalado, `npm.cmd test`, `npm.cmd run typecheck`, `npm.cmd run build`, `npm.cmd run test:browser` e `npm.cmd run test:live` dentro de `frontend/`. Os smokes criam contas/projetos exclusivamente QA; test:live leva aproximadamente 60s, pois observa deadlines reais de 30s.
- Próxima continuidade: Maestro integra os arquivos liberados e registra o incremento em docs raiz; Backend valida Redis real e produtores de incidentes. Repetir smokes de métricas/histórico preenchidos e incidentes reais após esses gates.

## Primeiro incremento (histórico anterior à integração de observações)

Implementado em 2026-10-04. Propriedade de arquivos respeitada: somente frontend; Dockerfile, .dockerignore e nginx.conf são infraestrutura de Maestro e não foram alterados. Documentação de progresso e commits serão consolidados por Maestro. Não foi executado git init, commit ou push nesta sessão.

## Funcionalidades

- React + TypeScript estrito + Vite, interface em português, fonte Public Sans servida localmente e layout responsivo.
- Cadastro retorna ao login, limpa a senha e não autentica implicitamente.
- Login, restauração da sessão por GET /auth/me, logout e retorno ao login quando a API informa sessão expirada.
- Cookie enviado com credentials same-origin; token CSRF somente em memória, sem localStorage/sessionStorage. Mutações usam X-Vigil-Request: browser; autenticadas usam X-CSRF-Token. JSON enviado em cadastro/login e formulários.
- Projetos: listar todas as páginas, criar, editar, selecionar e arquivar com confirmação. Após arquivar o selecionado, seleciona o próximo projeto disponível.
- Monitores: criar/editar configurações GET, arquivar com confirmação e pausar/retomar usando o DTO retornado pela API.
- Formulários com labels, autocomplete, validação HTML, limites e regras de URL/orçamento/latência. Erros da API traduzidos para ações úteis, inclusive campos de validação e cotas.
- Dashboard com busca, atualização manual, loading, erros recuperáveis e estados vazios. Tabela desktop e linhas estruturadas em mobile. Skip link, foco visível, headings e estados anunciados por alert/status.
- Saúde histórica preservada e exibida separadamente de no_data, stale e paused. Resumo considera somente monitores fresh com saúde avaliada; resumo parcial é sinalizado. Dados sem medição nunca geram online ou 100% de uptime.
- Leitura de freshness envelhece a cada 15 segundos segundo intervalo do monitor; pausa prevalece. Consultas antigas são canceladas ao trocar de projeto. Navegação de projeto e logout são bloqueados durante salvamento de formulário, prevenindo atualização no projeto errado.

## Arquivos principais

- `src/App.tsx`: inicialização de sessão, dashboard e ações de projeto/monitor.
- `src/Forms.tsx`: autenticação e editores inline.
- `src/api.ts`: transporte, CSRF, erros estruturados e paginação.
- `src/domain.ts`: qualidade dos dados, agregação de saúde e regras de configuração.
- `src/types.ts`: subconjunto consumido dos DTOs confirmados diretamente com Backend.
- `src/styles.css`, `public/favicon.svg`, `index.html`: aparência, responsividade e metadados.
- `src/test/`: testes de domínio, transporte e fluxos de UI.
- `scripts/browser-smoke.mjs`: smoke reproduzível com API real e captura de evidências.
- `package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`: ferramentas e dependências locais.
- `PRODUCT.md`, `DESIGN.md`, `.impeccable/design.json`: contexto e sistema visual observado.

## Execução

Requer Node compatível com Vite 7 (nesta sessão: Node 24.16), API em localhost:8000 e banco configurado pelo backend.

```powershell
cd frontend
npm.cmd ci --cache .npm-cache
npm.cmd run dev
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

URL de desenvolvimento: `http://127.0.0.1:5173`. Vite usa porta fixa e proxy `/api` para `http://localhost:8000`, preservando Origin. Prefixo REST `/api/v1`.

Nesta máquina, npm precisou de `$env:NODE_USE_SYSTEM_CA='1'` para confiar na cadeia TLS do sistema; TLS permaneceu habilitado. Cache e node_modules ficaram dentro de frontend. Esbuild/Vitest/Vite precisaram de execução aprovada para iniciar subprocessos locais, pois a sandbox padrão retornou spawn EPERM. O loader native sozinho não resolveu a transformação; nenhum ajuste permanente de segurança foi feito.

## Validação concluída

- `npm.cmd run typecheck`: aprovado.
- `npm.cmd run build`: aprovado, bundle produzido em `dist/`.
- `npm.cmd test`: **18 testes aprovados** em 3 arquivos. Cobrem transporte/CSRF/204/401/paginação, no_data/stale/paused e prioridade da saúde, orçamento/URL/latência, cadastro sem login, CRUD, pausa/retomada, arquivamento de monitor/projeto, erro/retentativa e corridas de leitura/salvamento ao trocar projeto.
- `npm.cmd run test:browser`: aprovado com Edge instalado, API FastAPI e PostgreSQL locais reais. Sem interceptação/mock de rede. Cadastro 201, login 200, projeto POST/PATCH 201/200, monitor POST/PATCH 201/200, pause/resume 200, archive monitor 204 e logout 204.
- Smoke também validou restauração do cookie após reload e deixou um monitor real no_data na conta QA local; nenhum GET ao endpoint monitorado foi executado.
- Desktop 1440×900 e mobile 390×844: scrollWidth igual à largura do viewport, sem overflow horizontal. Editor e login mobile também verificados.
- Sem erros JS ou console inesperados. Chromium registra a resposta 401 esperada de GET /auth/me antes do login; ela é explicitamente registrada como expectedSessionProbes, separada de erros.
- Impeccable Operate/craft floor aplicado. Detector mecânico executado uma vez: zero findings. Direção implementada em código conforme o brief; seed sem challengers/boards disponíveis, sem comp visual aprovado.
- Revisão final independente encontrou F1, corrida durante salvamento; corrigida com busy compartilhado e teste de POST adiado. Veredito final **ship; F1 resolved**, limitado à correção indicada, com recapturas válidas.

Evidências locais (gitignored, geradas pelo smoke):

- `.impeccable/review/desktop.png`
- `.impeccable/review/mobile.png`
- `.impeccable/review/mobile-editor.png`
- `.impeccable/review/mobile-login.png`
- `.impeccable/review/browser-smoke.json`: resultado, HTTPs, viewports e credenciais da fixture exclusivamente QA. Não contém credencial de produção e não deve ser publicado.

O Portal Maestri permitiu fluxos reais e inspeção DOM; seus screenshots em Frontend QA sofreram timeout de renderização. O smoke Playwright produziu as capturas válidas usando o Edge já instalado. Para reproduzir, API e Vite devem estar ativos e Edge instalado; o comando não baixa browsers. Cada execução cria uma conta/projeto de QA e mantém um monitor no_data para revisão.

## Limites e continuidade

- Pipeline de verificações, SSE, métricas, incidentes, histórico e página pública ainda não integram este incremento. Nenhum número de uptime ou latência foi fabricado.
- Atualização REST é manual; envelhecimento local de freshness não substitui consulta atualizada nem sincronização de relógio.
- No navegador real, no_data e paused foram exercitados; stale/health históricos foram verificados nos testes determinísticos. O pipeline futuro deverá fornecer esses estados reais para smoke de ponta a ponta.
- Não há restauração de itens arquivados neste contrato.
- Testes de UI usam fixtures somente em `src/test/`; a aplicação executável não contém modo demo/mock.
- Cookies/headers dependem da configuração de origem e segurança do backend. `vite preview` serve o build, mas não substitui o proxy de desenvolvimento; deploy usa a infraestrutura nginx de Maestro.
- Maestro deve considerar excluir `.npm-cache` e `.impeccable/review` do contexto Docker ao consolidar infraestrutura; estes caminhos são locais e já estão no .gitignore do frontend.
- Próxima etapa: alinhar schemas reais de dashboard/métricas/incidentes/status público com Backend antes de integrar. Depois conectar snapshots REST e SSE com ressincronização, sem preencher lacunas com dados fictícios.
