# Políticas, aceites e cookies

## Contrato do produto

- `/privacy`, `/terms` e `/cookies` são páginas públicas, disponíveis sem autenticação. A versão inicial é `2026-10-09`.
- Cadastro e login exigem duas confirmações independentes: Termos de Uso e ciência da Política de Privacidade. Ambas começam desmarcadas; o formulário não deve enviar uma requisição sem as duas.
- `POST /api/v1/auth/register` e `POST /api/v1/auth/login` recebem `terms_version` e `privacy_version` obrigatórios e iguais às versões atuais, além das credenciais. Ausência ou valor incompatível retorna 422.
- Cada cadastro/login bem-sucedido acrescenta uma linha em `legal_acceptances`, na mesma transação que a conta/sessão. O registro contém conta, versões, horário do servidor e operação. Não inclui IP ou user agent; falhas não registram aceite.
- A demonstração não cria contas, sessões reais ou registros de aceite.
- O aviso de cookies pode ser aceito ou recusado e reaberto pelo rodapé. A decisão versionada é conservada no navegador por até 180 dias. Não há analytics, publicidade ou categorias opcionais nesta implementação; a recusa não impede cookies estritamente necessários à sessão solicitada.
- Rotas de página desconhecidas mostram a página 404; o servidor da aplicação retorna HTML com status 404. Rotas `/api`, `/health` e assets ausentes preservam o tratamento de erro de suas superfícies.

## Conteúdo e atualização

`frontend/src/legalContent.ts` centraliza os documentos e o contato. `backend/app/legal.py` define as versões aceitas pela API. Mudanças materiais nos documentos exigem atualizar as versões nas duas camadas e revisar os testes; não reescrever o histórico de aceites.

A aceitação dos termos e a ciência da política não representam consentimento genérico para novas finalidades. A escolha de cookies é independente da autenticação. Cookies opcionais futuros precisam de controles reais que impeçam sua ativação antes da escolha; alterar apenas o texto do banner não é suficiente.

Os textos descrevem os recursos existentes: senha armazenada como hash, cookie de sessão, tema local, resultados sem corpo da resposta, publicação opcional de status, demonstração em memória e infraestrutura Render/Neon/GitHub/Cloudflare. Arquivamento não equivale a exclusão de conta.

## Pendências editoriais antes de publicar

- Preencher o nome do responsável e o e-mail de atendimento em `LEGAL_CONTACT`; atualizar os trechos de contato nos três documentos. Esses dados foram solicitados ao usuário e não foram inventados.
- Definir os prazos de conservação para contas, configurações e histórico de aceites e o processo operacional de atendimento a pedidos de titulares. O sistema ainda não exclui contas automaticamente.
- Confirmar as condições reais dos fornecedores e os procedimentos aplicáveis a processamento internacional. O texto informa a possibilidade de processamento fora do Brasil sem declarar salvaguardas que não tenham sido comprovadas.

## Publicação

A migration `0003_legal_acceptances` precisa ser aplicada antes do uso do novo backend. O bootstrap cloud já executa `alembic upgrade head`; web e executor devem acompanhar o mesmo schema. Versões anteriores do frontend não enviam os campos exigidos, por isso publicar frontend e API juntos.

Não há aprovação de push ou deploy implícita nesta implementação. O projeto utiliza deploy manual no Render; um push sozinho não atualiza o site.

## Referências utilizadas para o texto

- [LGPD — texto atualizado da Câmara dos Deputados](https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html): finalidades, transparência, hipóteses de tratamento e direitos dos titulares.
- [Guia orientativo de cookies da ANPD](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_orientativo_cookies_e_protecao_de_dados_pessoais): distinção entre tecnologias necessárias e opcionais, escolha informada e possibilidade de revisão.

Essas referências orientam a redação; a implementação não declara certificação de conformidade legal.
