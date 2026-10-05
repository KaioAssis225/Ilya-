-- Conciliação somente leitura do schema BR/EU.
-- Uso: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ops/reconcile_multimarket.sql
-- Não retorna PII, UUIDs, textos de pedidos ou valores de preço individuais.
-- Resultados marcados como "esperado zero" devem estar vazios antes do corte.

BEGIN TRANSACTION READ ONLY;

-- Head da migration e disponibilidade operacional de cada mercado.
SELECT version_num AS alembic_head FROM alembic_version;
SELECT code, currency, locale, tax_label, is_enabled
FROM markets
ORDER BY code;

-- Coortes comerciais e seus países já persistidos.
SELECT 'clients' AS entity, market_code, country, count(*) AS rows
FROM clients
GROUP BY market_code, country
UNION ALL
SELECT 'representatives', market_code, country, count(*)
FROM representatives
GROUP BY market_code, country
ORDER BY entity, market_code, country;

-- Pedidos são snapshots: comparar estado e total agregado, sem recalcular.
SELECT market_code,
       currency,
       locale,
       is_finalized,
       is_cancelled,
       count(*) AS orders,
       coalesce(sum(total_value), 0) AS total_value,
       coalesce(sum(total_ipi), 0) AS total_tax,
       coalesce(sum(total_with_ipi), 0) AS total_with_tax
FROM orders
GROUP BY market_code, currency, locale, is_finalized, is_cancelled
ORDER BY market_code, currency, locale, is_finalized, is_cancelled;

-- Filhos de pedido devem herdar o mercado do pai. Esperado zero em ambos.
SELECT 'order_items_without_parent' AS check_name, count(*) AS rows
FROM order_items item
LEFT JOIN orders ord ON ord.id = item.order_id
WHERE ord.id IS NULL
UNION ALL
SELECT 'order_history_without_parent', count(*)
FROM order_history history
LEFT JOIN orders ord ON ord.id = history.order_id
WHERE ord.id IS NULL;

-- Referências comerciais de pedidos não podem cruzar mercados. Esperado zero.
SELECT 'orders_client_cross_market' AS check_name, count(*) AS rows
FROM orders ord
JOIN clients client ON client.id = ord.client_id
WHERE client.market_code <> ord.market_code
UNION ALL
SELECT 'orders_rep_cross_market', count(*)
FROM orders ord
JOIN representatives rep ON rep.id = ord.rep_id
WHERE rep.market_code <> ord.market_code;

-- Acesso comercial efetivo: papel e status pertencem ao vínculo, não a users.role.
SELECT market_code, status, coalesce(role, '(null)') AS commercial_role,
       count(*) AS links
FROM user_markets
GROUP BY market_code, status, role
ORDER BY market_code, status, commercial_role;

-- Toda identidade comercial ativa precisa de vínculo explícito para home_market.
-- Esperado zero; home_market não é uma concessão de acesso.
SELECT 'active_users_without_home_link' AS check_name, count(*) AS rows
FROM users usr
WHERE usr.is_active
  AND NOT EXISTS (
      SELECT 1 FROM user_markets access
      WHERE access.user_id = usr.id
        AND access.market_code = usr.home_market
  );

-- Vínculos de cliente e representante só podem apontar ao mesmo mercado.
-- Esperado zero em ambas as consultas.
SELECT 'user_market_client_cross_market' AS check_name, count(*) AS rows
FROM user_markets access
JOIN clients client ON client.id = access.linked_client_id
WHERE client.market_code <> access.market_code
UNION ALL
SELECT 'user_market_rep_cross_market', count(*)
FROM user_markets access
JOIN representatives rep ON rep.id = access.rep_id
WHERE rep.market_code <> access.market_code;

-- Produto, preço e dimensões comerciais por mercado.
SELECT 'products' AS entity, market_code, count(*) AS rows
FROM products
GROUP BY market_code
UNION ALL
SELECT 'catalogs', market_code, count(*)
FROM catalogs
GROUP BY market_code
UNION ALL
SELECT 'product_types', market_code, count(*)
FROM product_types
GROUP BY market_code
UNION ALL
SELECT 'optional_categories', market_code, count(*)
FROM optional_categories
GROUP BY market_code
UNION ALL
SELECT 'optionals', market_code, count(*)
FROM optionals
GROUP BY market_code
ORDER BY entity, market_code;

-- Este diagnóstico expõe os vínculos ProductMarket em outro mercado que o
-- produto. No snapshot anterior ao corte, as 136 linhas EU legadas são
-- evidência preservada e ficam inertes; após o cadastro manual EU, o resultado
-- deve voltar a zero antes da habilitação de EU.
SELECT product.market_code AS product_market,
       availability.market_code AS availability_market,
       count(*) AS rows
FROM product_markets availability
JOIN products product ON product.id = availability.product_id
WHERE product.market_code <> availability.market_code
GROUP BY product.market_code, availability.market_code
ORDER BY product_market, availability_market;

-- Produto e lista de preço em mercados distintos são evidência legada enquanto
-- o produto EU ainda não foi cadastrado manualmente. Antes de habilitar EU,
-- nenhuma linha operacional EU pode permanecer nessa condição.
SELECT 'product_prices_cross_market' AS check_name, count(*) AS rows
FROM product_prices price
JOIN products product ON product.id = price.product_id
JOIN price_lists list ON list.id = price.price_list_id
WHERE product.market_code <> list.market_code;

-- Dimensões referenciadas pelo produto devem existir no mesmo mercado.
-- Produtos sem catálogo continuam permitidos.
SELECT 'product_type_missing_same_market' AS check_name, count(*) AS rows
FROM products product
WHERE NOT EXISTS (
    SELECT 1 FROM product_types product_type
    WHERE product_type.name = product.type
      AND product_type.market_code = product.market_code
)
UNION ALL
SELECT 'catalog_cross_market', count(*)
FROM products product
JOIN catalogs catalog ON catalog.id = product.catalog_id
WHERE catalog.market_code <> product.market_code;

-- IVA EU só pode ser liberado por decisão nominal; este agregado não revela SKU.
SELECT market_code,
       vat_status,
       vat_source,
       count(*) AS rows,
       count(*) FILTER (WHERE vat_rate IS NULL) AS missing_rate,
       count(*) FILTER (WHERE approved_by_user_id IS NULL) AS missing_approver
FROM product_markets
WHERE market_code = 'EU'
GROUP BY market_code, vat_status, vat_source
ORDER BY vat_status, vat_source;

-- Sessões e contadores, sempre em agregados.
SELECT scope,
       active_market,
       revoked,
       count(*) AS tokens
FROM refresh_tokens
GROUP BY scope, active_market, revoked
ORDER BY scope, active_market, revoked;

SELECT market_code, count(*) AS counter_rows, min(next_value) AS minimum_next_value
FROM market_order_counters
GROUP BY market_code
UNION ALL
SELECT market_code, 1, next_value
FROM market_quote_counters
ORDER BY market_code;

-- A outbox continua global por decisão de escopo. Reportar sem classificá-la.
SELECT event_type, status, count(*) AS events
FROM integration_outbox
GROUP BY event_type, status
ORDER BY event_type, status;

ROLLBACK;
