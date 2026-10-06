-- Conciliação PRÉ-CORTE: roda no schema que está em produção HOJE.
--
-- Por que existe separado de `reconcile_multimarket.sql`: aquele consulta
-- colunas que só passam a existir DEPOIS das migrations — `user_markets.status`
-- (rbac_r2a), `products.market_code` (r4), `catalogs.market_code` (r6). Rodando
-- antes do corte, ele aborta na primeira dessas consultas e deixa de verificar
-- as outras onze, justamente quando a verificação mais importa.
--
-- Este script responde a única pergunta que precisa ser respondida ANTES de
-- aplicar a cadeia: **alguma das duas migrations abortivas vai falhar?**
--
--   market_fk_r7    -> falha se houver pedido apontando para cliente ou
--                      representante de outro mercado
--   uf_whitelist_r8 -> falha se houver registro BR com UF fora das 27 siglas
--
-- Somente leitura: abre READ ONLY e encerra com ROLLBACK.
--
-- Uso:
--   psql "$PRODUCTION_DATABASE_URL" -f ops/reconcile_pre_cutover.sql

BEGIN TRANSACTION READ ONLY;

\echo '### 1. Ponto de partida'
SELECT version_num AS alembic_head FROM alembic_version;
SELECT code, currency, locale, tax_label, is_enabled FROM markets ORDER BY code;

\echo ''
\echo '### 2. Linha de base: contagens e totais a preservar'
SELECT 'clients' AS entidade, market_code, count(*) AS linhas FROM clients GROUP BY 2
UNION ALL SELECT 'representatives', market_code, count(*) FROM representatives GROUP BY 2
UNION ALL SELECT 'orders', market_code, count(*) FROM orders GROUP BY 2
ORDER BY 1, 2;

SELECT market_code, currency, count(*) AS pedidos,
       sum(total_value) AS soma_valor,
       sum(total_with_ipi) AS soma_com_imposto
FROM orders GROUP BY 1, 2 ORDER BY 1, 2;

\echo ''
\echo '### 3. Entidades ainda sem mercado (viram BR no backfill)'
SELECT 'products' AS entidade, count(*) AS linhas FROM products
UNION ALL SELECT 'catalogs', count(*) FROM catalogs
UNION ALL SELECT 'product_types', count(*) FROM product_types
UNION ALL SELECT 'optionals', count(*) FROM optionals
UNION ALL SELECT 'optional_categories', count(*) FROM optional_categories
ORDER BY 1;

\echo ''
\echo '### 4. market_fk_r7 vai abortar? (esperado 0 em todas)'
SELECT 'orders.client_id cruza mercado' AS checagem, count(*) AS linhas
FROM orders o JOIN clients c ON c.id = o.client_id
WHERE c.market_code <> o.market_code
UNION ALL
SELECT 'orders.rep_id cruza mercado', count(*)
FROM orders o JOIN representatives r ON r.id = o.rep_id
WHERE o.rep_id IS NOT NULL AND r.market_code <> o.market_code;

-- products.catalog_id ainda não tem par de mercado para cruzar: products não
-- tem market_code neste schema. A r4 classifica tudo como BR e a r6 faz o mesmo
-- com catalogs, então o cruzamento nasce impossível. Conferido depois do corte.

\echo ''
\echo '### 5. uf_whitelist_r8 vai abortar? (esperado 0)'
SELECT 'clients com UF invalida' AS checagem, count(*) AS linhas
FROM clients
WHERE market_code = 'BR' AND state NOT IN (
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO')
UNION ALL
SELECT 'representatives com UF invalida', count(*)
FROM representatives
WHERE market_code = 'BR' AND state NOT IN (
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO');

\echo ''
\echo '--- se houver UF invalida, estas sao as siglas encontradas ---'
SELECT 'clients' AS tabela, state, count(*) AS linhas
FROM clients
WHERE market_code = 'BR' AND state NOT IN (
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO')
GROUP BY 1, 2
UNION ALL
SELECT 'representatives', state, count(*)
FROM representatives
WHERE market_code = 'BR' AND state NOT IN (
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO')
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '### 6. Integridade das filhas (esperado 0)'
SELECT 'order_items sem pedido' AS checagem, count(*) AS linhas
FROM order_items oi LEFT JOIN orders o ON o.id = oi.order_id WHERE o.id IS NULL
UNION ALL
SELECT 'order_history sem pedido', count(*)
FROM order_history oh LEFT JOIN orders o ON o.id = oh.order_id WHERE o.id IS NULL
UNION ALL
SELECT 'orders sem cliente', count(*)
FROM orders o LEFT JOIN clients c ON c.id = o.client_id WHERE c.id IS NULL;

\echo ''
\echo '### 7. Vinculos de usuario (schema pre-r2a: sem status)'
SELECT market_code, count(*) AS vinculos FROM user_markets GROUP BY 1 ORDER BY 1;

\echo ''
\echo '### 8. Codigos de pedido: a unicidade composta vai aceitar?'
SELECT count(*) AS colisoes_market_owner_number FROM (
  SELECT market_code, number_owner_id, order_number
  FROM orders GROUP BY 1,2,3 HAVING count(*) > 1
) x;
SELECT count(*) AS orc_duplicado_por_mercado FROM (
  SELECT market_code, orc_id FROM orders GROUP BY 1,2 HAVING count(*) > 1
) y;

ROLLBACK;
