---
name: Vigil
description: Console claro para administrar projetos e monitores HTTP.
colors:
  accent: "#145c43"
  accent-hover: "#0e4934"
  muted: "#5c6b63"
  border: "#dbe3de"
  surface: "#fff"
  canvas: "#f7f9f8"
  text: "#202d28"
  control-text: "#283a30"
  control-border: "#bccbc2"
  control-border-hover: "#90a79a"
  field-border: "#aebfb4"
  placeholder: "#64746a"
  subtle: "#edf2ef"
  control-active: "#e3ece6"
  disabled-field: "#edf1ee"
  focus: "#26785a"
  nav-hover: "#e0e9e3"
  selected-bg: "#d7e7dd"
  selected-text: "#124b36"
  danger: "#a12828"
  danger-hover: "#842020"
  data-none-bg: "#e9eeeb"
  data-none-text: "#485b4f"
  data-stale-bg: "#fff0d2"
  data-stale-text: "#77520b"
  data-paused-bg: "#e7edf8"
  data-paused-text: "#385276"
  data-fresh-bg: "#dff0e5"
  data-fresh-text: "#235b3a"
  health-online: "#236443"
  health-degraded: "#875a07"
  alert-bg: "#ffefee"
  alert-text: "#802525"
  alert-border: "#eab9b3"
  success-bg: "#e9f4ed"
  success-text: "#23573c"
  success-border: "#b2d3bd"
typography:
  display:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "2.875rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-.03em"
  headline:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-.03em"
  title:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-.02em"
  body:
    fontFamily: "Public Sans, sans-serif"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Public Sans, sans-serif"
    fontSize: ".875rem"
    fontWeight: 600
    lineHeight: 1.5
  caption:
    fontFamily: "Public Sans, sans-serif"
    fontSize: ".75rem"
    fontWeight: 400
    lineHeight: 1.5
  button:
    fontFamily: "Public Sans, sans-serif"
    fontSize: ".875rem"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  link: "2px"
  badge: "4px"
  control: "6px"
  panel: "12px"
spacing:
  4: "4px"
  6: "6px"
  8: "8px"
  12: "12px"
  16: "16px"
  20: "20px"
  24: "24px"
  28: "28px"
  32: "32px"
  36: "36px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.control-text}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-danger-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-link:
    backgroundColor: "transparent"
    textColor: "{colors.accent}"
    typography: "{typography.button}"
    rounded: "{rounded.link}"
    padding: "4px 0"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    width: "100%"
  nav-project:
    backgroundColor: "transparent"
    textColor: "{colors.control-text}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
    width: "100%"
  nav-project-current:
    backgroundColor: "{colors.selected-bg}"
    textColor: "{colors.selected-text}"
  badge-no-data:
    backgroundColor: "{colors.data-none-bg}"
    textColor: "{colors.data-none-text}"
    rounded: "{rounded.badge}"
    padding: "3px 8px"
  badge-stale:
    backgroundColor: "{colors.data-stale-bg}"
    textColor: "{colors.data-stale-text}"
    rounded: "{rounded.badge}"
    padding: "3px 8px"
  badge-paused:
    backgroundColor: "{colors.data-paused-bg}"
    textColor: "{colors.data-paused-text}"
    rounded: "{rounded.badge}"
    padding: "3px 8px"
  badge-fresh:
    backgroundColor: "{colors.data-fresh-bg}"
    textColor: "{colors.data-fresh-text}"
    rounded: "{rounded.badge}"
    padding: "3px 8px"
  editor:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "28px"
  monitor-row:
    textColor: "{colors.text}"
    padding: "20px 16px"
  monitor-row-mobile:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "18px"
---

# Design System: Vigil

## Overview

**Creative North Star: "Console de operações"**

O Vigil apresenta um console claro e sóbrio para administrar projetos e monitores HTTP. Texto, divisórias e uma única cor de ação organizam o trabalho; a densidade permite comparar endpoints sem esconder o contexto de cada leitura.

Este documento registra decisões observadas neste incremento em `src/styles.css`, `src/App.tsx` e `src/Forms.tsx`. A direção deriva do brief e da autorização de implementação em `PRODUCT.md`; não representa uma preferência pessoal declarada pelo usuário. A separação entre saúde e qualidade dos dados orienta a apresentação de estados.

**Key Characteristics:**

- Superfícies claras, bordas discretas e nenhuma sombra.
- Public Sans local com hierarquia compacta.
- Verde profundo nas ações principais e seleção de projetos.
- Saúde e atualização dos dados em campos distintos.
- Formulários inline e lista adaptada à largura disponível.

## Colors

O verde profundo concentra ação e seleção; os neutros esverdeados sustentam leitura e agrupamento. Os valores normativos estão no frontmatter e correspondem ao CSS existente.

### Primary

- **Verde de ação** (`accent`, `accent-hover`): botões principais, links e ponto da marca; o hover escurece a ação.
- **Verde de seleção** (`selected-bg`, `selected-text`): combinação tonal reservada ao projeto atual.
- **Verde de foco** (`focus`): contorno visível para navegação por teclado.

### Neutral

- **Fundo claro** (`canvas`): área de trabalho; **superfície branca** (`surface`): controles e editores.
- **Plano sutil** (`subtle`): barra lateral, cabeçalho da tabela e hover de botões secundários.
- **Texto principal** (`text`) e **texto auxiliar** (`muted`): conteúdo e contexto, respectivamente.
- **Bordas** (`border`, `control-border`, `field-border`): seções, botões e campos; controles usam tratamentos próprios de hover e desabilitação.

Os tokens `data-*` descrevem qualidade: neutro para ausência, âmbar para dados antigos, azul para pausa e verde para dados atuais. `health-online`, `health-degraded` e `danger` descrevem saúde. Alertas e confirmações de sucesso usam pares de fundo, texto e borda específicos; vermelho também identifica arquivamento.

**The Independent States Rule.** Mostre a saúde e a qualidade dos dados separadamente; ausência ou idade da leitura não comunica um serviço saudável.

## Typography

**Body Font:** Public Sans, com fallback sans-serif. `src/main.tsx` carrega localmente os pesos 400, 500, 600 e 700 por `@fontsource/public-sans`.

A mesma família atende títulos, campos e dados. O contraste vem de tamanho e peso; não há uma segunda família de exibição ou monoespaçada.

### Hierarchy

- **Display:** mensagem de autenticação; reduz para (2rem) em telas pequenas.
- **Headline:** nome do projeto e títulos principais; reduz para (1.5rem) no mobile.
- **Title:** títulos de seções; o título da autenticação tem a variação observada (1.75rem). Subtítulos usam (1rem, peso 600).
- **Body:** texto normal com entrelinha herdada; parágrafos globais limitam largura a (70ch). O CSS não define um tamanho global explícito.
- **Label / Button:** rótulos e ações compactas; a entrelinha própria dos botões está no token `button`.
- **Caption:** ajuda de campos, URLs e contexto. Tabela e barra superior usam a variação (.8125rem); nome do monitor usa (.875rem, peso 600).

Datas, contagens e células numéricas usam algarismos tabulares. Nomes, URLs e conta permitem quebra para preservar a largura da tela.

## Layout

O shell desktop tem navegação lateral (236px) e conteúdo flexível. A área de trabalho limita-se a (1600px), com margens internas laterais (36px). Em até (1150px), a navegação reduz para (200px), as margens para (24px), cabeçalhos empilham e regras de formulário passam de três para duas colunas.

Em até (760px), a navegação vira uma área no topo, os projetos quebram em linhas e o conteúdo usa margens laterais (20px). A tabela conserva sua marcação semântica e apresenta cada monitor como um bloco com rótulos de coluna. Contagens formam duas colunas; formulários passam para uma coluna e ações podem quebrar de linha. A largura mínima do documento é (320px).

A autenticação usa duas colunas no desktop e empilha apresentação e formulário no mobile. O formulário limita-se a (370px). Editores aparecem inline, com formulário limitado a (960px); a malha inicial tem duas colunas e espaçamento horizontal (24px).

As capturas locais em `.impeccable/review/desktop.png`, `mobile.png`, `mobile-editor.png` e `mobile-login.png` registram este incremento. São evidência de revisão, não assets de produto.

## Elevation & Depth

O CSS não define sombras. Fundo, borda e espaço distinguem navegação, trabalho, editor e confirmação. O resumo usa divisórias horizontais, sem uma coleção de cartões elevados.

**The Flat Surfaces Rule.** Preserve a separação por tom e borda das superfícies existentes.

## Shapes

Controles têm curvas discretas (`rounded.control`); badges são menores (`rounded.badge`); editores, estados vazios, confirmação e linhas mobile usam cantos mais amplos (`rounded.panel`). O botão de texto usa a curva mínima (`rounded.link`). O ponto da marca é circular, sem introduzir outro vocabulário de formas.

Campos e superfícies usam bordas (1px). O foco global usa um contorno (3px), deslocado (3px), que permanece visível fora do controle.

## Components

### Buttons

Ações compactas com texto explícito. Primary salva, cria ou autentica; secondary atualiza, edita e cancela; danger confirma arquivamento; danger-text abre sua confirmação. Link atende ações discretas de conta e navegação.

Hover e active seguem o CSS de cada variante, sem deslocar o botão. Transições de fundo e borda duram (160ms). Desabilitação reduz opacidade (.55) e usa cursor de indisponibilidade. A preferência por movimento reduzido remove transições. Ações da linha usam padding (6px 8px) e fonte (.75rem); no mobile têm altura mínima (36px).

### Inputs / Fields

Campos brancos, borda definida e altura mínima (42px), com rótulos associados e ajuda textual. Placeholder e estado desabilitado usam tokens próprios. O foco usa o contorno global; não há uma decoração de erro por campo no CSS. Erros de validação aparecem no alerta do formulário. Textarea permite redimensionamento vertical.

### Navigation

Lista de projetos com alvo em toda a largura, alinhamento à esquerda e nome que pode quebrar. O projeto atual usa `aria-current="page"`, fundo tonal e peso 600. No mobile a lista vira um conjunto de itens que quebram em linhas. Durante uma mutação ou salvamento do editor, seleção e saída da conta ficam desabilitadas.

### Data badges

Rótulos pequenos, sem interação, para Sem dados, Desatualizados, Pausado e Atualizados. A cor reforça o texto; a leitura de saúde fica em outro campo. Não há hover ou foco em badges estáticos.

### Editors / Containers

Editor branco com borda e padding (28px; 20px no mobile). Ações Salvar e Cancelar ficam dentro do formulário. Durante envio, o fieldset e as ações externas concorrentes ficam desabilitados. Estado vazio usa a mesma superfície e cantos, com conteúdo centralizado e indicação da próxima ação. A confirmação de arquivamento usa fundo quente e ação danger.

### Monitor rows

A linha agrupa nome, URL, intervalo, qualidade, última saúde, último check e ações. Dados ausentes têm texto explícito; saúde histórica recebe a indicação Leitura histórica. A consulta de configuração não é uma medição do endpoint. No mobile, os mesmos campos viram linhas rotuladas dentro de uma superfície com borda.

### Feedback

Alertas usam `role="alert"`; confirmações e carregamento usam `role="status"`. O skeleton é uma superfície estática, sem animação. A interface fornece retry quando uma consulta falha e apresenta ausência de monitores como estado vazio.

## Do's and Don'ts

### Do:

- **Do** preserve a hierarquia de texto, bordas e superfícies claras observada no código.
- **Do** mantenha rótulos de saúde e qualidade dos dados independentes.
- **Do** preserve foco visível, rótulos de formulário e estados de envio desabilitados.
- **Do** adapte tabela, formulários e navegação nos breakpoints existentes.

### Don't:

- **Don't** apresente dados ausentes ou desatualizados como confirmação de saúde.
- **Don't** acrescente medições, uptime ou gráficos sem dados reais disponíveis.
- **Don't** acrescente sombras ou decoração que substituam a organização por tom e borda deste incremento.
- **Don't** trate o horário de consulta da configuração como o horário de um check.
