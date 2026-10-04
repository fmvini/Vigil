# Escopo do Vigil

Data da definição inicial: 2026-10-04. Documento de planejamento; nenhuma funcionalidade está implementada.

## Visão e problema

O Vigil acompanhará endpoints HTTP públicos para que desenvolvedores saibam quando um serviço responde, quanto demora e quando deixa de atender ao contrato esperado. Substitui verificações manuais e históricos dispersos por checks periódicos, métricas e incidentes consultáveis.

Uma resposta HTTP confirma apenas o comportamento observado naquele endpoint e naquele ponto de rede. O produto não concluirá que toda uma aplicação funciona porque seu `/health` respondeu, nem apresentará monitoramento de uma única região como uma medição global.

## Público-alvo e objetivos

- Desenvolvedores independentes e pequenas equipes responsáveis por APIs públicas.
- Pessoas que precisam acompanhar serviços próprios ou de terceiros que tenham autorização para consultar.
- Como projeto técnico, demonstrar concorrência de I/O, jobs duráveis, idempotência, transações, segurança de requisições externas e operação observável.

O objetivo inicial é um MVP utilizável por múltiplos usuários, com um proprietário por projeto, executado a partir de uma única região. O sucesso depende de medições compreensíveis e recuperação de falhas, além de telas de cadastro.

## Organização do produto

**Usuário → Projeto → Monitor.** Um projeto agrupa endpoints de uma aplicação ou serviço. Um monitor representa uma URL e suas regras. Não haverá uma entidade `Service` adicional no MVP: o projeto atende a esse papel de agrupamento.

Cada projeto poderá ter uma página pública, desativada por padrão. A exposição de cada monitor também será opt-in. Projetos de usuários diferentes permanecem isolados.

## MVP

| Área | Entrega inicial |
| --- | --- |
| Conta | Cadastro por e-mail/senha, login, logout e sessão revogável |
| Organização | Criar, editar, listar e arquivar projetos e monitores |
| Checks | GET em URL pública HTTP/HTTPS; sem credenciais, body ou headers personalizados |
| Configuração | Intervalo, timeout, status HTTP esperado, falhas para offline, retries e limiar de latência |
| Pipeline | Scheduler dedicado, fila Redis Streams e workers assíncronos com concorrência limitada |
| Disponibilidade | Online, degradado ou offline; ausência, pausa e desatualização exibidas separadamente |
| Histórico | Um resultado consolidado por ciclo, com resumo das tentativas |
| Incidentes | Abertura automática ao atingir offline e encerramento automático na recuperação |
| Métricas | Uptime por amostras, média/p95 de latências de sucesso e série temporal |
| Dashboard | Projetos, monitores, últimas medições, métricas e incidentes |
| Tempo real | SSE privado; reconciliação REST e polling de contingência |
| Status pública | Resumo e incidentes dos monitores explicitamente publicados |
| Qualidade | Testes de regras e integração, logs, métricas do pipeline e execução futura com Docker |

Todas essas áreas compõem o MVP completo; o roadmap entrega incrementos e não exige construir tudo antes da primeira validação.

## Limites iniciais de produto

Valores são defaults planejados, não capacidade já demonstrada. O contrato detalhado está em [REQUIREMENTS](REQUIREMENTS.md).

- Até 5 projetos e 100 monitores ativos por usuário; até 20 monitores ativos por projeto.
- Intervalo de 60 a 3.600 segundos; timeout de 1.000 a 15.000 ms.
- De 0 a 2 retries de rede por ciclo; GET somente em portas 80/443.
- Checks e jobs terminais por 30 dias; incidentes encerrados por 90 dias.
- Métricas consultáveis nas últimas 24 horas, 7 dias ou 30 dias, ou intervalo explícito dentro da retenção.
- Uma região de execução; sem garantia comercial de SLA e sem alta disponibilidade obrigatória no MVP.

Esses limites evitam transformar a plataforma em um gerador de tráfego sem controle. Alterações posteriores exigem rever capacidade, custos e documentação.

## Análise crítica antes da implementação

| Risco ou ambiguidade | Resolução proposta |
| --- | --- |
| URLs fornecidas pelo usuário permitem SSRF e acesso a metadados da infraestrutura | Restringir destinos públicos, validar A/AAAA na conexão, impedir redirects e aplicar isolamento de saída |
| Reentrega e queda do worker podem repetir checks | Identificar cada ciclo em PostgreSQL; resultado único e lease com token para impedir commits antigos |
| Scheduler pode avançar agenda e perder publicação no Redis | Registrar `CheckJob` e avanço da agenda na mesma transação; publicar e reconciliar depois |
| Timeout/retry pode ultrapassar o intervalo | Validar orçamento total do ciclo e não executar ciclos em paralelo para o mesmo monitor |
| Queda do Vigil pode parecer indisponibilidade do cliente | Excluir falhas internas do uptime e mostrar dados antigos/ausentes, além de medir saúde do pipeline |
| Uptime pode significar tempo real ou proporção de checks | Adotar proporção de ciclos avaliados; informar janela e tamanho da amostra |
| Retries escondem falhas transitórias | Sucesso após retry conta como disponibilidade, mas sinaliza degradado e preserva tentativas |
| Grande volume de checks torna o histórico caro | Retenção limitada, índices por monitor/tempo e paginação; agregações/partições só após evidência |
| Publicação de status pode revelar detalhes privados | DTO público separado, opt-in e ausência de URLs, erros brutos ou informações de conta |
| Login, cadastro e monitoramento podem sofrer abuso | Limites por conta/origem, rate limiting e revisão da política de cadastro antes de abertura pública |

## Futuro, após validar o MVP

- Alertas por e-mail, webhook ou mensageria, com deduplicação e preferências.
- Equipes, convites, permissões e organizações.
- Monitores autenticados com armazenamento criptografado de secrets.
- HEAD e outros métodos seguros, validação de body/JSON, DNS/TCP e certificado TLS.
- Agentes para redes privadas, sem abrir acesso interno aos workers públicos.
- Múltiplas regiões, confirmação cruzada e agregação por localização.
- Manutenções programadas, comunicação manual de incidentes e notas públicas.
- Histórico mais longo, agregações incrementais, particionamento e exportações.
- Uptime ponderado por tempo, SLOs e política formal para lacunas de observação.
- Domínios personalizados para status pages e autenticação externa.

## Fora do escopo inicial

Billing, planos comerciais, Kubernetes, Kafka, service mesh, arquitetura de microserviços, event sourcing, APM/tracing dos serviços dos clientes, armazenamento de bodies, checks que alteram dados, monitoramento global, infraestrutura multi-região e migração de ferramentas externas.

Nesta etapa de documentação também estão fora do escopo: qualquer código de aplicação, scaffold, instalação, configuração de PostgreSQL/Redis/Docker ou criação de migrations. A implementação depende de uma nova instrução.
