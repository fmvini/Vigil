# Contrato de investigação das FKs de evidência

## Evidência local disponível

`python -m app.db.audit_retention_contract`, executado de `backend/`, gera um JSON
com `scope=incident_evidence_fks_and_indexes_offline`. Usa metadata ORM e o SQL
offline do head Alembic real; não lê a URL runtime nem abre conexão.

`retention_contract_matches_migration` compara somente as duas FKs de evidência e
os índices declarados de `incidents`, não a paridade global do schema. O parser
suporta a definição inicial CREATE TABLE e índices aditivos. Recusa ALTER/DROP
conservadoramente; não interpreta SQL arbitrário nem substitui inspeção de catálogo.

Baseline `0001_initial`: `opening_check_id` e `closing_check_id` são nullable,
referenciam `check_results.id` com ON DELETE SET NULL e não possuem candidatos
B-tree declarados com essas colunas na primeira posição. Um candidato parcial
não prova aplicabilidade do predicado nem escolha do planner. Nenhuma conclusão
sobre custo, lock, execução de SET NULL ou ganho de performance foi medida.

As FKs simples de evidência verificam existência do resultado, não que ele pertença
ao mesmo monitor do incidente. Uma escrita SQL direta cruzando monitores/owners
foi aceita em SQLite com FKs habilitadas. A aplicação garante o vínculo em
`finalize_job` e no seed QA; a API não recebe IDs de evidência para escrita.
É um limite estrutural, sem vetor de bug API demonstrado. Não propor migration
para esse caso sem contrato e evidência PG17, preservando SET NULL da retenção.

## Hipótese e propriedade

`backend/app/services/retention.py`, seleção de evidências e subconsulta de
referências não adquiridas, usa opening_check_id OR closing_check_id. As FKs de
SET NULL também procuram referências ao remover resultados. A hipótese é custo
de scan sobre o histórico de incidentes; precisa de planos reais para avaliação.

Banco possui auditoria, models, migrations e test_db*. Backend preserva o serviço
e seus testes de retenção. Não alterar `0001_initial`, metadata ou criar migration
de otimização antes da evidência PG17. Maestro possui infraestrutura, documentação
central e Git. Gates false e PG18/runtime preservados.

## Executor e contrato do ensaio

O executor explícito é `python -B -m app.db.retention_plan_qa --qa-opt-in
--token <UUID> --lease-host <IP privado do PG QA> --report-file <arquivo novo>`.
Exige `VIGIL_RETENTION_PLAN_QA=1`, `VIGIL_RETENTION_QA_TOKEN` igual ao argumento,
`VIGIL_RETENTION_QA_DATABASE_URL` explicitamente fornecida pelo lease (qa/qa,
porta5432) e gates false. Não lê Settings nem usa URLs runtime/teste como fallback.
Backend fornece e executa o runner; IDs/labels/rede/digest e validade do lease são
coordenados antes da execução. Sem publicar DSN nos artefatos.

O módulo cria somente schema UUID com marker, aplica `0001_initial`, gera 10mil
jobs/resultados/incidentes e100 monitores. Há2500 incidentes em cada categoria:
opening apenas, closing apenas, ambas para o mesmo resultado, nenhuma evidência.
Os100 incidentes abertos possuem apenas opening; distribuição é consultada no PG.
SQL/binds do driver são capturados de `retain_batch` real nos lotes1/100/1000,
com rollback e fingerprints de linhas. Capturas terminam antes de coletar stats
QA uma única vez e executar ambos os estágios de planos com SQL/binds idênticos.
Probes auxiliares de igualdade não são execução/medição dos triggers FK.

Report JSON exclusivo contém SQL parametrizado, binds da fixture, planos completos,
catálogo de constraints/índices de incidents, stats, tamanhos dos candidatos e
confirmação de ausência após cleanup por marker. EXPLAIN não usa ANALYZE; captures
de retenção executam DML apenas na fixture e o revertem. Falha/cancelamento tenta
cleanup limitado com task protegida; marker diferente preserva o recurso. Falha
de cleanup deve ser reportada e coordenada com Backend, nunca escondida como sucesso.
Desde a revisão2026-10-06, `completed` permanece false até o cleanup terminar;
falha na remoção impede registrar conclusão bem-sucedida no JSON.
`tests/test_db_retention_plan.py` valida guardas/falhas/fixture sem conexão real;
aprovação desses testes não comprova planos PG.

1. Maestro fornece serviços PG17 descartáveis exclusivos, sem portas/volumes de
   runtime. Conferir identidade e versão antes de DDL. Criar schema UUID com
   marker e search_path exclusivo; aplicar a migration real `0001_initial`.
   Inspecionar catálogo/head/constraints/índices; metadata.create_all não serve
   como substituto. Evitar usar fixtures de observações existentes.
2. Preparar fixture determinística com 10 mil incidentes, resultados/jobs válidos
   e referências seletivas para lotes de 1/100/1000. Incluir opening, closing,
   ambas, evidências NULL e incidentes abertos; respeitar unicidade de incidente
   aberto por monitor. Registrar seed, contagens e distribuição. Atualizar stats
   somente das tabelas desse schema QA, fora da medição.
3. Capturar SQL e parâmetros das queries reais de `retain_batch`, mediante chamada
   em transação revertida, com eventos locais de teste. Não criar uma cópia manual
   do serviço. Observar seleção de evidências com OR e a subconsulta correlacionada;
   observar também a busca por igualdade em cada FK. Parâmetros vêm apenas da
   fixture; não registrar SQL/DSN/dados do runtime.
4. Rodar EXPLAIN (FORMAT JSON), sem ANALYZE, com SQL/parâmetros/estatísticas idênticos
   para baseline. Guardar estimativas, nós de scan/sort e seletividade. Isso não
   mede tempo de execução nem custo real de triggers FK. Não forçar planner nem
   afirmar que scan sequencial em população pequena é um bug.
5. Somente nesse schema descartável, ensaiar candidatos B-tree parciais
   `opening_check_id WHERE opening_check_id IS NOT NULL` e o equivalente closing.
   Repetir os planos e registrar o tamanho dos índices. Ainda não editar models
   nem migration do repositório. Mesmo que planos melhorem, declarar somente a
   evidência observada, sem promessa de latência/SLA ou benefício universal.
6. Se houver suporte nos planos, propor nova migration aditiva e metadata. Testes
   PG17 precisam provar upgrade0001→head, downgrade→0001, paridade do catálogo,
   preservação de incidentes/Monitor/Project, SET NULL das duas evidências e
   rollback; repetir `tests/test_retention.py` sem modificar suas expectativas.
   Regressão de plano não deve exigir escolha exata de índice pelo planner.
7. Cleanup confirma identidade/marker do schema e ausência após remoção; falha de
   identidade preserva o recurso. Maestro valida recursos Docker antes de cleanup.
   Sem PG17 acessível, testes reais ficam explicitamente pendentes, nunca aprovados
   por skip ou por SQLite.

## Verificação local

`tests/test_db_retention_contract.py` compara o contrato com o SQL offline real e
injeta drift de nulabilidade, DELETE action, alvo FK e índice apenas na metadata.
Também impede falso candidato por coluna não inicial ou índice hash, recusa
ALTER/DROP e verifica que o CLI continua offline com URLs runtime/teste inválidas
e métodos de conexão síncrona/assíncrona proibidos. Isso não executa SET NULL nem
substitui testes PG17 de catálogo, concorrência e retenção.

## Ensaio PG17 executado — 2026-10-05

Lease Backend `9e7cf99f9f0f42519af3af1be88f7f8d`, PG170011 descartável exclusivo.
Evidência: `.cache/verification/backend-retention-qa-9e7cf99f9f0f42519af3af1be88f7f8d/retention-plan.json`.
Migration0001 real,10mil linhas, categorias2500 cada e100 abertos sem closing.
SQL/binds idênticos em ambos os estágios; stats incidents10000 tuplas/198 páginas.
Fingerprints após rollback/EXPLAIN e ausência do schema após cleanup confirmados.
Constraints/FKs de incidents ficaram idênticas entre baseline e candidatos QA.

| Query real / lote | Custo total estimado baseline | Com candidatos |
| --- | ---: | ---: |
| Seleção de evidências /1 | 348.03 | 16.04 |
| Seleção de evidências /100 | 408.59 | 281.63 |
| Seleção de evidências /1000 | 530.22 | 446.69 |
| DELETE results com guarda de referências /1 | 468.18 | 32.64 |
| DELETE results com guarda de referências /100 | 16084.57 | 1107.01 |
| DELETE results com guarda de referências /1000 | 147648.50 | 6761.23 |

Nas duas queries, scans de incidents mudaram de seq scan para bitmap heap/index
com os dois candidatos. Demais queries do serviço permaneceram iguais. Probes
auxiliares de igualdade passaram de custo estimado323 para8.30 e index scan;
não são execução de triggers. Cada candidato ocupou180224bytes nessa fixture.

A evidência sustenta os dois B-tree parciais nessa distribuição e corroborou a
autorização da migration aditiva0002. Não há EXPLAIN ANALYZE, latência medida,
benefício universal/SLA ou medição do overhead real de manutenção dos índices.
O planner pode escolher outro acesso conforme volume, seletividade e estatísticas;
os testes de regressão não exigem um plano exato.

`0002_incident_evidence_indexes` acrescenta apenas os dois índices parciais
`IS NOT NULL`. Models refletem a mesma definição;0001 permanece congelada.
CREATE INDEX normal usa DDL transacional, permitindo rollback integral, e bloqueia
escritas concorrentes durante a construção. Uma aplicação da migration deve prever
essa janela de lock. Dois índices adicionam armazenamento e manutenção nas escritas;
não houve mudança espontânea para CONCURRENTLY, FKs, nulabilidade ou política TTL.

Regressões novas em `tests/test_db_incident_evidence_indexes.py` verificam catálogo,
upgrade0001/head/downgrade0001, preservação de linhas/constraints, SET NULL das duas
evidências e rollback de DDL/DML. Atualizadas conscientemente as expectativas head
e head→base offline em `test_db_postgresql.py`; baseline0001 continua comprovada
por testes offline e pelo catálogo antes do upgrade. JUnit PG histórico confirmado
em2026-10-06:102 passed/zero skips em26.491s, incluindo2 regressões de índices
e29 casos de retenção. Todos13 hashes conferidos iguais antes da correção do helper;
preflight posterior:schemas vazios,Redis0,gates false. A correção posterior do
relatório tem prova offline47 passed/zero skips, sem nova execução PG; não confundir
histórico PG17 com aplicação ao PG18 local. Backend preserva seu serviço e testes.

Referências de interpretação: [índices parciais PG17](https://www.postgresql.org/docs/17/indexes-partial.html)
e [combinação de índices PG17](https://www.postgresql.org/docs/17/indexes-bitmap-scans.html).
