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

## Ensaio antes/depois, ainda não executado

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
