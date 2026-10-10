# Registro de desenvolvimento

## 2026-10-10 — Contato do responsável e explicação de cookies

### Implementado
- E-mail `viniciusfmarrocos@gmail.com` informado pelo usuário como canal do responsável nos Termos, na Política de Privacidade e na Política de Cookies.
- Aviso explica o identificador usado pelo cookie de sessão e as preferências de tema e escolha guardadas no navegador antes dos botões de aceitar ou continuar sem aceitar.

### Arquivos principais alterados
- `frontend/src/legalContent.ts`, `frontend/src/Legal.tsx`, `frontend/src/test/Legal.test.tsx`
- `docs/LEGAL.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Mantida a versão `2026-10-09`: preenchimento do contato e esclarecimento das práticas existentes, sem novas finalidades ou tecnologias. Backend, migrations e registros históricos de aceite permanecem compatíveis.
- Nome completo do responsável não foi inferido do e-mail. Escolhas de cookies, recusa, reabertura pelo rodapé e autenticação seguem o fluxo existente; o cookie necessário à sessão continua sendo usado ao entrar.

### Estado atual
- Validação oficial das fontes desta unidade aprovada fora do sandbox: `npm test -- --reporter=dot` com 143/143 testes em 15 arquivos e `npm run build` com TypeScript/Vite. `git diff --check` passou; Maestro revisou os cinco arquivos da unidade. Sem nova campanha visual global, push ou deploy.
- A unidade não resolve as pendências de identificação completa, conservação de dados e atendimento operacional em `docs/LEGAL.md`, nem o gate visual do redesign.

### Próximos passos
- Unidade registrada com implementação, testes e documentação no mesmo commit local. Publicar somente na etapa integrada autorizada; o site em produção ainda não recebeu esta atualização.
- Antes da publicação integrada, concluir as pendências de LEGAL, validar o ambiente de produção e tratar o requisito de fidelidade do redesign conforme o checkpoint anterior.

## 2026-10-10 — Superfícies DARK aproximadas do comp

### Implementado
- Lote6 material do redesign: 23 tokens de superfícies/chrome/texto DARK restritos ao console e texto principal do cabeçalho da tabela. Painel `#16251f`, trilho `#15231e`, canvas `#0f1d19`, cabeçalho `#1e2b27` e texto principal `#f1f2f2`, com amostras da referência e documentação final dos tokens.
- Preservados geometria fix5, margem desktop16px, seis monitores, URLs/cadência/metadados, ações, filtros44px, saúde/ressalvas e tema claro. O mobile DARK recebe apenas a mudança tonal.

### Arquivos principais alterados
- `frontend/src/styles.css`, `frontend/DESIGN.md`, `frontend/.impeccable/design.json`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Frontend reassumiu explicitamente `frontend/`; não houve agente/reviewer novo. Maestro realizou revisão independente do pacote em `.cache/verification/redesign-fix6-maestro-review.md` e não editou fontes frontend.
- Tokens derivados de áreas reais do comp, sem gradientes/rasters decorativos, mudanças de caixas/pesos do comparador ou force. Semântica de saúde/qualidade, accent e foco existentes preservados.
- Encerrado este lote bounded; nenhum microajuste adicional indicado. Continuar exige novo objetivo material ou decisão explícita aceitando design adaptado e liberando reprodução numérica; o pedido de retomada não concedeu essa liberação.

### Estado atual
- Após liberação de permissão e pedido explícito de commit, testes/build oficiais das mesmas fontes passaram fora do sandbox:143/143 em15arquivos/11,23s e `npm run build` com TypeScript/Vite aprovado. Antes dessa liberação, os comandos encontravam spawnEPERM e o fallback143/143/bundleCLI já haviam passado; nenhuma assertion foi alterada.
- Freeze6 de38fontes `8e6783b3c6e9eb061790aaada8d99438b722d527052b051366ba5c8e8f1e2a9d`: sóCSS mudou frente ao freeze5. Maestro recalculou os38hashes e os5hashes de capturas sem divergência.
- Cinco capturas finais válidas em `frontend/.impeccable/review/redesign/final/`, before-fix6 preserva fix5. Primeiro frame1440claro ficou truncado1440x707 durante a interrupção de janela; preservado em fix6-invalid e substituído somente ele uma vez. Finais1440x884,390x836,1586x984; zero diferenças de geometria DOM e nenhum overflow de página reportado. Raster segue8px menor que DOM.
- Objetivo tonal resolvido na revisão do Maestro; nenhuma regressão introduzida evidenciada nas cinco capturas. Gate continua aberto64,50%<72%, contra63,14% dofix5. Cor80,67→80,19% e detalhe46,29→44,60% caíram; melhora local dos fundos não implica melhora global de todas as métricas. Heroopen/ok:false/forced:null.
- Sem nova certificação AA, teclado físico, full-page, desempenho/backend. Outras8Operate/25públicas retêm provas anteriores. Usuário solicitou explicitamente commit do estado implementado após liberar permissão: implementação verificada registrada como unidade local por solicitação do usuário, mantendo o requisito de fidelidade aberto. O pedido de commit não libera o gate e não autoriza push/deploy.

### Próximos passos
- Retomar por `fix6-handoff.md`, `fix6-proof.json` e revisão Maestro; não repetir este lote de capturas/detector nem testes aprovados sem nova mudança ou problema. Frontend permanece proprietário de seus arquivos, sem edição ativa ao entregar.
- Resolver o requisito de fidelidade por objetivo material verificável que preserve dados/funcionalidade, ou colher decisão explícita do usuário sobre aceitar o design adaptado. Não tratar64,50% como aprovação.
- Antes de publicar, validar navegação física por teclado, resolver contatos/políticas pendentes em LEGAL e o requisito visual. Testes/build oficiais já passaram para estas fontes. O redesign existente e sua documentação são registrados juntos por pedido explícito, sem push automático; novas mudanças devem formar outra unidade coerente.

## 2026-10-10 — Backup compatível com aceites e continuidade reconciliada

### Implementado
- Corrigido inventário do manifesto de backup Compose, que recusava o schema atualizado pela migration `0003_legal_acceptances`. Agora inclui oito tabelas de produto mais `alembic_version`, calculando digest dos aceites por `id` e comparando seu catálogo sem deduplicar logins repetidos.
- Regressões confrontam o inventário com os models, exercitam manifesto/digest com dois aceites e detectam alteração de conteúdo com contagem igual, tabela ausente/extra e drift de colunas/constraints/índices.
- DATABASE descreve LegalAcceptance/cadeia atual; ARCHITECTURE distingue transporte, cache planejado, SSE, heartbeat e batch implementados; ROADMAP registra a etapa atual e suas pendências. OPERATIONS explica o inventário atualizado e limites de ambos os helpers de backup.

### Arquivos principais alterados
- `scripts/backup_restore_check.py`, `scripts/tests/test_backup_restore_check.py`
- `docs/DATABASE.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Mantido inventário estático e exato em ordem alfabética: destinos anteriores à tabela de aceites são recusados, sem migration automática, descoberta permissiva ou nova dependência de aplicação no runtime do tooling.
- Preservados snapshot/export, validação de cluster/labels/PG17, restore UUID e cleanup. Uma linha de revisão Alembic e igualdade origem/restauração não certificam head instalado ou paridade global de schema.
- Maestro reutilizou Frontend, Backend e Banco de Dados existentes. Frontend reassumiu propriedade exclusiva de `frontend/`; Maestro possui scripts/documentação. Nenhum modelo/migration/backend de produto foi alterado.

### Estado atual
- Correção revisada e aprovada somente leitura pelo Banco de Dados. Backend revisou a documentação; corrigidas duas formulações sobre prazos do heartbeat/diagnóstico e atividade na abertura do SSE.
- Após liberação de permissão, `pytest` do módulo completo:36 passed/2skipped por ausência de PG17, sem deselections ou falhas. Os quatro casos de subprocessos/temp anteriormente bloqueados também passaram. XML: `.cache/verification/backup-commit-approved-20261010.xml`. Ruff com configuração backend e whitespace passaram; dump/restore físico ainda não foi executado.
- Docker/PG17 indisponíveis; nenhum cluster compartilhado iniciado, migration aplicada, endpoint externo executado ou estado cloud consultado. O wrapper PG18 anterior continua consultando apenas as sete tabelas pré-aceites, embora faça dump de `public` inteiro.
- Implementação do fix concluída e validada. Usuário liberou permissão e solicitou commit local; Maestro registra o fix com seus testes/documentação em unidade separada do redesign. Sem push ou deploy.

### Próximos passos
- Quando PG17/Compose estiver disponível, executar `scripts/test-compose-backup-restore.ps1` em destino QA explicitamente verificado com schema0003 e aceites repetidos; conferir nove entradas, hashes/catálogo, snapshot e cleanup confirmado.
- Os quatro casos antes bloqueados já passaram. Evoluir o helper PG18 para verificar aceites somente em unidade deliberada, sem tratá-lo como prova equivalente ao manifesto Compose.
- Fix/testes/documentação reconciliada são registrados juntos conforme pedido explícito, mantendo o redesign em outro commit. Não enviar ao remoto automaticamente.
- O lote6 DARK já foi revisado pelo Maestro; preservar a pendência de fidelidade até nova prova ou decisão explícita do usuário.

## 2026-10-10 — Redesign interrompido a pedido do usuário

### Implementado
- Lotes3–5 do mesmo achado de fidelidade: quatro grupos de qualidade com símbolos decorativos, zona de saúde compacta, controles menos pesados, URLs13px, nomes16px, título de saúde20px, colunas alinhadas e fluxo flexível nome/cadência. Corrigida fragmentação evitável em1440px; filtros44px preservados em faixa~71,5px.
- Último lote altera somente margem desktop entre masthead e heading de22px para16px. Reviewer recomenda manter essa versão pela posição mais próxima do comp, encerrando ajustes de margem.

### Arquivos principais alterados
- `frontend/src/App.tsx`, `frontend/src/styles.css`
- `frontend/DESIGN.md`, `frontend/.impeccable/design.json`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Nenhuma mudança backend/API/autenticação/conteúdo legal/dados ou dependência. Seis monitores e todas as ressalvas preservados; sem gráfico fictício, ocultação de linhas ou mudança de caixas do comp.
- Último score caiu67,74%→63,14% apesar do alinhamento visível mais próximo. Reviewer não atribui causalidade isolada ao CSS: composite inclui timestamps/crops e bandas. Não restaurar versão anterior somente para perseguir score; nenhuma liberação do gate inferida de “pode continuar”.

### Estado atual
- Usuário pediu encerrar por hoje para dormir e continuar amanhã. Nenhum novo ajuste/QA iniciado após essa instrução; somente checkpoint de continuidade. Sem staging/commit/push/deploy: unidade de redesign ainda aberta.
- Freeze38 fontes `.cache/verification/redesign-frontend-fix5-source-freeze.json`, agregado `d91496227a47171755ca9fcb6ff7fa0b2b29c0c559ff2e40cdc84bcac9400d1e`; sóCSS mudou contra fix4.143/143 Vitest validou as mesmas fontesTS/TSX; typecheck do lote4 e bundle CLI do lote5 passaram. Teste/build oficiais permanecem bloqueados por spawn EPERM, sem nova tentativa.
- `frontend/.impeccable/review/redesign/verdict4.md`: três direções resolvidas, fragmentação fechada, sem novas regressões. `verdict5.md`: alinhamento resolvido e nenhuma regressão visível, disposição fix porque gate segue parcial63,14%<72%. Encerrar microajustes de margem; não tratar como aprovação global.
- Cinco paths Operate finais atuais em `frontend/.impeccable/review/redesign/final/`; before-fix5 preserva fix4. Outros oito Operate/25públicos retêm escopo anterior. Raster8px menor que DOM, sem full-page/AA/teclado físico/backend certificado. Preview sintético5187 preservado, sem conta/API real.

### Próximos passos
- Retomar por este checkpoint e `verdict5.md`; não repetir context/detector/auditoria global nem testes já aprovados sem nova mudança. Frontend atingiu limite de uso; Maestro assumiu App/CSS explicitamente, verificar disponibilidade/propriedade antes de retomar concorrência.
- Apresentar ao usuário a pendência de fidelidade e definir objetivo material dirigido pelo comp antes de outra rodada. Encerrar como design adaptado exige decisão explícita liberando o gate; não forçar aprovação. Priorizar conteúdo/funcionalidade sobre pixels fictícios.
- Após conclusão: conferir build oficial/teclado físico em ambiente capaz, atualizar DESIGN/log e agrupar implementação/docs/testes correspondentes em commit local. `.git` tem restrição de escrita nesta sessão; não contornar permissões nem fazer push automático.

## 2026-10-10 — Aproximação da referência no console

### Implementado
- Continuação solicitada pelo usuário, restrita ao achado de fidelidade do finish reviewer: cabeçalho de Monitores compacto, endpoint com nome/método/cadência e URL, tipografia desktop ampliada e ícones SVG decorativos nas ações existentes.
- Terceiro lote: faixa de saúde com zona de220px e quatro grupos de qualidade com símbolos de44px, lettering menos pesado nas ações, URLs de13px e proporções da tabela alinhadas às âncoras do comp em1586px. Quarto lote corrige fragmentação evitável dos nomes em1440px com fluxo flexível de nome/cadência; nomes16px e heading de saúde20px, faixa de filtros~71,5px com controles44px. Dados, seis monitores, labels, handlers, ressalvas e layout mobile preservados.

### Arquivos principais alterados
- `frontend/src/App.tsx`, `frontend/src/styles.css`, `docs/DEVELOPMENT_LOG.md`
- `frontend/DESIGN.md` e `frontend/.impeccable/design.json`, revalidados independentemente após o lote.

### Decisões técnicas
- Sem gráfico fictício, dependência, texto legal ou mudança de contrato. Frontend atingiu limite após lote2; Maestro assumiu App/CSS para os três ajustes indicados pelo reviewer, com propriedade explicitamente comunicada.
- Em1440px a primeira captura do lote3 revelou overflow local na tabela; distribuição específica1151–1500 corrigiu esse problema. Nenhum novo detector manual ou busca independente de defeitos.

### Estado atual
- Typecheck aprovado;143/143 testes em15 arquivos via fallback CLI/Vitest em22,18s, sem alterar assertions; bundle CLI fresco aprovado. Loader oficial Vite/Vitest continua bloqueado por spawn EPERM; não afirmar build oficial aprovado.
- Freeze38 fontes `.cache/verification/redesign-frontend-fix4-source-freeze.json`, agregado `7d83df7705c99c48e69d3c3d0d7f55f3c26a9544d61d4563a8208f6faf3d1024`; somente CSS alterado contra fix3,37 idênticos. Vitest143/143 validou as mesmas fontesTS/TSX do freeze4; mudança posterior somenteCSS validada por typecheck/bundle e capturas. `redesign-proof.json` confirma zero divergências e pixels dos PNGs da marca preservados.
- Lote3 realizou duas capturas dos mesmos cinco viewports, com correção local entre elas; final é o segundo conjunto. PNGs atuais em `frontend/.impeccable/review/redesign/final/`; before-fix3 guarda o primeiro conjunto deste lote, não o final anterior. Os outros oito PNGs Operate e25 públicos retêm escopo anterior. DOM/raster diferem8px; nenhuma captura full-page ou certificação de teclado físico/AA/backend.
- Os mesmos cinco paths foram recapturados uma vez no lote4; before-fix4 preserva finalfix3. Nomes maiores agora usam largura disponível antes de realocar cadência; URLs completas podem legitimamente quebrar. Mobile mantém resumo y499–679,19 e Monitores y691–719 no raster836px. Sem overflow horizontal de página amostrado.
- Score de fidelidade cresceu de62,30% para65,50% e67,74% em `frontend/.impeccable/review/redesign/final-fix4/report.json`, ainda abaixo do gate72%; hero record recusado, sem force/reponderação/mudança de caixas. Verdict3 parcial confirmou strip/pesos, pediu corrigir fragmentação e escala; verdict4 em processamento independente. Sem staging/commit/push/deploy enquanto esta unidade permanece aberta.

### Próximos passos
- Incorporar `frontend/.impeccable/review/redesign/verdict4.md` e continuar somente seus achados materiais, respeitando o limite de rodadas da skill e a direção do usuário. Preservar gate aberto enquanto falho; não registrar aprovação global.
- Executar build oficial e teclado físico em ambiente capaz antes de publicar. Agrupar redesign/documentação/testes correspondentes em um commit local quando a unidade estiver concluída, sem push automático.

## 2026-10-09 — Redesign integral Centro de controle

### Implementado
- Direção visual escolhida pelo usuário com Impeccable e Taste em todo o site: acesso/cadastro, dashboard, demonstração, status pública, políticas, cookies e 404. Superfícies minerais, Public Sans local, marca existente e geometria compartilhada entre temas claro/escuro.
- Console com trilho de projetos, ações reais no cabeçalho, resumo independente de saúde/qualidade e monitores antes da investigação e configuração. Métricas/incidentes em grid 2:1 no desktop; incidentes em região nomeada/focável com rolagem limitada e paginação preservada.
- Acesso prioriza formulário e aceites; políticas recebem índice lateral e coluna de leitura. Mobile usa navegação compacta e quatro contagens em duas colunas; resumo completo e título Monitores aparecem dentro da primeira captura. Botões de histórico incluem nome/URL/cadência na mesma área nativa, com 53px medidos no desktop.
- Contratos de autenticação/API, conteúdo e versões legais, preferências de cookies, DTOs, dados reais e ressalvas históricas preservados. Nenhuma dependência nova ou alteração backend/banco.

### Arquivos principais alterados
- `frontend/src/App.tsx`, `frontend/src/Forms.tsx`, `frontend/src/Observations.tsx`, `frontend/src/Legal.tsx`, `frontend/src/styles.css`, `frontend/src/ProcessingFailures.css`
- `frontend/.impeccable/surfaces/src-app-tsx.md`, `frontend/.impeccable/mocks/decision/redesign-control.png` e sidecar JSON de origem/aprovação
- `frontend/DESIGN.md`, `frontend/.impeccable/design.json`
- `.gitignore`, `frontend/public/apple-touch-icon.png`, `frontend/public/brand/vigil-logo.png`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Operate governa o console, Read os documentos; Taste orienta apresentação sem inserir convenções de marketing no console. Seed `e183038d`, direção 6, comp escolhido de 1586x992; catálogo remoto indisponível reportado. Public Sans permanece fixada pelo brief.
- Seis monitores reais, metadados, ações, dados e métricas existentes têm prioridade sobre quatro linhas e gráfico fictícios do conceito. Nenhum avatar/settings/help/sorting/chart foi inferido do mock. Essas adaptações não constituem aprovação de fidelidade exata.
- Dois PNGs de marca receberam apenas metadados de origem: chunks de pixels conferem com HEAD. Comp escolhido contém prompt exato; scan de três rasters não encontrou origem ausente. Build/review/cache são ignorados no Git.

### Estado atual
- TypeScript aprovado; 143/143 testes em 15 arquivos passaram novamente após correções, usando esbuild CLI e Vitest com configuração nativa/preserveSymlinks, sem alterar fontes ou assertions dos testes. Bundle CLI fresco compilou. `npm test`/`npm run build` oficiais continuam bloqueados antes da execução pelo loader/esbuild `spawn EPERM` nesta sessão.
- Freeze final de 38 fontes: `.cache/verification/redesign-frontend-fix-source-freeze.json`, agregado `11d8ba2f19d27990d4d34555ed3e2aff50ebbad1638cb3f4a498c54163e70388`, zero divergências. Provas `redesign-vitest.json` e `redesign-proof.json` na mesma pasta.
- Preview sintético local `http://127.0.0.1:5187`, sem conta/cloud/API real. Revisão independente abriu 13 capturas Operate + 25 públicas válidas com cobertura representativa desktop/mobile claro/escuro. Cinco imagens nomeadas do console foram recapturadas após o lote material, preservando os originais em `frontend/.impeccable/review/redesign/before-fix1/`.
- Portal perde 8px no raster: DOM 1440x892/390x844/1586x992 produz PNG 1440x884/390x836/1586x984. São capturas de viewport e trechos rolados; sem full-page, reprodução exata do comp, certificação AA, foco/teclado físico, performance ou integração backend. Capturas anteriores retêm o escopo do primeiro freeze.
- Finish reviewer em `frontend/.impeccable/review/redesign/finish-review.md` pediu quatro correções: gate do comp, composição mobile, targets desktop e seed em FORM. Veredito `verdict1.md` marcou mobile/targets/seed resolvidos e medições corrigidas; gate parcial/aberto, com score 62,29% abaixo de 72%, sem force. Nenhuma regressão evidenciada nas cinco recapturas; veredito restrito à lista de quatro itens, não aprovação global.
- Documenter independente substituiu `frontend/DESIGN.md` e `frontend/.impeccable/design.json` por tokens claros/escuros, Public Sans, formas, composição, componentes e limites extraídos das fontes finais. Verificou 108 cores usadas contra CSS, referências, oito seções canônicas e dez snippets; nenhum linter externo de schema foi executado. PRODUCT não foi alterado; drift factual anterior não recebeu reparo incidental.
- Em 2026-10-09 o usuário pediu explicitamente continuar aproximando da referência, sem liberar o gate. Segundo lote material em andamento: cabeçalho/tabela mais compactos, endpoint em duas linhas com nome/método/cadência e URL, tipografia e chrome de ações reais. Reutiliza o mesmo reviewer e cinco viewports nomeados; não registrar aprovação ou commit intermediário.
- Detector executado uma vez; output truncado mostrou avisos de rampas contra DESIGN anterior. Não há relatório completo limpo nem segunda execução. Nenhum staging/commit/push/deploy nesta etapa.

### Próximos passos
- Concluir segundo lote de fidelidade solicitado, reconstruir/testar as fontes, recapturar cinco viewports e enviar ao mesmo reviewer para `verdict2`. Revalidar DESIGN.md/sidecar após o lote. Sem novo detector ou caça de defeitos.
- Executar testes/build oficiais em ambiente que permita spawn, conferir teclado/focus-visible em navegador ativo e validar release antes de publicação. Não enviar ao remoto automaticamente.
- Preservar pendências reais de contato/retencão em `docs/LEGAL.md`; redesign não altera conteúdo legal. Git deve agrupar implementação, design e este log em uma unidade concluída.

## 2026-10-09 — Políticas, aceites de autenticação e página 404

### Implementado
- Páginas públicas `/privacy`, `/terms` e `/cookies`, com leitura por seções, navegação, versão `2026-10-09`, temas existentes e acesso pelo rodapé. Conteúdo descreve o serviço real, dados tratados, publicação opcional, fornecedores, retenção e direitos; contato do responsável permanece explicitamente pendente porque não foi informado.
- Cadastro e login exigem dois aceites independentes, inicialmente desmarcados, com validação HTML e guarda antes da requisição. Links preservam o formulário em outra aba; troca de modo e cadastro concluído limpam os aceites.
- API exige `terms_version` e `privacy_version` como strings estritas iguais às versões atuais; ausência, tipo incorreto ou versão antiga retorna 422. Cada autenticação bem-sucedida acrescenta registro de aceite na transação da conta/sessão; falhas não produzem aceite nem credencial. Sessões existentes permanecem válidas.
- Modelo `LegalAcceptance` e migration `0003_legal_acceptances`, descendente de `0002_incident_evidence_indexes`: conta, versões, horário UTC e ação register/login, FK sem cascade e índice não único. Nenhum IP/user agent, aceite retroativo ou deduplicação.
- Aviso de cookies com aceitar/continuar sem aceitar, reabertura pelo rodapé, preferência local versionada por 180 dias, sincronização entre abas e tolerância a storage indisponível. Somente cookie necessário de sessão e preferências existentes; nenhuma integração de analytics/marketing.
- Página 404 compartilhada pelo site e demonstração. Rotas reconhecidas recebem HTML 200; páginas desconhecidas recebem HTML 404 sem autenticação; namespaces API/health e arquivos ausentes preservam JSON 404. Scripts QA de autenticação acompanham o novo contrato.

### Arquivos principais alterados
- `frontend/src/Legal.tsx`, `frontend/src/legalContent.ts`, `frontend/src/cookiePreference.ts`, `frontend/src/App.tsx`, `frontend/src/DemoApp.tsx`, `frontend/src/Forms.tsx`, `frontend/src/styles.css`
- `frontend/src/test/Legal.test.tsx`, `frontend/src/test/App.test.tsx`, `frontend/src/test/AuthErrors.test.tsx`, `frontend/src/test/DemoApp.test.tsx`, `frontend/src/test/api.test.ts`
- `frontend/scripts/legal-consent.mjs`, `frontend/scripts/legal-smoke.mjs` e clientes smoke existentes
- `backend/app/legal.py`, `backend/app/api/auth.py`, `backend/app/api/schemas.py`, `backend/app/web.py`, `backend/app/db/models.py`, `backend/migrations/versions/0003_legal_acceptances.py`
- `backend/tests/test_legal_auth.py`, `backend/tests/test_db_legal_acceptances.py`, `backend/tests/test_web.py` e fixtures/clientes de autenticação existentes
- `README.md`, `docs/API.md`, `docs/LEGAL.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Versões centralizadas em frontend/legalContent e backend/legal. Histórico append-only pelo fluxo da aplicação, sem trigger de imutabilidade no banco; cada login registra nova linha. Migration não fabrica consentimento para usuários existentes.
- A transação externa da requisição inclui usuário/aceite ou sessão/aceite. Removido savepoint do cadastro para garantir rollback SQLite quando o commit final falha; testes também exercitam PostgreSQL real.
- Ciência da política e aceitação contratual não são consentimento genérico para novas finalidades. Recusar o aviso não impede cookie estritamente necessário ao login solicitado. Preferência do aviso permanece no navegador, independente dos aceites de autenticação.
- Impeccable usado como extensão da identidade existente. Fontes React/TS compiladas individualmente via esbuild CLI permitiram executar Vitest com config nativa e preserveSymlinks sem alterar assertions, dependências do produto ou fontes para contornar o ambiente.
- Frontend, Backend e Banco coordenados via Maestri, respeitando propriedade dos arquivos; documentação e Git centralizados no Maestro.

### Estado atual
- Retomada para commit após liberação de permissão: 143/143 testes oficiais Vitest em 15 arquivos passaram, incluindo 19 casos legais; build TypeScript/Vite aprovado (50 módulos, JS `index-CT3En0jD.js`, CSS `index-O_W-0rcP.css`). As fontes frontend/backend/banco conferem com os hashes das campanhas anteriores. Nenhum push/deploy nesta retomada.
- Na sessão original, TypeScript e 143/143 testes frontend pelo fallback CLI/Vitest passaram; `npm test` padrão e Vite build eram bloqueados por spawn EPERM. A execução aprovada fora do sandbox resolveu esse bloqueio na retomada. Evidência original com hashes `.cache/verification/legal-frontend-vitest-proof.json` preservada.
- Banco: 105 testes direcionados e regressão completa de test_db com 165 passed/2 skipped em PostgreSQL18.6 real, cluster QA próprio isolado55435. Skips apenas ensaios com lease PG17. Upgrade preserva integralmente sete tabelas populadas, downgrade/reupgrade, SQL offline, metadata, constraints, FK e rollback verificados. Evidências `.cache/verification/legal-db-targeted.xml` e `.cache/verification/legal-db-regression.xml`.
- Backend: regressão ampliada 345 passed/8 skipped em 424,08s, mais quatro casos de preservação de sessões aprovados. SQLite e PostgreSQL18.6 verificaram rejeição sem mutação, versões, repetição de aceites, isolamento, rollback de insert/commit/rehash/rotação e sessões legadas/outro dispositivo. Skips incluem locks/concorrência PostgreSQL na variante SQLite e réplicas Redis indisponíveis. Hashes das 12 fontes conferidos contra `.cache/verification/legal-backend-proof.json`; XMLs `backend-legal-regression.xml` e `backend-legal-existing-sessions.xml`. Ruff e diff-check passaram; testes HTTP usam build sentinela, sem comprovar render React.
- QA funcional rodada1 em bundle CLI sintético local5175 concluiu quatro matrizes (1440x892 e390x836, claro/escuro): login/políticas/404/demo404/rodapé/aviso sem overflow pelo DOM, ações cookies com44px/tratamento equivalente, ambas escolhas/180dias/reabertura/foco e storage bloqueado. Guarda de submit, versões, cadastro/login e reset passaram com transporte sintético sem API/cloud real. Relatório `frontend/.impeccable/review/legal-round1/portal-report.json`,32 snapshots DOM e `auth-functional.json`; fontes freeze com zero divergências de hashes, sintaxe dos sete scripts aprovada. Falha inicial de troca de modo era clique do portal sem ativação; clique DOM acionou o mesmo handler React e provou reset, sem mudança de produto, diagnóstico preservado.
- Nenhuma screenshot atual válida: captura/check do portal impedidos por janela sem renderização, Playwright launch bloqueado por spawn EPERM. DOM não certifica composição/contraste/teclado físico. Nova aba e storage entre abas foram exercitados em Vitest, sem certificação física no navegador. Nenhuma captura antiga foi usada como prova; revisão visual independente permanece pendente. Preview5175 preservado, portal em `/cookies`, tema Sistema/desktop.
- Detector Impeccable sem findings primários, somente advisories de tipografia contra documentação existente. Identidade e documentação de design preservadas; sem reparo incidental de drift anterior.
- Finish reviewer independente conferiu fontes e os 38 hashes frontend sem defeitos materiais verificáveis; disposição `recapture`, sem aprovação visual por ausência de capturas atuais. Documenter independente confirmou extensão do sistema por diff/fontes e anterioridade do drift de borda/tema em HEAD; `PRODUCT.md`, `DESIGN.md`, sidecar e tokens preservados.
- Banco encerrou somente seu cluster QA55435 após liberação do Backend, com diretório/PID confirmados, nenhum cliente/schema QA restante e socket fechado. pg_ctl foi bloqueado pelo sistema; Stop-Process somente no PID confirmado conseguiu encerrar. Arquivos preservados, com pidfile residual que pode exigir recovery se o cluster descartável for reutilizado. Prova `.cache/verification/legal-db-cleanup.json`; nenhum cluster compartilhado alterado.
- Recurso local, sem aplicação da migration em produção, push ou deploy. Identificação/e-mail do responsável, prazos de conservação de conta/configurações/aceites e atendimento dos titulares precisam ser definidos antes da publicação definitiva dos documentos; pendências em `docs/LEGAL.md`.
- Na sessão original, staging explícito dos 42 arquivos relacionados falhou com Permission denied ao criar `.git/index.lock`, com `.git` somente leitura e approval never. Na retomada, o usuário liberou a permissão e solicitou novamente o commit local; implementação, testes e documentação compõem uma única unidade, sem push/deploy.

### Próximos passos
- Concluir evidência visual atual e nova revisão sobre capturas válidas; a revisão de fontes e a comparação de documentação já terminaram, e o QA de banco foi encerrado.
- Fornecer nome/e-mail do responsável e atualizar `LEGAL_CONTACT` e os trechos pendentes dos três documentos. Definir conservação e atendimento operacional, confirmar condições dos fornecedores antes de publicação definitiva.
- Testes e build oficiais aprovados na retomada. Capturar desktop/mobile claro/escuro para concluir a revisão visual; não confundir as evidências DOM anteriores com screenshots válidas.
- Implementação, testes e este log acompanham um único commit local `feat: adiciona políticas, aceites obrigatórios e página 404`; não executar push automaticamente.
- Após autorização explícita de envio/publicação, publicar frontend/API juntos, aplicar `alembic upgrade head` e validar aceites, recusas, páginas públicas e HTTP 404 em release. Render usa deploy manual; push sozinho não atualiza o site.

## 2026-10-09 — Demonstração pública interativa sem login

### Implementado
- Acesso “Visualizar demonstração” no login e nas telas de carregamento/erro da sessão. `/demo` e suas rotas são resolvidas antes da autenticação; rotas desconhecidas da demonstração retornam estado local de página inexistente.
- Dashboard real reutilizado com exemplos fictícios: dois projetos, monitores online/degradado/offline/pausado/desatualizado/sem leitura, métricas, histórico e tentativas, incidentes abertos/encerrados e falhas de processamento. Filtros, períodos, paginação e temas permanecem disponíveis.
- CRUD de projetos/monitores, pausa/retomada, arquivamento, restauração e simulação explícita de verificações acontecem somente em memória. `/demo/status/vigil-demo` reutiliza a página pública com DTO restrito; navegação interna preserva alterações durante a sessão. Recarregar ou abrir em outra aba restaura os exemplos, sem compartilhar edições.
- Banner persistente identifica dados fictícios. URLs `.invalid`, allowlist de transporte sem fallback de rede, SSE desativado na demonstração e saída sem logout real. Domínio da simulação preserva limiar de falhas, interrupção por pausa, recuperação, versões e duração dos ciclos; jobs técnicos não contam como falhas do endpoint.
- Maestro reutilizou Frontend/Backend/Banco via Maestri. Frontend implementou fontes até atingir limite de uso; Maestro assumiu testes, QA, correções finais e documentação. Backend comprovou fallback SPA `/demo/*` sem autenticação ou conexão DB; nenhuma mudança backend/schema/cloud foi necessária.

### Arquivos principais alterados
- `frontend/src/DemoApp.tsx`, `frontend/src/demo.ts`, `frontend/src/transport.tsx`
- `frontend/src/App.tsx`, `frontend/src/Forms.tsx`, `frontend/src/Observations.tsx`, `frontend/src/CheckTiming.tsx`
- `frontend/src/api.ts`, `frontend/src/live.ts`, `frontend/src/runtimeConfig.ts`, `frontend/src/styles.css`
- `frontend/src/test/demo.test.ts`, `frontend/src/test/DemoApp.test.tsx`
- `.gitignore`, `README.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Provider React injeta cliente em memória explicitamente; cliente real continua padrão fora da demonstração. Não há monkeypatch de fetch no produto, seeds no banco, migrations, execução HTTP ou persistência de entidades em storage. Tema mantém a preferência existente.
- Atualização do runtime real pelo transporte conserva HTTP200 estrito, cache no-store, abort e ausência de revogação de sessão em erro da leitura anônima. Rotas públicas fictícias nunca usam `/status` real.
- Identidade visual existente preservada. Corrigidos controles do banner cortados em390px e link de acesso ao conteúdo encoberto pelo banner. Margem de rolagem usa altura medida do banner e atualização por ResizeObserver, com limpeza de listeners/observer.

### Estado atual
- Retomada para commit: 124/124 testes oficiais Vitest passaram, incluindo os oito casos da demonstração; build TypeScript/Vite aprovado (47 módulos, JS `index-BK3m_EYn.js`, CSS `index-CyatHwCA.css`). O bloqueio de spawn da sessão original foi resolvido com execução aprovada fora do sandbox. Nenhuma publicação ou envio remoto nesta retomada.
- Typecheck e bundle direto esbuild CLI passaram. Ensaios executáveis das fontes finais em Node/React/jsdom:38 assertions,0chamadas de fetch/API,0SSE e cookies intactos; CRUD/reset/isolamento/public DTO/paginação/limiar/pausa/recuperação/versões/tempos/rotas/status/retorno verificados. Evidência `.cache/verification/demo-node-assertions.tsx` e relatório `.cache/verification/demo-proof-20261009.json`.
- QA em portal real `Vigil Demo`, servidor isolado127.0.0.1:5181: primeira simulação gerou HTTP200 no histórico; criação/pausa/arquivamento de monitor fictício passaram e log de pedidos API permaneceu vazio. Desktop1440/mobile390 claro/escuro, status pública e formulário inspecionados. Capturas `.impeccable/review/` são ignoradas no Git. Bootstrap/contraste de tema:3 testes Node passaram.
- Na sessão original, Vitest e Vite build foram bloqueados na inicialização por spawn EPERM; na retomada, os oito casos novos e toda a suíte oficial passaram. A verificação de release em Linux continua prevista no workflow verify-web.
- Revisão Impeccable independente preservou identidade; achado de acessibilidade corrigido e pontuado como resolvido/ship no escopo da correção. Portal inativo não fornece foco real de teclado: aparência de foco foi emulada somente nas capturas, com remoção do estilo QA; ativação DOM nativa do link confirmou hash/foco no destino e topo209px contra banner193px no celular. Navegação real por teclado ainda deve ser validada em navegador ativo.
- Documenter independente comparou fontes/capturas com `frontend/PRODUCT.md`, `frontend/DESIGN.md` e `frontend/.impeccable/design.json`: extensão mantém o sistema. Arquivos de design preservados; divergências prévias de pipeline, tema e borda de campo foram relatadas, sem reparo incidental.
- Recurso somente local, ainda não publicado no Render. Agenda/jitter/CheckTiming integrada no commit local `8ae32f8`; a demonstração acompanha implementação, testes e este registro em sua própria unidade. Escrita Git liberada pela revisão automática na retomada; nenhum push/deploy realizado.

### Próximos passos
- Obter pedido explícito antes de enviar os commits locais de agenda/jitter/UX e demonstração ao remoto. Testes e registros acompanham cada implementação; não há commit separado de testes ou atualização automática do log.
- Testes e build oficiais aprovados na retomada; validar teclado ativo no dashboard/status e abrir `/demo`/`/demo/status/vigil-demo` por acesso direto e reload em release. Executar verify-web em Linux após envio autorizado antes de publicar.
- Após envio/publicação autorizados, conferir CTA e ausência de pedidos `/api/v1`/SSE durante uso da demonstração; compartilhar o link online `/demo` com recrutadores. Preview local usa5181 e não altera o QA sintético anterior em5173.

## 2026-10-09 — Agenda externa e diagnóstico de endpoints sem medição

### Implementado
- Maestro coordenou Frontend, Backend e Banco de Dados. A investigação confirmou ausência de disparos do executor por horas: eventos GitHub schedule às05:17UTC e12:02UTC, intervalo6h45, apesar do cron15 configurado. Criação já deixa `next_check_at` imediatamente devido; nenhum defeito de persistência ou polling REST/SSE foi demonstrado.
- Criado e ativado Worker Cloudflare Free `vigil-check-schedule`, cron UTC `2,17,32,47 * * * *`, em2026-10-09T12:06:26Z. Dispara exclusivamente o workflow existente `free-checks.yml/main` por HTTPS verificado; token fine-grained somente `fmvini/Vigil`, Actions write/Metadata read, armazenado como secret de produção. workers.dev e previews desativados, logs habilitados, sem DB/URL de monitor/rota HTTP. Prova completa da agenda regular concluída às12:32UTC, descrita abaixo.
- Backend local mitiga jitter pequeno: consulta futuro elegível com relógio DB único e ausência de job aberto por monitor; espera acumulada<=30s somente sem trabalho ativo/pendente, abaixo do cap e com restante estrito>delay+51s após consulta. Fecha sessão antes de dormir e revalida admissão real ao acordar. Não antecipa900s nem altera schema, leases ou orçamento90s.
- Frontend local mostra agenda via runtime-config no dashboard/status pública, primeira medição e pausa; explica que Atualizar consulta resultados salvos e que atraso não equivale a offline. REST30s existente foi preservado.
- Preparado workflow manual `verify-web.yml`, Node24/Linux, para testes oficiais frontend/build e contrato Worker sem secrets ou checks reais; execução ainda depende de envio autorizado ao repositório.

### Arquivos principais alterados
- `backend/app/monitoring/batch.py`, `backend/tests/test_batch.py`, `backend/tests/test_batch_jitter.py`
- `frontend/src/CheckTiming.tsx`, `frontend/src/App.tsx`, `frontend/src/Observations.tsx`, `frontend/src/runtimeConfig.ts`, `frontend/src/styles.css`, `frontend/src/test/CheckTiming.test.tsx`
- `infra/check-schedule/worker.mjs`, `infra/check-schedule/worker.test.mjs`, `infra/check-schedule/wrangler.jsonc`, `infra/check-schedule/README.md`
- `.github/workflows/verify-web.yml`
- `README.md`, `docs/FREE_CLOUD.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Agenda Cloudflare15min substitui dependência exclusiva do GitHub schedule; schedule GitHub permanece ativo em paralelo como reserva e pode acrescentar rodadas aos96 disparos/dia Cloudflare. Mesma concorrência/gates/Docker/firewall/TLS; mínimo DB preservado. API web continua sem execução HTTP arbitrária. Recibo HTTP200/API2026-03-10 identifica aceitação pelo workflow_run_id, não execução/check concluídos; timeout10s e sem retry ambíguo.
- Não adotado polling5min:288 rodadas/dia versus96, acesso DB poderia impedir suspensão Neon5min e elevar CUh. Não alterados next_check_at, mínimo900, heartbeat, migrations ou plano pago. Jitter>30s/preflight lento e espera GitHub continuam sem SLA15min.
- Configuração versionada do Worker desativada por padrão; produção ativada explicitamente. Token expira em2027-01-07; renovar antes, sem registrar valor no Git/logs/argumentos.
- Primeira invocação real12:17UTC falhou antes de criar run GitHub com unavailable. Fonte primária workerd `http.c++` demonstrou que redirect=error é rejeitado na construção do Request, apesar da documentação Web padrão listar o valor. Corrigido para manual+rejeição estrita de qualquer status!=200, sem seguir Location. Wrapper globalThis.fetch e diagnóstico de fase/classe permitida/abort/tempo/status foram acrescentados; nenhum detalhe de transporte/segredo exposto. Módulo corrigido publicado12:22UTC. Cron extra de teste12:24 não teve invocação observada durante propagação; removido12:33UTC. Readback final tem somente o cron15 regular.

### Estado atual
- Retomada para integração local: 69 testes de batch/jitter e Ruff passaram; contrato Worker 10/10 aprovado. Unidade isolada de agenda aprovada em 116 testes oficiais Vitest, TypeScript e build Vite. Revisão por unidade preserva testes e documentação com a implementação; nenhum push/deploy nesta retomada.
- Recuperação real em release existente `e68ba02`: [run37925806514](https://github.com/fmvini/Vigil/actions/runs/37925806514) manual completed/success40s; monitor QA próprio HTTPS200/76ms às11:47:00UTC, histórico/métricas/status pública e dashboard confirmados. Agregado Neon antes:1 ativo/0sem resultados/1devido/último05:17:43; depois:2ativos/0sem resultados/0devidos/último11:47:02. O monitor ativo preexistente também voltou a receber medição. Nenhuma URL/dado privado do usuário inspecionado.
- [Run37927459762](https://github.com/fmvini/Vigil/actions/runs/37927459762) nativo schedule completed/success às12:02UTC, antes da ativação Cloudflare; QA recebeu segundo check200/76ms às12:02:54. Não comprova o novo Cron Trigger. Evidência inicial `.cache/verification/cloud-endpoint-recovery-20261009.json`.
- Prova real do novo cron regular: Cloudflare scheduled às12:32:08UTC, versão Worker `7ef7fb10-4853-410b-8e7f-16f937a1b63d`, recibo dispatch_accepted/run37930675185. [Run37930675185](https://github.com/fmvini/Vigil/actions/runs/37930675185) workflow_dispatch emmain/c3ef052, completed/success12:32:55UTC,45s. Novo monitor QA criado12:14UTC/sem dados recebeu primeira medição automaticamente12:32:40UTC: HTTPS200/59,94ms, uma tentativa/amostra, saúde online. Monitor QA anterior também recebeu check às12:32:41; dashboard reconciliou via REST e status pública mostrava dois fresh/online. Não prova SLA ou cadência futura; backend/UI novos ainda estão locais.
- Agregado Neon após cron:3 ativos/0sem resultados/0devidos/último12:32:43, confirmando nova medição também no monitor preexistente. Projeto QA arquivado com guardas de conta própria/marker/IDs dos dois monitores:archive204, privado/público404, projetos próprios0, logout204/me401 às12:35UTC. Conta/histórico retidos, nenhum purge. Portal online devolvido ao login anônimo. Evidências `.cache/verification/cloud-check-schedule-proof-20261009.json`, `cloud-check-schedule-cleanup-20261009.json` e `cloud-check-schedule-20261009.json`.
- Readback Neon após limpeza12:36UTC:1ativo/0sem resultados/0devidos/último12:32:43, recurso preexistente preservado. Readback Cloudflare:apenas cron15, enabled=true, secret_text presente, workers.dev/previews=false. Captura live de logs encerrada; portais preservados.
- Backend129 passed/14 skipped, Ruff e diff-check; revisão Banco68 passed independente. Regressão central87 passed/21 skipped em27,14s (`.cache/verification/maestro-endpoint-regression.xml`). Ensaios PG/Redis físicos indisponíveis; PG55432 recusou conexão e não foi reiniciado. Worker final10/10 Node, incluindo receiver/diagnóstico/redirect3xx sem follow; revisão Backend aprovada. Upload real Cloudflare validou módulo e readback confirmou secret/cron/gate true/rotas desativadas. Etag corrigido b396a7929b9c6c8c05be5132b7fc0ed592dca9145cd59b87e7383eeced278ea2.
- Frontend typecheck passou;21 assertions Node domínio/runtime/SSR e bundle esbuild CLI passaram. QA sintético em navegador: REST sem reload reconciliou primeira medição/métricas, pausa/histórico,1440/390 claro/escuro sem overflow. Relatório com hashes `.cache/verification/check-timing-portal/report.json`. Vitest e Vite build oficiais bloqueados na inicialização por spawn EPERM, zero testes oficiais executados nesta sessão; approval never impede escalada. `frontend/dist` antigo não prova fontes novas. Preview5173 pertence ao QA sintético, não à API cloud.
- Backend/UI novos ainda não publicados; Render continua `e68ba02`/auto deploy Off. Staging explícito falhou com Permission denied ao criar `.git/index.lock`; sandbox só permite leitura de `.git` e approval never impede escalada. Sem stage/commit/push, working tree preservado. Docker Linux local também indisponível (pipe dockerDesktopLinuxEngine ausente). Repositório remoto não foi alterado nesta etapa. Infra Cloudflare corrigida e validada online; recursos QA arquivados e sessão encerrada.

### Próximos passos
- Acompanhar próximos cron15 Cloudflare e correlacionar recibos/runner/checks, sem transformar esta primeira prova em SLA. Próxima rodada após ensaio12:47UTC. Preservar recursos reais e históricos; QA já encerrado.
- Enviar o commit local da agenda somente após pedido explícito de push conforme AGENTS.md; esta unidade contém implementação, testes e documentação. As restrições de Git e spawn descritas acima ocorreram na sessão original; testes/build foram liberados pela revisão automática na retomada.
- Após push autorizado, executar workflow manual verify-web e exigir npm test/npm run build oficiais aprovados antes da publicação; publicar manualmente Render Free e validar novo commit/bundle/runtime/dashboard/status pública. Acompanhar cadência/backlog/quotas e renovar o token antes de2027-01-07.

## 2026-10-08 — MVP com modo escuro publicado e verificado

### Implementado
- Após pedido explícito do usuário, enviados `e43e1d3` (entradas API), `d32bd04` (modo escuro) e `e68ba02` (build limpo) para `origin/main`; publicado `e68ba02` no Render Free. Nenhum plano pago ou mudança de quotas/gates cloud.
- Verificação real da nova versão: cadastro/login/projeto/monitor próprios, validações inválidas422 sem mutação parcial, check HTTPS200 persistido e visível online no dashboard escuro e na status pública clara/escura.

### Arquivos principais alterados
- `README.md`, `docs/FREE_CLOUD.md`, `docs/PROJECT_SCOPE.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Deploy manual preserva auto deploy Off. Build inicial falhou por dependência Node ausente, corrigida em unidade fix com instalação limpa verificada; nenhum teste foi excluído da compilação.
- Evidências sintéticas de tema e prova real cloud são distintas. Nenhuma medição foi fabricada para preencher a aplicação.

### Estado atual
- Render deploy `dep-db3qv0d9fdbs73essqpg` Live/Free em `e68ba02`; build Linux passou. Live/ready200, banco ok, runtime900/900, `/theme.js`200 e bundle oficial `index-MUkzQPic.js`/`index-RgnfoF_B.css`. Tema escuro salvo sobreviveu reload; claro/escuro funcionaram na página pública, sem overflow desktop/celular.
- [Runner37797297573](https://github.com/fmvini/Vigil/actions/runs/37797297573) em `e68ba02`: checks32s, uma tentativa/um job completed, backlog0/status ok/cleanup confirmed. HTTPS200 às15:01:57UTC, latência107ms; histórico1/métricas1/uptime por amostras100%. Não representa cobertura contínua.
- Recurso QA arquivado com guardas de owner/marker/monitor; privado/público404, lista própria0, logout204 e sessão401. Conta/histórico retidos; nenhum purge. Portal devolvido ao login anônimo, preferência Sistema e largura desktop. Evidências `.cache/verification/cloud-theme-release-20261008.json` e `theme-cloud-release/`.
- Goal de MVP online com modo escuro atingido. Build/typecheck/Vitest111 e Edge16 passaram; auditorias Backend324 e Banco205 registradas abaixo. Atrasos de horas da agenda gratuita continuam conhecidos; não há SLA de15min. Ensaios físicos Docker/PG17/TLS desta sessão permanecem limitados como registrado.

### Próximos passos
- Acompanhar cadência/backlog/quotas reais; se o produto exigir checks pontuais, selecionar executor confiável antes de prometer frequência.
- Preservar PG local em execução e conferir posse/lock antes de restart, por ausência do pidfile. Ensaiar PG17/TLS sem interceptação e campanha UI v3 em ambiente apropriado quando retomados.

## 2026-10-08 — Tipos Node explícitos no build limpo

### Implementado
- Declarado `@types/node`24.19.1 como dependência de desenvolvimento e incluído `node` nos tipos do TypeScript. Lockfile inclui a dependência transitiva `undici-types`7.24.6.
- Corrigida falha do build Render após instalação limpa: fixtures de tema usam `node:fs`, `node:path` e `process`; os tipos estavam disponíveis somente por pacote instalado em uma pasta ancestral local.

### Arquivos principais alterados
- `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Testes continuam incluídos na compilação; nenhum erro de tipo foi ocultado e nenhuma fonte de aplicação mudou.
- Download local inicialmente falhou por cadeia TLS. `NODE_USE_SYSTEM_CA=1` foi usado apenas no processo npm para ler certificados já confiados pelo Windows e restaurado depois; registry e verificação TLS preservados. Render usa seu ambiente Linux normal.

### Estado atual
- `npm ci` limpo passou,173 pacotes em3s. Build oficial43 módulos, typecheck e Vitest111/111 em11 arquivos passaram (16,87s); tipos resolvem de `frontend/node_modules/@types/node`, sem depender da pasta ancestral. Bundle preservado `index-MUkzQPic.js`/`index-RgnfoF_B.css`. Evidência `.cache/verification/node-types-clean-build-report.json`. Primeiro deploy `dep-db3qqn59fdbs73esfp50` falhou em TS2307/TS2591; release anterior `6e6c87b` permanece online até nova publicação.

### Próximos passos
- Integrar a correção e repetir publicação autorizada no Render Free. Conferir novo release, probes públicos e preferência de tema na nuvem.

## 2026-10-08 — Modo escuro e revisão online do MVP

### Implementado
- Tema Sistema por padrão, com seleção Claro/Escuro/Sistema no login, dashboard, status pública e estados de abertura/erro. Preferência `vigil.theme` persistida; bootstrap bloqueante aplica o tema antes do React. Mudanças de sistema e storage são acompanhadas; storage indisponível mantém a escolha no documento.
- Tokens claros/escuros cobrem marca, campos, botões, alertas, saúde/qualidade, tabelas, histórico, incidentes e falhas do processamento. SVG inline preserva a geometria da marca usando a cor do tema. Bordas de campo claro ajustadas para contraste mínimo3:1.
- Revisão de documentação remove afirmações obsoletas de que não existia implementação e registra a frequência cloud realmente observada.

### Arquivos principais alterados
- `frontend/index.html`, `frontend/package.json`, `frontend/public/theme.js`
- `frontend/src/ThemeControl.tsx`, `frontend/src/App.tsx`, `frontend/src/Brand.tsx`, `frontend/src/Forms.tsx`, `frontend/src/Observations.tsx`, `frontend/src/styles.css`
- `frontend/src/test/ThemeControl.test.tsx`, `frontend/scripts/theme-unit.mjs`, `frontend/scripts/theme-smoke.mjs`
- `README.md`, `docs/PROJECT_SCOPE.md`, `docs/FREE_CLOUD.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Preferência pertence ao navegador, sem mudança de API/schema ou dependências. Tema pode ser escolhido durante edição/mutação. Sem medições fabricadas para preencher a UI.
- Subprocessos inicialmente bloqueados por EPERM foram liberados pela revisão automática de `require_escalated`. O preview5173 agora serve o `frontend/dist` gerado pelo build oficial Vite; o bundle CLI temporário anterior não é usado como prova de produção.
- Testes e log pertencem às unidades correspondentes de feat/fix; não haverá commit exclusivo de testes ou registro automático.

### Estado atual
- Build oficial `npm run build` passou (TypeScript/Vite7.3.6,43 módulos); preview5173 serve o `frontend/dist` resultante. Vitest oficial:11 arquivos/111 testes passados, incluindo16 de ThemeControl. Typecheck e Node3/3 passaram: bootstrap,28 pares de texto por tema>=4,5:1 e bordas de campo>=3:1. Fontes finais congeladas.
- QA real via portais: cadastro/login/projeto/monitor próprios; login/dashboard/formulário/status pública em1440/390, claro/escuro, sem overflow e seletor44px. Confirmado bundle final, borda clara efetiva, preferência persistida e Sistema seguindo OS dark. Capturas/DOM em `.cache/verification/theme-portal/`; relatório `theme-portal-report.json`. Projeto arquivado, lista própria vazia, status pública404 e logout; conta dedicada retida, sem purge.
- Playwright Edge oficial passou nas16 combinações de login/dashboard/formulário/status pública,1440/390 e claro/escuro, sem overflow ou erro JS. Nome acessível exato Tema, alvo44px e foco visível por teclado comprovados; preferência antes do primeiro conteúdo/reload, mudanças de sistema e storage entre abas passaram. Métricas/série, incidentes e jobs populados usam fixtures declaradas, sem comprovar integração backend/cloud. Evidência `.cache/verification/theme-official-smoke/report.json` e PNGs; limitações EPERM anteriores resolvidas nesta retomada. O nome acessível composto do seletor encontrado no ensaio foi corrigido com label associado separado.
- Cloud existente validada novamente em `6e6c87b`: cadastro201/login200/projeto201/monitor201; [runner manual37792782610](https://github.com/fmvini/Vigil/actions/runs/37792782610) success40s, um job completed/uma tentativa/backlog0/cleanup confirmed. HTTPS200 às14:29:15UTC, latência82ms, histórico com1 check e métricas com1 amostra; dashboard/status pública online. `.cache/verification/cloud-mvp-20261008.json`. Archive204, privado/público404, projetos0, logout204/me401 (`cloud-mvp-20261008-cleanup.json`). Conta/histórico de QA retidos conforme domínio/TTL.
- Agenda schedule confirmada, mas entre duas rodadas recentes decorreram cerca de7h23; não há garantia de15min. Neon Free mostrou0,42CUh/32,57MB; nenhum plano pago contratado.
- Escrita Git liberada pela revisão automática: correção API integrada no commit local `e43e1d3`, sem push. Tema validado no bundle oficial `index-MUkzQPic.js`/`index-RgnfoF_B.css`, ainda sem publicação cloud. API8000 corrigida e ready200; preview5173 ativo. PG local mestrePID14956 saudável, mas `postmaster.pid` ausente após tentativas simultâneas de startup; preservar o processo e conferir posse antes de qualquer novo restart.

### Próximos passos
- Obter pedido explícito de push conforme AGENTS.md, enviar os commits e publicar o release revisado no Render Free, com auto deploy Off. Confirmar novo commit/bundle, `/theme.js`, live/ready/runtime e preferência no navegador público. Não reutilizar release antigo como prova do modo escuro online.
- Acompanhar atrasos/quotas/backlog da nuvem. Para monitoramento pontual, reavaliar executor agendado fora do GitHub best-effort; nenhum SLA foi acrescentado. Ensaios físicos Docker/PG17/TLS sem Avast continuam próximos passos de operação.

## 2026-10-08 — Validação de entradas e auditoria do MVP

### Implementado
- Corrigido PATCH de projeto com `name: null`: retorna 422 sanitizado, sem alterar outros campos, em vez de 500.
- Aplicado teto BIGINT a offsets de projetos, monitores, checks e incidentes privados/públicos, consistente com a lista de jobs.
- Maestro coordenou os agentes existentes Backend, Frontend e Banco de Dados; staging e commits permanecem centralizados, com testes junto da implementação.

### Arquivos principais alterados
- `backend/app/api/schemas.py`, `backend/app/api/resources.py`, `backend/app/api/observations.py`
- `backend/tests/test_api_input_boundaries.py`, `docs/API.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Entradas inválidas são rejeitadas antes da mutação ou binding SQL; o limite de paginação não promete consultas baratas para offsets elevados.
- Nenhum bug de persistência demonstrado; não foram necessárias novas migrations ou alterações nos contratos de banco.

### Estado atual
- Backend: 324 passed, 5 skips de variantes incompatíveis SQLite/PG e 9 casos PG17 deselecionados em PG18.6; `.cache/verification/backend-mvp-compatible-pg18.xml`. Batch sintético: 3 passed/3 skips SQLite em `backend-cloud-batch-pg18.xml`. Ruff e diff-check passaram.
- Banco: 205 passed/zero skips em 68,65s (`db-audit-20261008-pg18.xml`), mais 3 casos de cleanup próprios. Catálogo/head public preservados; migrations/head 0002 e constraints, isolamento, rollback, leases e retenção verificados. Três schemas observados durante a suíte têm autoria incerta e foram preservados.
- Runtime local PG18/55432 e API8000 ativos, gates externos desligados e Redis desabilitado nesta sessão. API live/ready 200; runtime60/null. Docker indisponível; guardas PG17 preservadas. Dois testes TLS físicos foram interceptados pelo Avast no loopback, com certificado distinto da fixture; TLS não foi relaxado. Regressão runtime compatível: 124 passed/49 skips/2 casos TLS deselecionados.
- Cloud existente: HTTPS live/ready200, runtime900/900, Render Live no release `6e6c87b`. Agenda automática confirmada: [run37785218408](https://github.com/fmvini/Vigil/actions/runs/37785218408), evento schedule em `fc38a58`, success32s, completed=true/status ok/cleanup confirmed; nenhum monitor elegível ou job nessa rodada. Isso comprova execução automática, não nova medição de um alvo nem cadência garantida.

### Próximos passos
- Finalizar e validar modo escuro, com registro próprio junto da feature. Recompilar pelo fluxo oficial Vite antes da nova publicação; Node/esbuild com pipes apresenta EPERM neste ambiente.
- Publicar os commits revisados no Render após pedido explícito de envio remoto exigido pelo AGENTS.md; confirmar release, UI e probes públicos da nova versão.
- Acompanhar atrasos da agenda e quotas cloud em uso real; repetir ensaios físicos em ambiente Docker/PG17/TLS sem interceptação quando disponível.

## 2026-10-06 — Publicação gratuita no Render e execução remota

### Implementado
- Após autorização explícita de push, enviada a implementação `6e6c87b` para
  `fmvini/Vigil/main` e publicado https://vigil-4q06.onrender.com no Render Free.
- Neon exclusivo, TLS verificado e schema vigil/head 0002 reutilizados pelo web
  e pelo runner GitHub; API sem Redis, runtime-config 900/900 e novo bundle ativos.
- Agenda habilitada por `VIGIL_FREE_CHECKS_ENABLED=true`; execução manual remota
  concluída com check HTTPS 200 persistido e visível como online na página.
- API local 8000 reiniciada com fontes atuais, PG18/55432 preservado; novo bundle
  servido em 5173, runtime-config 60/null e gates false. Redis desabilitado nesta sessão
  local explicitamente, sem mudar o default do código. Containers QA removidos
  após conferir IDs/labels próprios; nenhum recurso de outro projeto foi removido.
- Projeto QA cloud arquivado pela API, GET posterior 404 e lista vazia; logout
  confirmado, portal público novamente no login. Conta/histórico retidos conforme
  domínio e TTL, sem purge nem remoção de dados locais.
- Pasta temporária `.cache/cloud-private` removida após validar o caminho absoluto;
  credenciais cloud não permanecem nesses arquivos nem nos containers QA removidos.

### Arquivos principais alterados
- `README.md`
- `docs/FREE_CLOUD.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Render Hobby/Free sem cartão, cobrança atual/projetada USD 0.00; auto deploy Off.
  Publicação não depende do computador local ficar ligado.
- Usuário deve criar conta e monitores na nuvem, sem importar seus dados locais.
  Nenhum upgrade/plano pago foi contratado; cotas e atrasos continuam aplicáveis.

### Estado atual
- Render serviço `srv-db2j4eei0phs738oer30`, deploy `dep-db2j4emi0phs738oese0`,
  implementação `6e6c87b` Live. HTTPS live/ready 200, runtime-config 900/900,
  assets index-Q0hhzUNE.js conferidos. Desktop/mobile sem overflow.
- GitHub manual [37505959414](https://github.com/fmvini/Vigil/actions/runs/37505959414):
  success em 40s, attempts 1/jobs_admitted 1/completed 1, backlog 0, status ok,
  deadline false, cleanup confirmed. HTTPS example.com retornou 200, último check
  2026-10-06T17:45:36.478157Z, latência 61ms, saúde online no produto.
  Evidência privada `.cache/verification/cloud-github-manual-report.json`.
- Rodada anterior 37505503548 skipped com variável false, não usada como prova.
- Até 18:05 UTC não apareceu evento schedule. Workflow active na default branch main
  e variável true confirmados pela API GitHub; primeira execução automática ainda
  sem prova observada. Sem SLA e sem promessa de checks 60s neste perfil.

### Próximos passos
- Confirmar primeira execução schedule e registrar resultado/cleanup real.
- Após uso real, acompanhar cotas Neon/Render e backlog; agenda pode atrasar e
  GitHub pode desativá-la após 60 dias sem atividade. Campanha física UI v3 segue pendente.

## 2026-10-06 — Perfil gratuito online com checks em lotes

### Implementado
- Web Docker recompila React e serve SPA/API na mesma origem; bootstrap explícito
  cria somente schema privado vigil e aplica Alembic antes de iniciar a API.
- API sem Redis opt-in, runtime-config anônimo e formulário com mínimo dinâmico.
  Perfil cloud usa 900/900 segundos; defaults locais 60/null preservados.
- Runner one-shot reutiliza claim/HTTP/finalização duráveis, backlog e retries, sem
  broker Redis. Workflow público/manual/agendado 15min usa Docker protegido e relay
  TCP com hostname original e TLS verificado. Recursos próprios recebem cleanup validado.
- Factory TLS/schema/pool e Alembic privado integrados. SET SESSION no connect evita
  search_path de startup descartado pelo Neon; sem fallback public/DDL na factory.
- Timeout de conexão cloud10s/local3s; relatórios distinguem fase e deadline global.
  Retenção até10s por batch dentro do prazo90s, sem alterar TTL ou statement/lock limits.

### Arquivos principais alterados
- `backend/app/config.py`, `backend/app/main.py`, `backend/app/web.py`, `backend/app/api/runtime.py`
- `backend/app/api/resources.py`, `backend/app/services/resources.py`, `backend/app/domain/monitors.py`
- `backend/app/monitoring/batch.py`, `backend/app/monitoring/run.py`, `backend/app/monitoring/tasks.py`, `backend/app/monitoring/status.py`
- `backend/app/db/session.py`, `backend/migrations/env.py`, `backend/app/services/check_jobs.py`, `backend/app/services/retention.py`
- `backend/tests/test_batch.py`, `backend/tests/test_batch_postgresql.py`, `backend/tests/test_db_session.py`, `backend/tests/test_db_fresh_slot.py`, `backend/tests/test_pipeline_db.py`
- `backend/tests/test_runtime_config.py`, `backend/tests/test_web.py`, `backend/tests/test_retention.py`
- `frontend/src/runtimeConfig.ts`, `frontend/src/Forms.tsx`, `frontend/src/domain.ts`, `frontend/src/test/RuntimeConfig.test.tsx`, `frontend/src/test/App.test.tsx`, `frontend/src/test/Observations.test.tsx`, `frontend/src/test/fixtures.ts`
- `infra/free-cloud/Dockerfile`, `infra/free-cloud/pg_relay.py`, `infra/worker/egress.py`, `.dockerignore`, `render.yaml`, `.github/workflows/free-checks.yml`
- `scripts/free_cloud_start.py`, `scripts/free_cloud_checks.py`, `scripts/tests/test_free_cloud.py`, `docs/FREE_CLOUD.md`, `docs/API.md`, `README.md`, `backend/app/db/IMPLEMENTATION.md`

### Decisões técnicas
- Usuário escolheu Neon separado, gratuito, checks15min. Supabase Vault/VFitness e
  bancos locais preservados; não transferir dados locais automaticamente.
- Projeto Neon exclusivo vigil/lingering-water-00111721, Oregon, compute fixo0.25CU
  e scale-to-zero5min. Schema vigil no head0002; clientTLS1.3/hostname verificado.
- Render Free single instance, healthCheckPath live para evitar manter compute DB
  acordado por probes; readiness explícita no deploy. API gatesfalse, runner true/true.
- Cron best-effort sem SLA/replay de checks omitidos. Fresh slot usa clock real DB
  após locks; legado abaixo900 legível e excluído da agenda até ajuste explícito.
- Workflow somente default branch público não fork, sem PRs, checkout fixado e
  runner padrão. Secrets servidor; nenhum DSN/cookie/senha em Git ou frontend.

### Estado atual
- Banco:138 passed/zero skips em PG18 UUID autorizados, antes do ajuste de connect;
  `.cache/verification/db-cloud-neon-contracts-pg18-final.xml`, cleanup/catalog public preservados.
- Backend:183 passed/76 skips sem URLs na regressão inicial; PG18 synthetic22 passed/3
  skips SQLite-only, `.cache/verification/backend-cloud-pg18.xml`.
- Maestro final:137 passed/zero skips de schema/timeout/tooling/egress em4.87s;
  `.cache/verification/cloud-final-boundaries.xml`. API/batch/readiness83 passed/7
  variantes incompatíveis SQLite/PG skipped em180.26s; `cloud-final-api-pg18.xml`.
- Frontend:build Linux completo e Vitest real10 arquivos/95 testes passed,6.61s.
  Novo bundle index-Q0hhzUNE.js, sem reutilizar dist histórico; formulário900/900
  em1440/390 sem overflow, cópia15min e mínimo900 conferidos no portal.
- Firewall físico na imagem final:18 bloqueios, controles negativos reais, IPv4/IPv6,
  TLS/SNI/CA/hostname e NDP passed; `.cache/egress-qa/a58fbf4f57d348c0bbaa83f9a4c93fed/report.json`, cleanup confirmado.
- Neon real:bootstrap/head0002, readiness200, cadastro/login/monitor QA próprio,
  batch com1 completed/0 backlog, cleanup confirmado. HTTP example.com retornou200,
  latência74.65ms, saúde online e last_checked_at2026-10-06T17:32:03.111087Z.
  Check HTTPS anterior gravou tls_error da inspeção local, sem relaxar verificação.
- Preview QA em5180(prod)/5181(dev somente para browser local) usa banco Neon
  separado; runtime local anterior8000/5173 mantido. Ruff/diff-check aprovados.
- Serviço Render ainda não publicado e agenda GitHub desativada por variável false;
  aguarda código remoto e validação pública. Conta/projeto QA ainda existem nesta etapa.
  Sem nova execução do verify completo RequireIntegration, guardasPG17 preservadas.

### Próximos passos
- Após commit local da unidade, obter pedido explícito de push exigido pelo AGENTS;
  enviar main, publicar Render Free já preparado e validar URL HTTPS live/ready/UI.
- Validar workflow manual no GitHub contra Neon e só então ativar variável true;
  conferir rodada agendada e limites/cotas, sem adicionar cartão/upgrade.
- Arquivar projeto QA próprio e logout, remover containers QA identificados e arquivos
  privados temporários; preservar banco e credenciais exclusivamente nos secrets.
- Registrar URL/provas públicas efetivas; não chamar online/agenda de concluídos
  apenas porque build e runner local passaram.

## 2026-10-06 — Prontidão por migration e execução local

### Implementado
- Readiness exige conectividade e uma única revision Alembic igual ao head dinâmico dos arquivos instalados. Preserva liveness, deadline, cancelamento e503 sanitizado, sem aplicar migrations.
- Adicionado `start-local.ps1 frontend -Preview`, servindo build existente em5173 com proxy/API e configuração nativa Node24, sem bundling/hot reload.
- README/API/OPERATIONS documentam o ambiente local e procedimentos de reinício. Provas e regressões acompanham a correção.

### Arquivos principais alterados
- `backend/app/main.py`, `backend/app/readiness.py`
- `backend/tests/test_api_health.py`, `backend/tests/test_readiness.py`
- `scripts/start-local.ps1`, `README.md`, `docs/API.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Head resolvido via ScriptDirectory ancorado no backend, sem hardcode/CWD/conexão no startup. Probe usa apenasSELECT e respeita search_path. Confirma versão declarada, não integridade global do schema.
- Somente SQLite explicitamente injetado em testes dispensa Alembic; fixtures PG metadata sem alembic_version corretamente retornam503.
- Preview serve dist histórico e52dd02; src/public/package/config não mudaram, mesmos assets da coleta anterior. Sem novo rebuild ou equivalência criptográfica fonte→bundle nesta sessão.
- Runtime usa PostgreSQL18.6 próprio em `.cache/postgresql/data`, porta55432, API8000 e frontend5173; PostgreSQL independente5432 preservado. Redis/scheduler/worker não iniciados e gates de checks externos preservados.

### Estado atual
- Readiness final:31 passed/2 skips exclusivamente SQLite-only em4.87s; `.cache/verification/backend-local-readiness-pg18-final.xml`. Missing/empty/old/unknown/multiple/current exercitados em schemas UUID próprios; cleanup confirmado, public nohead0002 sem DDL/DML dos testes.
- Regressão offline:110 passed/49 skips de integrações semURLs, em28s; `.cache/verification/backend-local-readiness-regression.xml`. Ruff completo, diff-check e AST PowerShell aprovados; Preview iniciado pelo novo comando.
- HTTP live/ready8000 e frontend5173 responderam200; portal Vigil Preview no login. Cadastros/consultas disponíveis, com smoke jobsUI vazio descrito na entrada anterior. Redis ausente limita fanout/pipeline; checks automáticos não estão ativos.
- Build/esbuild e launch Edge restringidos por spawn EPERM; Docker sem daemon disponível. Verify completo obrigatório/campanha v3 não executados.
- Escrita Git antes bloqueada; usuário liberou commits locais e a operação foi autorizada pelo revisor do ambiente. Três unidades concluídas agrupam implementação/testes/docs em feat/fix, sem commit exclusivo de testes/log ou push.

### Próximos passos
- Quando Docker/Edge estiverem disponíveis, executar verify completo obrigatório com dependências isoladas e provas de egress/recovery; manter limites desta sessão registrados.
- Para testar checks externos, preparar Redis e scheduler/worker pelo procedimento existente e validar egress antes de habilitar ambos os gates; next_check_at não demonstra execução ativa.
- Para editar UI, voltar ao Vite normal em ambiente que permita esbuild; recompilar antes de usar Preview sobre novos sources.

## 2026-10-06 — Relatório de latência v3 com replay auditável

### Implementado
- Tooling guarda evidências projetadas de SSE/GET/DOM por atualização e oferece replay offline, sem modificar UI, transporte ou polling do produto.
- Builder exige UUID de projeto como string primitiva; corrigida aceitação de arrays/String encapsulada por coerção regex. Regressões integram a implementação.
- Contratos/documentação registram smoke jobsUI real de leitura do dataset vazio.

### Arquivos principais alterados
- `frontend/scripts/live-latency-observer.mjs`, `frontend/scripts/live-latency-observer-browser.mjs`, `frontend/scripts/live-latency-smoke.mjs`
- `frontend/scripts/live-latency-unit.mjs`, `frontend/scripts/live-latency-replay.mjs`
- `frontend/LIVE_LATENCY_V3_CONTRACT.md`, `frontend/IMPLEMENTATION.md`, `frontend/JOBS_UI_CONTRACT.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Whitelist de campos vincula run/projeto/revisão/nome QA e IDs CDP, mantendo clocks CDP e browser separados e sem copiar credenciais ou payloads privados.
- Replay comprova consistência da evidência projetada, sem autenticação criptográfica, paint, causalidade exclusiva de SSE ou instante exato de commit. Relatório v2 histórico preservado; não fabricar conversão para v3.

### Estado atual
- Sete testes Node passed/zero skips, typecheck/syntax/diff-check aprovados; `frontend/.impeccable/review/live-latency-resume-20261006/unit.tap`. Build/esbuild e launch Edge restringidos por spawn EPERM nesta sessão; aprovações anteriores são históricas.
- Smoke jobsUI real passed:17 consultas200, situações all/exhausted/expired e períodos24h/7d/30d, reload, fechamento40s sem novas leituras, reabertura default. Desktop1440/mobile390 sem overflow e controles44px.
- Owner/projeto QA privados próprios vazios; guardas owner/singleton/marker/zero-monitores passaram. Archive204 seguidoGET404/lista autenticada vazia; logout204/me401. Conta e projeto arquivado retidos pela API, sem purge/seed histórico/gates alterados.
- Evidências/capturas em `frontend/.impeccable/review/live-latency-resume-20261006/`: `jobs-api-real.json` SHA256354C17C44433F11BA8BF6D1F6C71CFC183C7579B4209B0B2E7F6E3D8874DC58C, `jobs-desktop.png`, `jobs-mobile.png`.
- Runtime serviu dist histórico e52dd02, src/public/package/config intactos. Sem novo rebuild ou campanha física v3. Dataset vazio não cobre linhas/paginação/filtro de monitor/teclado nativo/token antigo; ResourceTiming não é trace bruto dos métodos ou SLA.

### Próximos passos
- Executar primeira campanha física v3 em QA exclusivo com Docker/Edge disponíveis, seguida do replay offline; preservar v2 e cleanup.
- Em outra janela QA própria, preencher falhas exhausted/expired e validar filtro de monitor, paginação e teclado com cleanup confirmado.

## 2026-10-06 — Índices de evidência e ensaio de retenção

### Implementado
- Migration 0002 e metadata acrescentam índices parciais em opening_check_id e closing_check_id dos incidentes, corroborados por planos PostgreSQL17 históricos.
- Helper QA captura queries reais de retenção, compara EXPLAIN JSON sem ANALYZE em schema UUID próprio e só marca completed após cleanup bem-sucedido. Regressões acompanham a implementação.

### Arquivos principais alterados
- `backend/app/db/models.py`, `backend/app/db/retention_plan_qa.py`
- `backend/migrations/versions/0002_incident_evidence_indexes.py`
- `backend/tests/test_db_postgresql.py`, `backend/tests/test_db_retention_contract.py`, `backend/tests/test_db_incident_evidence_indexes.py`, `backend/tests/test_db_retention_plan.py`
- `backend/app/db/IMPLEMENTATION.md`, `backend/app/db/RETENTION_QA_CONTRACT.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Índices B-tree parciais preservam FKs, nulabilidade e regras de retenção. CREATE INDEX normal é transacional e bloqueia escritas durante construção; exige janela adequada e acrescenta manutenção/storage.
- Planos estimados não demonstram redução medida de latência ou SLA. Guardas PG17 permanecem; resultados históricos e novas provas PG18 são separados.

### Estado atual
- Histórico PG17:102 passed/zero skips em26.491s; hashes de models/migration/testesPG conferidos. Evidência em `.cache/verification/backend-retention-qa-9e7cf99f9f0f42519af3af1be88f7f8d/`.
- Banco:47 testes offline passed/zero skips em0.65s, incluindo completed/cleanup; `.cache/verification/db-retention-resume-20261006-offline-final.xml`.
- Central:102 passed/zero skips em38.41s com schemas próprios noPG18, incluindo dbpostgresql/schema/contrato/helper/retenção; `.cache/verification/local-pg18-retention.xml`. Nenhuma nova campanha de planos PG17 após o fix de cleanup.
- Banco local vigil/55432 atualizado de0001 para0002 após preflight sem outros clientes e backup `.cache/local-runtime/vigil-before-0002.dump` (138434bytes). Revision e ambos os índices confirmados; schemas temporários ausentes. Serviço independente na5432 preservado.
- Fontes liberadas pelos agentes, Ruff completo e diff-check aprovados. Permissão de commits locais liberada pelo usuário; implementação, testes e documentação integram a mesma unidade, sem push.

### Próximos passos
- Repetir helper/catálogo/retenção em PG17 exclusivo com fontes atuais quando Docker estiver disponível, preservando cleanup e hashes.
- Registrar continuidade das unidades de tooling v3 e execução local em seus commits correspondentes.

## 2026-10-05 — Verificação obrigatória de jobs e provas QA reais

### Implementado
- `verify.ps1 -RequireIntegration` exige testes PostgreSQL de jobs no JUnit; omissão ou skip real recusa a verificação. Skips exclusivos de SQLite continuam permitidos.
- API e seção Falhas do processamento do Vigil concluídas no código integrado anteriormente; contrato documentado como implementado, com projeção sanitizada, filtros e paginação somente leitura.
- Regra de commits atualizada no AGENTS: unidade concluída agrupa implementação/testes/docs, sem commits de testes ou log automáticos.

### Arquivos principais alterados
- `scripts/verify.ps1`, `AGENTS.md`
- `docs/API.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`, `frontend/JOBS_UI_CONTRACT.md`

### Decisões técnicas
- Verificação deve comprovar execução dos jobs PG, além de receber uma URL. Quatro cenários controlados do bloco PowerShell validaram presença, omissão, skip PG e skip SQLite; AST sem erros. Não foi executado o comando verify completo nesta etapa.
- Serviços QA exclusivos usam UUID/labels/IDs, limites, tmpfs e mounts readonly. Docker/Git voltaram a funcionar via revisão de permissões; bloqueios descritos nas entradas anteriores são históricos. Nenhum serviço PG18 ou gate compartilhado foi alterado.
- Campanha de carga e testes migrations/jobs são ensaios distintos: helper usa metadata; migrations reais são exercitadas em fixtures próprias. Nenhum índice especulativo ou alegação de plano/paridade global.

### Estado atual
- Backend QA token `2c11a939f92546d0aeeae1f50bd7dac1`:52 passed/zero skips em5,416s (sete jobsPG, quatro namespacePG, um Redis,40 casos puros/controlados), sete SQLite deselected. Provas RR/RO/UPDATE25006 e COUNT/página durante commit de writer distinto passaram. Migrations:29 passed/zero skips em13,427s; head0001_initial/base, tipos/UTC, constraints, identidade composta, SET NULL das duas evidências e concorrência.
- Banco revisou JUnits, log, hashes e limpeza: schemas/keys vazios antes/depois, sete fontes inalteradas; três containers, rede e imagem QA exclusivos removidos e ausência confirmada. Artefatos privados em `.cache/verification/backend-qa-2c11a939f92546d0aeeae1f50bd7dac1/`.
- Carga Taskiq/PG17/Redis/TLS: baseline100/60s e rajada100/0s com contagens completas, zero erros,13 métricas×100 amostras, commit por PID distinto antes do ACK e cleanup confirmado. Agenda commit→XACK p95:99,31ms baseline/4198,21ms rajada; máximos callbacks/HTTP1/1 e15/4. Relatórios `.cache/pipeline-load/31315bf2092c4c75923cfa9c98769b9b/` e `2d39277258f64df6b1e2a9f5aacb9a86/`. Limite50 não foi saturado; um projeto serializa locks e observadores adicionam overhead. Sem SLA/capacidade sustentada.
- UI jobs:72 Vitest/zero skips, build e seis estados Edge desktop/mobile passaram com API sintética; não prova integração dessa seção com PG real. APIjobs continua usando fixture metadata separada da fixture Alembic; nenhum EXPLAIN/volume de histórico medido.
- Coleta UI/API real `29b74cc0-09f0-406a-a5bf-232df865f8c6`:240 REST+25 PATCH medidos passed/errors0, correlacionando SSE nativo/revisão/GET posterior por requestId CDP/DOM. PATCH-start→DOM p95=264,30ms; SSE→GET p95=216,70ms. Build e52dd02/PG170011/head0001_initial/Redis, owner/projeto privado vazio e gates false; uma API não prova fanout. Cleanup API archive/logout/token antigo confirmado; depois containers e duas redes próprias removidos. API/PG/Redis internos, bridge adicional exclusiva do web para loopback. Dois preflights anteriores de binding foram limpos antes de criar conta. Evidências `.cache/verification/ui-real-e481d12e845740a58c5f8f0833bc2e08/` e `frontend/.impeccable/review/live-latency/<UUID>/report.json`. Quantis nearest-rank, polling mantido, sem tempo exato commit→DOM/SLA.
- Frontend aprovou revisão readonly da coleta real e recalculou todos os quantis/contagens independentemente. O JSONv2 guarda flags/deltas, sem requestIds e timestamps CDP brutos: reconstrução independente de cada pareamento exige mais evidência; a revisão também conferiu fontes do observador. Sem sobreposição periódica observada não significa causalidade exclusiva.

### Próximos passos
- Integrar prova de leitura da seção jobs no navegador contra schema Alembic real em nova janela QA exclusiva; a coleta concluída mede projeto vazio/REST/SSE, com jobs fechado.
- Antes de otimizar histórico ou retenção, executar o contrato de planos PG17 com volume representativo em `backend/app/db/RETENTION_QA_CONTRACT.md`; não inferir ganho dos índices candidatos.
- Executar verify completo obrigatório em janela isolada com todas as dependências; esta etapa não substitui provas de fanout/réplicas/firewall/recovery do restante da suíte.

## 2026-10-05 — Logo de olho e favicons do Vigil

### Implementado
- Marca vetorial de olho aplicada no login, dashboard, abertura de sessão e status pública. Componente Brand compartilha símbolo decorativo e nome textual acessível, preservando destinos dos links.
- Logo com lettering Public Sans Bold em contornos, PNG transparente de 1024px, favicon SVG e ICO de 16/32px, além de ícone de 180px para tela inicial.

### Arquivos principais alterados
- `frontend/src/Brand.tsx`, `frontend/src/App.tsx`, `frontend/src/Forms.tsx`, `frontend/src/Observations.tsx`, `frontend/src/styles.css`
- `frontend/public/brand/vigil-eye.svg`, `frontend/public/brand/vigil-logo.svg`, `frontend/public/brand/vigil-logo.png`, `frontend/public/brand/README.md`, `frontend/public/brand/PUBLIC-SANS-LICENSE.txt`
- `frontend/public/favicon.svg`, `frontend/public/favicon.ico`, `frontend/public/apple-touch-icon.png`, `frontend/index.html`
- `frontend/DESIGN.md`, `frontend/.impeccable/design.json`, `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Olho geométrico mantém verde profundo e tipografia existentes. Favicon em negativo é simplificado para tamanhos pequenos; símbolo estático não comunica saúde ou atividade de monitor.
- SVG da logo é independente de fontes externas; Public Sans já instalada foi convertida em contornos com ferramenta temporária, sem adicionar dependência ao produto. PNG/ICO são renderizações dos SVGs autorais.
- Ícone da aplicação tem alt vazio/aria-hidden para evitar nome duplicado. Links mantêm foco visível e área mínima de 44px, com olho de 36px.

### Estado atual
- Central: 72 Vitest passed/zero skips, TypeScript/Vite build aprovado. Edge154 verificou login/dashboard/status pública em 1440 e 390: seis capturas, assets carregados, sem overflow/erros, nome/destinos/foco preservados e altura de 44px.
- Frontend fez revisão visual read-only das seis montagens e da prancha da identidade, sem bloqueadores. Evidências em `frontend/.impeccable/review/branding/`; ICO decodificado no navegador.
- Essas capturas usam API sintética isolada, sem alegar smoke físico do produto. A seção de jobs também passou nos seis estados desktop/mobile, com `processing-failures/report.json` final aprovado.

### Próximos passos
- Reutilizar os assets e o componente Brand nas próximas superfícies; preservar nome acessível, destinos e área de foco.
- Continuar provas PG17/Redis dos jobs e helper em QA exclusivo; registrar campanha física e limites separadamente.

## 2026-10-05 — Relatório de carga exige tipos inteiros do protocolo

### Implementado
- Corrigida aceitação de booleano/decimal no identificador de versão, limites configurados de concorrência e UID do relatório QA. O runner exige inteiros JSON além dos valores esperados.

### Arquivos principais alterados
- `scripts/pipeline_load_check.py`, `scripts/tests/test_pipeline_load_check.py`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Igualdade numérica do Python não valida o tipo do protocolo: true == 1 e 1.0 == 1. A recusa de tipos incorretos complementa as guardas existentes de contagens, quantis, ordem, identidade e cleanup.
- Versão 1, limites 50/5/50 e UID10001 permanecem; não houve alteração no helper, infraestrutura ou runtime.

### Estado atual
- Sete entradas indevidas reproduzidas antes da correção, em `.cache/verification/load-protocol-types-before.xml`. Depois, 49 testes do runner passaram em 0,14s; Ruff check/format aprovados. JUnit `.cache/verification/load-protocol-types-after.xml`.
- Regressão de guardas de egress/proxy/carga: 95 passed/1 deselected em 0,18s; o caso de diretório temporário foi excluído por restrição de ACL já identificada. JUnit `.cache/verification/load-protocol-guards-regression.xml`; lint completo de scripts/infra aprovado.
- São provas de parsing e guardas com recursos controlados, não campanha física PG17/Redis/TLS. Commit local continua impedido pela escrita em `.git`.

### Próximos passos
- Executar a campanha real com o helper v1 de 13 fases quando o terminal tiver acesso ao Docker; preservar os relatórios e validar cleanup.
- Integrar testes à unidade do runner/fix, sem commit exclusivo de testes.

## 2026-10-05 — Contrato de leitura de falhas do processamento

### Implementado
- Acordado o contrato privado de leitura de jobs exhausted/expired, com filtros, paginação, projeção sanitizada e janela de agenda. API e interface ainda estão em implementação.
- Frontend documentou DTO e léxico estático; Banco revisou população da query, snapshot, autorização e limites dos índices existentes sem alterar persistência.

### Arquivos principais alterados
- `docs/API.md`, `docs/DEVELOPMENT_LOG.md`
- `frontend/JOBS_UI_CONTRACT.md`, `frontend/IMPLEMENTATION.md`
- Fontes em implementação: `backend/app/api/jobs.py`, `backend/app/services/operational_jobs.py`, `backend/app/main.py`.

### Decisões técnicas
- Default all reúne somente exhausted/expired. Pausados entram e arquivados não. A leitura não modifica jobs, saúde ou incidentes e não depende de Redis.
- Autenticação termina antes do snapshot de observação; owner/projeto/monitor, COUNT e itens usam a mesma leitura. Projeção SQL impede carregar configuração privada no DTO; códigos desconhecidos viram null.
- Janela usa scheduled_at, retenção usa finished_at e elegibilidade. Snapshot de uma resposta não estabiliza páginas entre requests; COUNT/OFFSET não têm custo limitado pela quantidade de itens. Nenhuma migration especulativa.
- Recuperação de manifesto QA permanece apenas proposta: não implementar journal/publisher/reseed nesta etapa. Arquivo e PostgreSQL não têm commit atômico conjunto.

### Estado atual
- Contrato confirmado pelos três agentes. Backend implementa API/testes; Frontend implementa componente isolado contra fixture exata, aguardando freeze para revisão integrada. Ainda não há evidência de funcionamento da feature de jobs.
- Central confirmou a baseline das unidades anteriores: 174 passed/5 skips de integrações PG/Redis, mais 7 testes Node sem skips e TypeScript aprovado. JUnit `.cache/verification/contracts-jobs-integration-baseline.xml`. Isso não valida a API nova.
- Regressão central de compatibilidade com o router registrado: 62 passed/3 skips que exigem PG/56 deselected, em 124,38s; JUnit `.cache/verification/api-compatibility-jobs-router.xml`. Banco compilou COUNT/página em dialect PostgreSQL sem conexão, confirmou join inequívoco e oito campos; não é plano ou teste RR/RO real.
- Docker e Git seguem sem acesso de escrita/pipe neste terminal; testes físicos e commits locais continuam pendentes.

### Próximos passos
- Revisar e executar `backend/tests/test_operational_jobs.py` após liberação do Backend; exigir isolamento, fronteiras, whitelist, zero efeitos e provas PG separadas.
- Liberar consumo do DTO congelado ao Frontend; validar componente, mensagens, GET apenas, troca de projeto, teclado e mobile com fixture própria.
- Atualizar esta documentação para implementado somente após os testes correspondentes; executar PG17 RR/RO e smoke físico quando a infraestrutura estiver acessível.

## 2026-10-05 — Filtros de qualidade na lista de monitores

### Implementado
- Seletor Todos/Atualizados/Desatualizados/Sem dados/Pausados combinado com busca de nome/URL, usando freshness atual e clock15s existente; não filtra pela saúde histórica.
- Contagem do snapshot fora de aria-live, reset ao trocar projeto, estados vazios distintos e Limpar filtros com retorno de foco à busca. Pausa/retomada pode retirar item do filtro sem alterar a seleção.

### Arquivos principais alterados
- `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/test/MonitorFilters.test.tsx`
- `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Filtragem local sobre snapshot do projeto, sem API/busca global ou inferência de disponibilidade. Timer existente permite envelhecer dados sem nova resposta HTTP.

### Estado atual
- Frontend entregou64 Vitest passed/zero skips em7,84s, TypeScript/build/whitespace aprovados; seis regressões de filtros.
- Edge154 com build e API sintética próprios passou todas as opções, foco/teclado/reset em1440/390, sem overflow/erros. Controles mobile44px ou mais; relatório `frontend/.impeccable/review/monitor-filters/report.json`. Não é prova do produto8080/PG real.
- Maestro confirmou typecheck e revisão de lógica/reset; unidade liberada sem alterações de auth/polling/API. Commit permanece impedido por Git readonly.

### Próximos passos
- Smoke físico da lista após readiness com owner exclusivo, preservando checks externos desligados.
- Alinhar DTO exato e implementar leitura de falhas operacionais do Vigil em seção separada dos incidentes do alvo, sem retry/mutação.

## 2026-10-05 — Configuração recusa portas de origem inválidas

### Implementado
- Settings valida a porta explícita da origem HTTP(S), rejeita zero/vazia/não numérica/fora do intervalo e sanitiza erros de parsing IPv6. Strings não são normalizadas; defaults e regra HTTPS de produção preservados.

### Arquivos principais alterados
- `backend/app/config.py`, `backend/tests/test_validation.py`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- urlsplit não validava porta sem acessar parsed.port; a validação agora ocorre no startup para impedir configuração de origem inviável.

### Estado atual
- Oito entradas indevidas aceitas antes, com regressão registrada. Central66 passed/zero skips em0,12s; nove negativos e oito positivos novos, incluindo IPv6/portas1/65535. JUnit `.cache/verification/origin-port-central.xml`; Ruff aprovado.
- Nenhum endpoint, DB, gate ou processo foi alterado. Git readonly mantém commit pendente.

### Próximos passos
- Preservar origens explícitas válidas e produção HTTPS na próxima verificação de API.
- Finalizar feature de jobs operacionais readonly em módulo separado, sem introduzir política Redis ou migration especulativa.

## 2026-10-05 — Seed QA recusa diretório inválido antes do banco

### Implementado
- `run_seed` valida/cria o diretório pai do manifesto antes de criar engine, evitando fixture commitada para esse erro determinístico de filesystem.
- Regressão usa pai que é arquivo real e proíbe engine; erro/cancelamento com transações controladas confirma saída/rollback/dispose sem manifesto.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`, `backend/tests/test_db_qa_seed_preflight.py`
- `backend/app/db/IMPLEMENTATION.md`, `backend/app/db/RETENTION_QA_CONTRACT.md`, `docs/DEVELOPMENT_LOG.md`
- `AGENTS.md` registra preferência atual por commits de feat/fix, com testes acompanhando a unidade e sem commit exclusivo de testes.

### Decisões técnicas
- Mudança restrita à ordem; open exclusivo e conteúdo do manifesto preservados. Arquivo/PG não são atômicos: I/O/cancelamento após commit ainda pode deixar owner QA isolado.
- Auditoria estrutural registra que FK de evidência garante existência, enquanto finalize/seed garantem mesmo monitor; não foi encontrado vetor público para fornecer IDs de evidência.

### Estado atual
- Banco entregou38 passed/2 skips PG em0,59s. Central preflight/contratos/schema/validação aninhada30 passed/zero skips em0,50s; JUnit `.cache/verification/seed-preflight-central.xml`, Ruff/whitespace aprovados.
- Nenhum seed real, manifesto anterior, schema/migration/serviço ou PG18/runtime foi alterado. Commit local segue bloqueado pela escrita em `.git`.

### Próximos passos
- Repetir testes reais do seed em schema UUID PG17/migrations próprio, sem renovar manifesto/public existente.
- Manter limite pós-commit explícito; discutir fluxo de publicação do manifesto somente com teste de falhas real e preservação de recursos exclusivos.

## 2026-10-05 — Janelas de observação rejeitam epoch implícito

### Implementado
- Tipo de query compartilhado nas quatro rotas privadas de checks/métricas/incidentes rejeita epoch em segundos/milissegundos antes da coerção Pydantic; preserva ISO, offsets, defaults e regras de janela do serviço.
- Respostas422 mantêm apenas query.from/to e tipo do erro, sem valores/contexto privados.

### Arquivos principais alterados
- `backend/app/api/observations.py`, `backend/tests/test_observations.py`
- `docs/API.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Corrige aceitação silenciosa de formatos fora do contrato ISO, sem alterar DTOs, serviço, banco ou política de queries desconhecidas. Incidentes públicos aceitam somente period/state/limit/offset, sem janela from/to explícita.

### Estado atual
- Duas falhas HTTP reproduzidas antes do fix, com200 para epoch segundos/ms. Central final direcionada16 passed/7 PG skips/22 deselected em15,86s; nove formatos puros e sete casos HTTP/SQLite. JUnit `.cache/verification/window-epoch-central.xml`.
- Backend entregou regressão49 passed/1 skip SQLite snapshot/38 deselected em52,98s. Readiness ASGI controlada confirmou erro/timeout503 sanitizado e propagação/cleanup de cancelamento; não é prova de driver/pool PG.
- Ruff/format/whitespace aprovados; integração PG pendente e commit bloqueado pela sessão Git readonly.

### Próximos passos
- Repetir testes reais PG17 após liberação de infraestrutura; preservar ISO-Z/-03, sanitização e janelas antigas.
- Continuar revisão de API sem introduzir política de rate limiting antes de coordenar contrato/falha Redis e validar integração real.

## 2026-10-05 — Mensagens de autenticação em português

### Implementado
- Login com invalid_credentials mostra orientação genérica ptBR, sem distinguir conta/senha. Erros conhecidos de sessão/CSRF/origin/browser/JSON e fallback401/403 usam mensagens estáticas, sem ecoar message/details do servidor.
- Transporte, ApiError, cookies, callbacks de sessão e contrato do backend preservados.

### Arquivos principais alterados
- `frontend/src/api.ts`, `frontend/src/test/api.test.ts`, `frontend/src/test/AuthErrors.test.tsx`
- `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Tradução usa código estável do backend; login401 não invalida sessão pelo callback reservado às leituras privadas. Outros erros desconhecidos conservam comportamento anterior.

### Estado atual
- Frontend entregou58 Vitest passed em8,14s e TypeScript/Vite build aprovados; cobre nove traduções com sentinelas, login401 e alerta acessível do formulário.
- Maestro confirmou oito mappings sanitizados e login401 sem callback mediante compilação TypeScript/Node local; typecheck aprovado. Não executado login físico da API nesta unidade. Git readonly impede commit local.

### Próximos passos
- Validar formulário/login no smoke real em owner exclusivo quando readiness estiver disponível; não usar transporte isolado como evidência física.
- Concluir filtro de qualidade dos monitores com contagem/foco/reset e verificação desktop/mobile, em unidade feat separada.

## 2026-10-05 — Sincronização acessível e coleta passiva SSE

### Implementado
- Topo do dashboard mostra conexão, fallback30s, espera durante ação e última consulta de monitores bem-sucedida. Horário conserva em erro, reinicia ao trocar projeto e fica fora da região anunciada.
- Coletor QA correlaciona requestId CDP, sinal/revisão, GET posterior e DOM; prepara240 leituras REST e25 atualizações em owner/projeto privado vazio exclusivo. Guardas e métodos de quantis documentados no relatóriov2.

### Arquivos principais alterados
- `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/test/SyncStatus.test.tsx`
- `frontend/scripts/live-latency-smoke.mjs`, `frontend/scripts/live-latency-observer.mjs`, `frontend/scripts/live-latency-unit.mjs`, `frontend/scripts/live-latency-observer-browser.mjs`
- `frontend/package.json`, `frontend/IMPLEMENTATION.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Conexão/consulta da UI não representa saúde nem horário de check. Somente modo muda dentro de role=status; horário não anuncia ticks.
- PATCH-start→DOM é limite superior, não medição exata commit→DOM. SSE→GET usa um clock CDP; polling permanece ativo e pode tornar causalidade ambígua. Não combinar percentis por rota nem quantis desta amostra vazia com carga de worker.

### Estado atual
- Frontend entregou47 Vitest passed, TypeScript/build aprovados,7 Node e1 Edge em fixture sintética própria; seis estados desktop1440/mobile390 passaram sem overflow/erros. Captura mobile revisada centralmente; relatório `frontend/.impeccable/review/sync-ux/report.json`.
- Maestro confirmou7 Node/zero skips e TypeScript/sintaxe. Vitest/build/Edge no terminal Maestro bloqueiam spawn EPERM; evidências do Frontend são identificadas separadamente.
- Nenhum smoke de latência do produto8080 nem latência de pipeline foi medido nesta unidade. Git local bloqueado pelo sandbox read-only de `.git`; nenhum commit/push alegado.

### Próximos passos
- Confirmar readiness da API/UI reais em terminal com acesso Docker e executar `test:latency` com janela liberada/owner novo. Preservar archive/logout e relatório privado; não renovar seed anterior.
- Concluir correção ptBR de erros de autenticação em `frontend/src/api.ts` com regressões, separada da sincronização e do tooling.

## 2026-10-05 — Guardas de carga e auditoria offline de retenção

### Implementado
- Helper/runner QA observa13 fases de agenda/publicação/claim/commit/ACK com contagens, backlog, concorrência, CPU/RSS e limites de amostragem; namespace UUID, CA fixture e serviços PG17/Redis/TLS descartáveis próprios.
- Runner exige identidade/protocolov1, ordem, commit visível em conexão distinta antes do ACK, todas as amostras/quantis finitos e cleanup; booleanos JSON não substituem contagens numéricas.
- Verificador obrigatório inclui campanha/guardas PG/Redis e coletor Edge; recusa daemon Docker inacessível antes de testes caros/recursos, com mensagem sanitizada.
- CLI offline compara somente FKs de evidência e índices de incidents com SQL Alembic real; registra investigação antes/depois sem alterar models/migrations.

### Arquivos principais alterados
- `backend/tests/helpers/pipeline_load_process.py`, `backend/tests/test_pipeline_load.py`
- `scripts/pipeline_load_check.py`, `scripts/tests/test_pipeline_load_check.py`, `infra/worker/qa_pipeline_load.py`, `scripts/verify.ps1`
- `backend/app/db/audit_retention_contract.py`, `backend/tests/test_db_retention_contract.py`, `backend/app/db/RETENTION_QA_CONTRACT.md`, `backend/app/db/IMPLEMENTATION.md`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Metadata da fixture não valida migrations/head. Verifier por ACK/sampler alteram custo observado; locks de um projeto serializam writes. Percentis de fases não são somáveis; backlog máximo é amostrado e não SLA.
- Auditoria offline tem escopo explícito e recusa ALTER/DROP; ausência de índice inicial apoia investigação, sem provar scan/custo/ganho ou justificar migration especulativa.

### Estado atual
- Central final:105 passed/5 skips obrigatórios ainda não executados (quatro PG17 e um Redis), em1,06s, JUnit `.cache/verification/qa-contracts-central-final.xml`. Runner42, helper39 e contratos/schema24 passaram localmente; Ruff/config do backend/format aprovados.
- Preflight PowerShell aprovado com daemon ausente, versão inválida/válida simuladas e recusa real do pipe, sem iniciar campanha. Tooling parcial completo117 passed/3 skips/2 falhas/4 erros de restrições em pipes/tmp do sandbox; não é aprovação global.
- Campanha física100/60s e negativos PG/Redis atuais continuam pendentes. Docker aberto pelo usuário, pipe negado no Maestro; nenhum startup compartilhado, gate ou PG18 foi alterado. Infra TLS nova ainda precisa da prova Linux real.
- Auditoria confirma head0001_initial e FKs nullable/SET NULL para check_results, sem candidato B-tree inicial nas duas evidências; nenhum SET NULL/plano/otimização real medido. Git bloqueado; não houve commit/push desta unidade.

### Próximos passos
- Liberado acesso ao daemon/Git no terminal, executar verificação obrigatória Linux/PG17/Redis e campanha100 jobs/60s; exigir cleanup confirmado e preservar todos os relatórios de falhas anteriores.
- Executar ensaio de retenção descrito em `backend/app/db/RETENTION_QA_CONTRACT.md` antes de decidir índices/migration; não conectar PG18.

## 2026-10-05 — Validação422 não ecoa nomes JSON extras

### Implementado
- Handler remove do caminho o nome de campo extra controlado pelo cliente; conserva envelope422 e caminhos de campos declarados/índices numéricos.
- Regressões HTTP cobrem cadastro/login, objetos aninhados, erro de parsing JSON e contexto privado de validador.

### Arquivos principais alterados
- `backend/app/api/errors.py`, `backend/tests/test_auth.py`, `backend/tests/test_validation_errors.py`
- `docs/API.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- `extra_forbidden` aponta para o objeto pai; valores/input/contexto permanecem ausentes. Schemas e respostas de sucesso não mudam.

### Estado atual
- Duas regressões de auth falharam antes do fix. Revisão central: auth/validation/observability74 passed/25 skips PostgreSQL em8,02s; três casos aninhados passed em0,05s. Ruff e whitespace aprovados. JUnit `.cache/verification/validation-field-review.xml` e `validation-nested-review.xml`.
- Central parcial anterior:275 passed/214 skips e2 falhas TLS físicas no Windows; peer substituído por Avast, conforme diagnóstico do Backend. Trust não foi alterado. Nenhuma integração PG/Redis desta unidade foi alegada.
- Docker Desktop aberto pelo usuário, mas terminal Maestro recebe permission denied no pipe; provas de carga/retention PG17 continuam pendentes. Sem alteração de gates ou PG18.

### Próximos passos
- Integrar tooling de carga e observação SSE após revisão local; registrar separadamente resultados sintéticos e campanha real ainda pendente.
- Rodar verificação obrigatória Linux/PG17/Redis quando o terminal autorizado tiver acesso Docker; não tratar skips ou interceptação TLS como aprovação global.

## 2026-10-04 — Regressão do seed QA verifica dados commitados

### Implementado
- Testes do tooling existente verificam owner exclusivo, preservação de dados anteriores, hash de login, leitura autenticada pela API, paginação de72 checks/36 incidentes encerrados e exclusão da sentinela privada nos DTOs públicos.
- Métricas/buckets/p95 têm esperados independentes; rollback do chamador remove somente a nova fixture. Guarda de manifesto existente impede abertura/escrita sem depender de ACL de temporários no Windows.

### Arquivos principais alterados
- `backend/app/db/seed_observations_qa.py`, `backend/tests/test_db_qa_seed.py`, `backend/app/db/IMPLEMENTATION.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Produto e comportamento do seed permanecem; import sys explícito substitui import dinâmico. Os testes usam migrations/schema PG17 efêmero e HTTP ASGI local, sem checks externos.
- Não repetir seed em public nem renovar manifesto privado/freshness somente para revisar entrega já integrada.

### Estado atual
- Banco entregou13 passed/zero skips em3,69s e Ruff/format; revisão central confirmou13 passed/zero skips em3,52s no PG17/55433, JUnit `.cache/verification/qa-seed-review.xml` e Ruff aprovado.
- PG17 anterior: schema/migrations/pipeline/retention90 passed/zero skips em59,82s, migration0001_initial(head). Nesta revisão nenhum seedCLI/public, novo smoke ou alteração do manifesto existente; PG18 preservado.
- Limites: ASGI não é navegador; proteção de manifesto verifica recusa antes de I/O, sem medir ACL real. Falha de gravação do manifesto depois do commit ainda pode deixar owner QA isolado.

### Próximos passos
- Concluir campanha Taskiq/PG17/Redis/TLS em serviços descartáveis próprios: Backend possui helper/teste; Maestro servidor/rede/runner e integração. Sem modelos/migrations ou escrita no runtime PG18.
- Medir agenda/publicação/claim/commit/ACK separadamente e reportar limites da amostragem de CPU/RSS; gates compartilhados continuam false.

## 2026-10-04 — Cleanup QA valida recursos antes de remover

### Implementado
- Ensaio egress valida rede internal/UUID, IDs Docker, labels e interfaces de todos os containers conhecidos, além dos endpoints da rede, antes da primeira remoção.
- Revalida cada container e remove por ID imutável; revalida identidade e endpoints da rede antes de removê-la por ID. Divergências preservam recursos e tornam o ensaio falho com cleanup pending_review.

### Arquivos principais alterados
- `scripts/egress_check.py`, `scripts/tests/test_worker_egress.py`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Nomes literais servem somente para inventário/inspeção; remoção usa identidades capturadas para reduzir risco de reutilização de nome.
- Rede não internal, interfaces estrangeiras ou endpoint inesperado já presente bloqueiam todas as remoções. Docker não oferece transação para esse conjunto: mudança tardia pode deixar containers próprios removidos e rede preservada para revisão.

### Estado atual
- Tooling completo:91 passed/zero skips em21,35s, incluindo Edge real, guardas de pré-validação e identidade/endpoint alterados durante cleanup. JUnit `.cache/verification/egress-cleanup-tooling.xml`; Ruff/format passaram nos arquivos modificados.
- Ensaio físico com política/fixture existentes passou firewall/TLS/NDP e confirmou cleanup em `.cache/egress-qa/08c67177d9ff437a867c3d32e837f75f/report.json`; nenhuma rede QA rotulada permaneceu.
- Backend/produto/infra de runtime não mudaram; baseline central anterior433 backend/16 skips SQLite e44 frontend permanece. Gates compartilhados false, PG18 preservado.

### Próximos passos
- Coordenar com Backend helper Taskiq/PG17/Redis/CheckExecutor TLS real para carga em fixtures exclusivas, medindo etapas e backlog; Maestro mantém rede/servidor/runner/relatório.
- Banco finaliza correção pendente do seed QA com testes antes de staging centralizado. Frontend liberado, sem repetir manifesto/smoke expirado sem mudança.

## 2026-10-04 — Heartbeat persistido de ticks concluídos

### Implementado
- Scheduler/publicador observa ticks após commit/publicação e grava hash por stream/group com clock Redis e TTL120s em script atômico. Falha preserva último sucesso/counts.
- Telemetria tem prazo1s, client sem retry e erro JSON sanitizado sem impedir próximos ticks. Cancelamento externo propaga; gate false não cria cliente.
- Diagnóstico readonly observa terceira fonte: last_success/attempt ages, TTL, duração/counts e estados fresh/stale/tick_failed/missing/clock_skew; não inicializa nem renova chave.

### Arquivos principais alterados
- `backend/app/monitoring/heartbeat.py`, `backend/app/monitoring/publisher.py`, `backend/app/monitoring/run.py`, `backend/app/monitoring/status.py`, `backend/app/observability.py`
- `backend/tests/test_scheduler_heartbeat.py`, `backend/tests/test_pipeline_status.py`, `backend/IMPLEMENTATION.md`
- `scripts/verify.ps1`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Identidade JSON stream/group hash SHA256 evita colisão por delimitadores e nomes privados no relatório. Chave única agrega schedulers desse par, sem criar labels por processo.
- TIME do servidor evita comparar relógios de aplicação; timestamps futuros ficam clock_skew/idade null. Fresh significa último sucesso até5s, não liveness da API; ausência após TTL não inventa sucesso.
- Contagens são do último sucesso completo. Tentativa com falha conserva esse histórico e renova TTL; erro de observação não altera persistência do pipeline nem gates.

### Estado atual
- Direcionada inicial28 passed/sem skips; integração/regressão46 passed/5 skips apenas SQLite em30,62s. Primeira central:432 passed/16 skips SQLite e um timeout de admissão TCP da fixture na rajada fria de40 conexões Redis. Relatório preservado em `.cache/verification/heartbeat-central-first.xml`.
- Fixture ajustada para dois writers/reader, três sockets reutilizados e TaskGroup com cleanup;40 escritas/leituras paralelas mantêm prova de atomicidade, sem relaxar prazos do runtime. Final30 passed/sem skips no Windows4,73s/Linux3,89s.
- Central final aprovada:433 backend/16 skips apenas SQLite em245,05s,85 tooling/20,26s e44 frontend;18 casos heartbeat/12 status, zero skips obrigatórios. Ruff/TypeScript/build/Compose/whitespace/firewall/TLS/NDP/DNS Nginx passaram. Cleanup confirmado em `.cache/egress-qa/fdcbf05f68de4f6092df32584171c4ec/report.json` e `.cache/proxy-qa/12431c42864c423abde9105e488bd631/report.json`.
- Provas Redis UUID: sucesso→falha conserva último sucesso, TTL expira de verdade, leituras não renovam chave,40 escritas em dois writers com reader paralelo preservam pares atômicos, namespaces distintos não herdam heartbeat e dados inválidos são sanitizados.
- Prova PG17+Redis confirma publicação já commitada ao observar tick. Entrypoint configurado somente no teste usa schema/fila exclusivos vazios, registra heartbeat sem checks; entrypoint false recusa conexão. Diagnóstico runtime readonly confirmou ausência esperada com gates false.
- CLI final passou também em Linux sem privilégios/código readonly com fila/heartbeat ausentes e gates false. API não foi reiniciada nesta unidade; fontes foram montados somente no container diagnóstico. Nenhum scheduler/worker compartilhado foi iniciado; PG18 preservado. Limites: agregado por fila/grupo, sem saúde por processo/worker, histórico/exporter/carga/SLA; telemetria em falha pode somar1s ao ciclo.

### Próximos passos
- Harden cleanup do ensaio egress em `scripts/egress_check.py`: validar rede internal/UUID, todas as interfaces dos containers e endpoints inesperados antes de remover qualquer recurso; preservar recursos divergentes para revisão.
- Provar carga end-to-end controlada com executor TLS real contra fixtures isoladas e medir atraso/backlog/recursos, mantendo checks externos desligados.

## 2026-10-04 — Diagnóstico read-only de backlog e leases

### Implementado
- CLI privado agrega jobs pending/running/publicação/retry/leases com clock PG e transação REPEATABLE READ/READ ONLY; consultas têm limites de tempo sem row locks.
- Redis distingue stream retido, lag não entregue e ACK pendente em leitura atômica. PEL amostrada em100 menores IDs, com truncamento e medidas exclusivamente da amostra; não faz ACK/reclaim nem cria fila.
- Fontes independentes preservam dados saudáveis em falha parcial, emitindo códigos sanitizados e exit1. Configuração inválida não revela credenciais; não importa tasks nem ativa checks.

### Arquivos principais alterados
- `backend/app/monitoring/status.py`, `backend/tests/test_pipeline_status.py`, `backend/IMPLEMENTATION.md`
- `scripts/verify.ps1`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- pending_due mede elegibilidade temporal, sem alegar autorização/configuração/orçamento suficiente para claim. Contagens de leases/publicação respeitam cutoffs <=now/30s; idade sem população e lag Redis desconhecido ficam null.
- XLEN inclui ACKados; PEL e lag não são intercambiáveis. Não usa XPENDING IDLE, que pode percorrer toda PEL. Consumers registrados não significam processos vivos.
- Nenhum heartbeat foi inventado a partir de jobs; scheduler informa not_implemented/idade null. Flags refletem Settings do CLI e não processos alheios.

### Estado atual
- Direcionada status/observability/publisher/pipeline_db/broker_integration:57 passed/7 skips apenas SQLite em56,38s;12 testes novos. Ruff aprovado, integração central inclui o módulo obrigatório. Relatório `.cache/verification/pipeline-status.xml`.
- Provas PG17/schema UUID: dados intactos, row locks não bloqueiam consulta e DML injetada é rejeitada em read-only. Redis UUID:150 pendentes/amostra100, ACK100 conserva XLEN160 e reduz PEL50, lag10 separado; lag desconhecido não vira zero.
- CLI passou no Windows e Linux UID/GID10001/caps removidas/código readonly contra runtime PG17/Redis com gates false, zero jobs e stream ausente. Conexão Redis local indisponível retornou partial/exit1, preservando snapshot PG; sem mensagens privadas/URLs/DSN no JSON.
- Sem alterações nos processos/dados PG18 nem startup do pipeline. Limites: não há atomicidade entre fontes, benchmark de volume, métricas históricas/exporter ou heartbeat persistido; status ok indica consulta bem-sucedida, não saúde do pipeline.

### Próximos passos
- Persistir heartbeat de tick concluído do scheduler em chave exclusiva com TTL, distinguir falha/ausência/idade sem confundir com liveness/readiness da API.
- Provar carga end-to-end controlada com executor TLS real somente contra fixtures isoladas, incluindo atraso de início/backlog e recursos; checks externos seguem desligados.

## 2026-10-04 — Nginx acompanha mudança de IP da API

### Implementado
- Upstream compartilhado com resolução periódica do DNS Docker para `/api/` e `/health/`, mantendo URI/headers e SSE sem buffering.
- Prova física em rede internal UUID move alias api entre listeners vivos de IPs distintos, verifica nova rota sem reload/restart e primeiro frame SSE antes da conclusão do corpo.
- Guardas recusam mutação/cleanup de redes ou containers estrangeiros; integração obrigatória inclui o ensaio. Smoke CRUD identifica rota/fase e correlaciona GET401 privado somente após logout real.

### Arquivos principais alterados
- `frontend/nginx.conf`, `frontend/scripts/browser-smoke.mjs`, `frontend/IMPLEMENTATION.md`
- `infra/web/qa_upstream.py`, `scripts/proxy_recovery_check.py`, `scripts/tests/test_proxy_recovery.py`, `scripts/verify.ps1`
- `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Shared zone/server resolve usa resolver127.0.0.11, validade5s e timeout2s; evita manter o IP inicial indefinidamente sem prometer atualização instantânea.
- A API antiga permanece viva/alcançável: voltar a receber HTTP200 não basta como evidência, o proxy precisa retornar a identidade da substituta. PIDs master/workers e StartedAt devem permanecer iguais.
- 401 de métricas durante revogação foi reproduzido; o smoke exige resposta GET401 da mesma rota/origem após pedido POST logout e não silencia erros durante o workflow.

### Estado atual
- Configuração anterior manteve 27 respostas da antiga por12s mesmo após DNS apontar só à substituta. Corrigida recuperou em3,534s, primeiro frame SSE16ms, mesmos PIDs e cleanup confirmado: `.cache/proxy-qa/fc6a94fe23394f29986c0498525b9c00/report.json`.
- Tooling85 passed/sem skips em19,63s com PG17/Redis/Edge; Ruff, Compose, whitespace e nginx -t aprovados. Guards novos são8 casos. Não foi repetida a suíte backend/produto JS, que não mudou; baseline central anterior403 backend/16 skips apenasSQLite e44 frontend.
- Web atualizado isoladamente; Edge8080 passou CRUD/history/no_data/status pública/404, desktop1440/mobile390 sem overflow e SSE connected/project.updated/periodic/REST/revogação. API/PG17/Redis preservados, gates false e nenhum sinal/alteração no PG18.
- Limites: troca de alias IPv4 em Docker local/fixtures sintéticas, sem SLA, balanceamento produtivo, migração de streams já abertos, failover de host ou TLS externo.

### Próximos passos
- Implementar snapshot operacional read-only de backlog/PEL/leases e idade de ticks, sem endpoint público nem labels de alta cardinalidade.
- Provar carga controlada end-to-end do pipeline com executor TLS real somente contra fixtures isoladas, mantendo checks externos desabilitados.

## 2026-10-04 — Correlação HTTP e logs JSON de atividade

### Implementado
- Middleware ASGI puro gera X-Request-ID e registra tempo até headers/término com template declarado; requests concorrentes não compartilham contexto, SSE não é bufferizado e cancelamento propaga.
- Formatter limita eventos/fields/códigos, valida UUIDs/números e ignora args/exceções/body/headers/query/URLs/SQL. Sink OSError/ValueError não altera resposta/commit/ACK.
- Worker registra claim/atraso, finalização após commit, recusa/cancelamento/falha persistente; scheduler registra contagens/duração por tick. CMD API desliga access log Uvicorn com URI/query.

### Arquivos principais alterados
- `backend/app/observability.py`, `backend/app/main.py`, `backend/app/api/errors.py`
- `backend/app/monitoring/worker.py`, `backend/app/monitoring/publisher.py`, `backend/app/monitoring/tasks.py`, `backend/app/monitoring/run.py`
- `backend/tests/test_observability.py`, `backend/tests/helpers/api_replica_process.py`
- `backend/Dockerfile`, `backend/IMPLEMENTATION.md`, `frontend/scripts/reconnect-browser-process.mjs`, `scripts/tests/test_api_browser_reconnect.py`, `scripts/verify.ps1`
- `docs/API.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Route é obtida por identidade de rotas de código; desconhecidas ficam unmatched. Isso suporta os routers incluídos da versão FastAPI instalada sem serializar path/query ou depender de APIs privadas.
- 500 de ServerErrorMiddleware externo conserva o ID pelo handler; SSE que falha após headers conserva status original e outcome=error/cancelled. Duração total de stream não é latência REST.
- Helper preserva stderr/erros Uvicorn e grava apenas atividade JSON em relatório privado. Prova Edge arma a API própria antes do crash para correlacionar 503/leituras interrompidas exclusivamente à réplica encerrada.

### Estado atual
- Direcionado: 14 passed/2 skips apenas SQLite em 13,60s. Primeira central: 403 backend/16 skips SQLite em 267,68s; tooling teve 76 passed e uma falha de classificação de ERR_EMPTY_RESPONSE de leitura interrompida durante crash, após recuperar/reconectar/logout com sucesso.
- Correlação da fixture ajustada para conexões da API declaradamente encerrada, incluindo resposta parcial. Edge passou novamente em 22,31s; central final aprovada: 403 backend/16 skips apenas SQLite em 243,32s, 77 tooling e 44 frontend, zero skips obrigatórios. Ruff/TypeScript/build/Compose/whitespace/egress aprovados; cleanup confirmado em `.cache/egress-qa/892dc1d639654f2da9918069b70aba2f/report.json`.
- API local reconstruída/atualizada isoladamente. Prova readonly Nginx8080 correlacionou resposta404 e dois eventos JSON, sem sentinel de query/ID recebido nos logs API; CMD sem access log, gates false e CA de build ausente. Relatório `.cache/verification/activity-runtime.json`.
- Smoke Edge8080 após atualização passou com SSE connected/project.updated/periodic, reconciliação REST e revogação, errors=[]. Web/PG17/Redis e processos PG18 foram preservados.
- Gates false e PG18 preservado. Limites: atividade por processo; métricas agregadas/heartbeats/exporter pendentes. Logs de frameworks/proxy permanecem independentes deste formatter, sem promessa de sanitização global.

### Próximos passos
- Implementar snapshot operacional de backlog/PEL/leases e idade de ticks, sem endpoint público nem labels de alta cardinalidade.
- Provar recuperação do Nginx após mudança real de IP da API em rede QA exclusiva; o proxy atual resolve upstream somente na inicialização.

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
