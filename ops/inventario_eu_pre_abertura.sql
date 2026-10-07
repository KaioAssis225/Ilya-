-- Inventário dos SKUs do mercado EU, antes de aprovar IVA e ativar.
--
-- Por que existe: `POST /platform/markets/EU/activate` recusa a ativação se
-- houver QUALQUER SKU disponível sem IVA aprovado, sem as três listas de preço
-- ou com tipo/catálogo/opcional fora do mercado EU. Este script mostra o estado
-- de cada uma dessas exigências ANTES de tentar, para a ativação não ser
-- tentativa e erro contra produção.
--
-- Responde o que precisa ser decidido:
--   1. quantos e quais SKUs estão marcados como disponíveis no EU
--   2. quais já têm IVA e em que estado (approved / pending / rejected)
--   3. quais têm as três listas de preço
--   4. quais têm tipo, catálogo ou opcional que não é do EU
--
-- Somente leitura: READ ONLY + ROLLBACK.
--
-- Uso:
--   .\ops\inventario-eu.ps1

BEGIN TRANSACTION READ ONLY;

\echo '### 1. Trava de abertura: estado atual'
SELECT code, currency, locale, tax_label, is_enabled FROM markets ORDER BY code;

\echo ''
\echo '### 2. Quantos produtos existem no EU, e quantos estao disponiveis'
SELECT
  count(*)                                              AS produtos_market_eu,
  count(*) FILTER (WHERE pm.is_available IS TRUE)       AS marcados_disponiveis,
  count(*) FILTER (WHERE pm.product_id IS NULL)         AS sem_linha_product_markets
FROM products p
LEFT JOIN product_markets pm
       ON pm.product_id = p.id AND pm.market_code = 'EU'
WHERE p.market_code = 'EU';

\echo ''
\echo '### 3. Estado do IVA nos SKUs disponiveis (o que a ativacao exige)'
SELECT
  coalesce(pm.vat_status, '(nulo)') AS vat_status,
  pm.vat_rate,
  count(*) AS skus
FROM products p
JOIN product_markets pm
  ON pm.product_id = p.id AND pm.market_code = 'EU'
WHERE p.market_code = 'EU' AND pm.is_available IS TRUE
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '### 4. LISTA NOMINAL: cada SKU disponivel e o que falta nele'
SELECT
  p.product_code,
  left(p.description, 38)            AS descricao,
  p.type                             AS tipo,
  coalesce(pm.vat_status, '(nulo)')  AS iva_status,
  pm.vat_rate                        AS iva_taxa,
  (SELECT count(*) FROM product_prices pp
     JOIN price_lists pl ON pl.id = pp.price_list_id AND pl.market_code = 'EU'
    WHERE pp.product_id = p.id)      AS listas_de_preco,
  (SELECT count(*) FROM product_types pt
    WHERE pt.market_code = 'EU' AND pt.name = p.type) AS tipo_existe_no_eu,
  CASE WHEN p.catalog_id IS NULL THEN 'sem catalogo'
       WHEN EXISTS (SELECT 1 FROM catalogs c
                     WHERE c.id = p.catalog_id AND c.market_code = 'EU')
         THEN 'catalogo EU'
       ELSE 'CATALOGO FORA DO EU' END AS catalogo
FROM products p
JOIN product_markets pm
  ON pm.product_id = p.id AND pm.market_code = 'EU'
WHERE p.market_code = 'EU' AND pm.is_available IS TRUE
ORDER BY p.product_code;

\echo ''
\echo '### 5. Os bloqueios da ativacao, contados (tudo zero = pode ativar)'
WITH disponiveis AS (
  SELECT p.id, p.product_code, p.type, p.catalog_id, pm.vat_status, pm.vat_rate
  FROM products p
  JOIN product_markets pm
    ON pm.product_id = p.id AND pm.market_code = 'EU'
  WHERE p.market_code = 'EU' AND pm.is_available IS TRUE
)
SELECT 'sem IVA aprovado' AS bloqueio, count(*) AS skus
FROM disponiveis
WHERE vat_status IS DISTINCT FROM 'approved' OR vat_rate IS NULL
UNION ALL
SELECT 'sem as tres listas de preco', count(*)
FROM disponiveis d
WHERE (SELECT count(*) FROM product_prices pp
         JOIN price_lists pl ON pl.id = pp.price_list_id AND pl.market_code = 'EU'
        WHERE pp.product_id = d.id) <> 3
UNION ALL
SELECT 'tipo nao existe no EU', count(*)
FROM disponiveis d
WHERE NOT EXISTS (SELECT 1 FROM product_types pt
                   WHERE pt.market_code = 'EU' AND pt.name = d.type)
UNION ALL
SELECT 'catalogo fora do EU', count(*)
FROM disponiveis d
WHERE d.catalog_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM catalogs c
                   WHERE c.id = d.catalog_id AND c.market_code = 'EU')
UNION ALL
SELECT 'opcional fora do EU', count(*)
FROM disponiveis d
WHERE EXISTS (SELECT 1 FROM product_optionals po
                JOIN optionals o ON o.id = po.optional_id
               WHERE po.product_id = d.id AND o.market_code <> 'EU');

\echo ''
\echo '### 6. Pessoas no EU: a ativacao exige o pais de lancamento'
SELECT 'clients' AS tabela, coalesce(country, '(nulo)') AS pais, count(*) AS linhas
FROM clients WHERE market_code = 'EU' GROUP BY 1, 2
UNION ALL
SELECT 'representatives', coalesce(country, '(nulo)'), count(*)
FROM representatives
WHERE market_code = 'EU' AND relationship_ended_at IS NULL
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '### 7. Listas de preco, tipos e catalogos no EU (contexto)'
SELECT 'price_lists' AS entidade, name AS nome FROM price_lists WHERE market_code = 'EU'
UNION ALL
SELECT 'product_types', name FROM product_types WHERE market_code = 'EU'
UNION ALL
SELECT 'catalogs', name FROM catalogs WHERE market_code = 'EU'
ORDER BY 1, 2;

ROLLBACK;
