-- Abertura de Portugal: IVA 23% aprovado nos 122 SKUs, acesso e mercado.
--
-- Contexto, apurado em 06/10: o cadastro EU JÁ EXISTE. Os 122 SKUs têm os 366
-- preços em EUR (três listas × 122), e `product_markets` tem as linhas EU com
-- `vat_rate` preenchido. O que está errado é a taxa: 3,25% e 9,75% são
-- alíquotas de IPI brasileiro, herdadas do grupo fiscal BR quando as linhas
-- foram criadas -- exatamente o que o Checkpoint 06 passou a proibir. Portugal
-- usa 23%.
--
-- Por que SQL direto e não o endpoint `PUT /EU/products/{id}/vat`:
-- `_apply_vat_decision` exige `Product.market_code = 'EU'`, e estes produtos
-- são BR com disponibilidade EU via `product_markets`. O endpoint devolveria
-- 404 para todos.
--
-- A aprovação é indivisível por constraint (`ck_product_markets_vat_approval`):
-- `approved` exige taxa, autor e data juntos. Os quatro são gravados.
--
-- Os 14 SKUs fora da lista (IAC0134..IAC0146, luminárias LED) ficam como estão:
-- `is_available = false` e `pending`. Não bloqueiam a ativação, porque
-- `activate_europe` só verifica SKUs disponíveis. Decisão do usuário em 06/10.
--
-- Uso:
--   .\ops\abrir-portugal.ps1 -Email "admin@ilya.com"            (ensaio)
--   .\ops\abrir-portugal.ps1 -Email "admin@ilya.com" -Aplicar   (grava)

\set ON_ERROR_STOP on

BEGIN;

\echo '=============================================='
\echo 'ANTES'
\echo '=============================================='

\echo ''
\echo '--- IVA atual dos SKUs da lista ---'
WITH alvo AS (SELECT unnest(ARRAY[--SKUS--]) AS product_code)
SELECT pm.vat_rate, pm.vat_status, pm.vat_source, pm.is_available, count(*) AS linhas
FROM alvo a
JOIN products p ON p.product_code = a.product_code
JOIN product_markets pm ON pm.product_id = p.id AND pm.market_code = 'EU'
GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;

\echo ''
\echo '--- Mercado e vinculo do usuario ---'
SELECT code, is_enabled FROM markets WHERE code = 'EU';
SELECT u.email, um.market_code, um.status, coalesce(um.role,'(nulo)') AS role
FROM users u JOIN user_markets um ON um.user_id = u.id
WHERE lower(u.email) = lower(:'alvo') ORDER BY um.market_code;

\echo ''
\echo '=============================================='
\echo 'APLICANDO'
\echo '=============================================='

-- 1. IVA 23% aprovado nominalmente nos 122 SKUs da lista.
--    `vat_source` registra a procedência honestamente: aprovação em lote por
--    SQL, não pelo fluxo da aplicação. Quem auditar vê como entrou.
WITH alvo AS (SELECT unnest(ARRAY[--SKUS--]) AS product_code),
     aprovador AS (SELECT id FROM users WHERE lower(email) = lower(:'alvo'))
UPDATE product_markets pm
SET vat_rate = 23.00,
    vat_status = 'approved',
    vat_source = 'manual_sql_20261006',
    approved_by_user_id = (SELECT id FROM aprovador),
    approved_at = now()
FROM products p, alvo a
WHERE pm.product_id = p.id
  AND pm.market_code = 'EU'
  AND p.product_code = a.product_code
  AND (SELECT count(*) FROM aprovador) = 1;
\echo '1. SKUs com IVA 23% aprovado:'

-- 2. Mercado EU habilitado.
UPDATE markets SET is_enabled = true WHERE code = 'EU' AND is_enabled = false;
\echo '2. mercado EU habilitado:'

-- 3. Vinculo do usuario. `allowed_market_accesses` exige status='active' E
--    role NOT NULL; a rbac_r2a deixou os dois pendentes de proposito.
--    Vinculos comerciais vao a NULL por ck_user_markets_role_links.
UPDATE user_markets um
SET status = 'active', role = 'admin', linked_client_id = NULL, rep_id = NULL
FROM users u
WHERE u.id = um.user_id
  AND lower(u.email) = lower(:'alvo')
  AND um.market_code = 'EU';
\echo '3. vinculo EU ativado:'

\echo ''
\echo '=============================================='
\echo 'DEPOIS'
\echo '=============================================='

\echo ''
\echo '--- IVA dos SKUs da lista ---'
WITH alvo AS (SELECT unnest(ARRAY[--SKUS--]) AS product_code)
SELECT pm.vat_rate, pm.vat_status, pm.is_available, count(*) AS linhas
FROM alvo a
JOIN products p ON p.product_code = a.product_code
JOIN product_markets pm ON pm.product_id = p.id AND pm.market_code = 'EU'
GROUP BY 1,2,3 ORDER BY 1,2,3;

\echo ''
\echo '--- Os de fora da lista seguem intocados ---'
WITH alvo AS (SELECT unnest(ARRAY[--SKUS--]) AS product_code)
SELECT pm.vat_rate, pm.vat_status, pm.is_available, count(*) AS linhas
FROM product_markets pm
JOIN products p ON p.id = pm.product_id
LEFT JOIN alvo a ON a.product_code = p.product_code
WHERE pm.market_code = 'EU' AND a.product_code IS NULL
GROUP BY 1,2,3 ORDER BY 1,2,3;

\echo ''
\echo '--- Mercado e vinculo ---'
SELECT code, is_enabled FROM markets WHERE code = 'EU';
SELECT u.email, um.market_code, um.status, coalesce(um.role,'(nulo)') AS role
FROM users u JOIN user_markets um ON um.user_id = u.id
WHERE lower(u.email) = lower(:'alvo') ORDER BY um.market_code;

\echo ''
\echo '--- Outros vinculos EU seguem pendentes (revisao nominal) ---'
SELECT status, coalesce(role,'(nulo)') AS role, count(*) FROM user_markets
WHERE market_code = 'EU' GROUP BY 1,2 ORDER BY 1,2;

\echo ''
\echo '--- Bloqueio restante para venda em Portugal (esperado 0) ---'
SELECT 'SKU disponivel sem IVA aprovado' AS bloqueio, count(*) AS linhas
FROM product_markets pm
WHERE pm.market_code = 'EU' AND pm.is_available IS TRUE
  AND (pm.vat_status IS DISTINCT FROM 'approved' OR pm.vat_rate IS NULL);

\echo ''
\echo '--- Amostra: preco EUR + IVA 23% ---'
WITH alvo AS (SELECT unnest(ARRAY[--SKUS--]) AS product_code)
SELECT p.product_code, left(p.description,22) AS descricao,
       max(CASE WHEN pl.code='lojista' THEN pp.amount END) AS eur_lojista,
       max(pm.vat_rate) AS iva,
       round(max(CASE WHEN pl.code='lojista' THEN pp.amount END) * 1.23, 2) AS com_iva
FROM alvo a
JOIN products p ON p.product_code = a.product_code
JOIN product_markets pm ON pm.product_id = p.id AND pm.market_code = 'EU'
JOIN product_prices pp ON pp.product_id = p.id
JOIN price_lists pl ON pl.id = pp.price_list_id AND pl.market_code = 'EU'
GROUP BY p.product_code, p.description ORDER BY p.product_code LIMIT 8;
