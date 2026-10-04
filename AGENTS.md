# Instruções do projeto

## Git

- Faça commit local a cada unidade relevante e coerente de funcionalidade, correção, refatoração, configuração ou etapa concluída.
- Antes de commitar, revise `git diff`, rode os testes existentes e adicione somente os arquivos relevantes explicitamente.
- Não commite código quebrado, sem verificação ou com erros de sintaxe. Não execute push sem pedido explícito do usuário.
- Mensagem: `<tipo>: <resumo claro em até aproximadamente 70 caracteres>`, linha em branco e bullets descrevendo mudança, motivação e impacto. Tipos: feat, fix, refactor, docs, test, chore.
- Pergunte antes de executar `git init` se não houver repositório. Neste projeto, o usuário autorizou a inicialização local em 2026-10-04.
- Durante trabalho concorrente no Maestri, Maestro centraliza staging e commits; especialistas entregam arquivos e evidências de testes sem disputar o índice.

## Continuidade

- Consulte `docs/DEVELOPMENT_LOG.md` antes de tarefa relevante.
- Atualize esse arquivo ao concluir funcionalidades, correções importantes, arquitetura, API, persistência, configuração, dependências ou etapas significativas.
- Adicione registros recentes no topo usando data e título, seguidos de `Implementado`, `Arquivos principais alterados`, `Decisões técnicas`, `Estado atual` e `Próximos passos`.
- Preserve registros anteriores, use caminhos reais e registre limitações/incompletudes honestamente. Próximos passos devem permitir continuidade imediata.
- Não documente recursos como concluídos antes de funcionarem.

## Coordenação

- Reutilize os agentes conectados Frontend, Backend e Banco de Dados. Consulte `maestri list` antes de enviar mensagens.
- Frontend possui `frontend/`; Backend possui `backend/`, exceto persistência; Banco de Dados possui `backend/app/db/`, `backend/migrations/`, `backend/alembic.ini` e `backend/tests/test_db*`.
- Maestro possui documentação e infraestrutura e revisa a integração. Dockerfiles e arquivos de infraestrutura nos diretórios de aplicação são exceções de propriedade coordenadas pelo Maestro.
- Não edite arquivos que outro agente está modificando; combine mudanças de contrato diretamente antes de integrar.
