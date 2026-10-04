# Vigil frontend

## Platform
Web responsivo em português, navegação por teclado e formulários HTML semânticos.

## Product
Ferramenta de monitoramento HTTP para desenvolvedores e pequenas equipes. Este incremento administra contas, projetos e monitores. O pipeline de checks ainda não existe; nenhuma medição ou disponibilidade é fabricada.

## Stack
React, TypeScript, Vite. API FastAPI em /api/v1 via proxy localhost:8000. Sessão por cookie; token CSRF somente em memória.

## Confirmed brief
Login/cadastro, seleção de projeto, criação/edição/arquivamento de projetos e monitores, pausa/retomada e dashboard com saúde separada de qualidade dos dados. Listas, erros e dados vêm da API real.

## Direction
Modo Operate. Console claro e sóbrio para trabalho cotidiano: navegação lateral compacta, tabela de monitores com prioridade para qualidade dos dados, formulários inline. Verde profundo para ações e seleção; cores semânticas distintas para saúde e qualidade. Sem gráficos ou cartões de métricas sem dados.

O usuário autorizou iniciar e prosseguir sem aguardar decisões adicionais. A direção e o fluxo direto em código derivam do brief, não de uma preferência visual previamente estabelecida.
