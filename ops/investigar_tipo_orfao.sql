-- Investigação: produtos cujo `type` não casa com nenhum `product_types.name`
-- do mesmo mercado.
--
-- Por que importa: `products.type` é texto livre, não FK. Em
-- api/routers/orders.py:497 (criação) e :927 (edição) o IPI sai de
--
--     ipi_rate = _decimal(product_type.group.ipi) if product_type and
--                product_type.group else _ZERO
--
-- Com `type` órfão, `type_map.get(product.type)` devolve None e o imposto cai
-- para ZERO em silêncio -- exatamente o "IPI zero silencioso" que o Checkpoint
-- 06 proíbe. No EU o caminho equivalente (`_resolve_eu_vat`) RECUSA o pedido
-- quando o IVA está ausente; no BR, zera e emite.
--
-- A conciliação pós-corte de 06/10 contou 5 linhas com
-- `product_type_missing_same_market`. Aquela consulta só conta. Esta diz QUAIS
-- são, se já entraram em pedido e quanto imposto deixou de ser cobrado.
--
-- Nota sobre `order_items`: não existe coluna `subtotal`. O valor da linha é
-- calculado de `qty`, `unit_price` e `discount`, como em _calculate_order_line.
--
-- Somente leitura: abre READ ONLY e encerra com ROLLBACK. Nenhuma escrita.
--
-- Uso:
--   psql "$PRODUCTION_DATABASE_URL" -f ops/investigar_tipo_orfao.sql

BEGIN TRANSACTION READ ONLY;

\echo '### 1. Quais sao os produtos com tipo orfao'
SELECT
  p.product_code,
  left(p.description, 45)  AS descricao,
  p.market_code,
  p.type                   AS tipo_gravado_no_produto,
  (p.catalog_id IS NOT NULL) AS tem_catalogo
FROM products p
WHERE NOT EXISTS (
  SELECT 1 FROM product_types pt
  WHERE pt.name = p.type AND pt.market_code = p.market_code
)
ORDER BY p.market_code, p.product_code;

\echo ''
\echo '### 2. O tipo existe em OUTRO mercado? (erro de backfill vs. digitacao)'
SELECT
  p.product_code,
  p.type              AS tipo_do_produto,
  p.market_code       AS mercado_do_produto,
  pt.market_code      AS tipo_existe_no_mercado
FROM products p
LEFT JOIN product_types pt ON pt.name = p.type
WHERE NOT EXISTS (
  SELECT 1 FROM product_types x
  WHERE x.name = p.type AND x.market_code = p.market_code
)
ORDER BY p.product_code;

\echo ''
\echo '### 3. Existe tipo parecido no mesmo mercado? (candidato a correcao)'
SELECT DISTINCT
  p.product_code,
  p.type        AS tipo_gravado,
  pt.name       AS tipo_existente_parecido,
  pg.ipi        AS ipi_que_seria_aplicado
FROM products p
JOIN product_types pt
  ON pt.market_code = p.market_code
 AND (upper(btrim(pt.name)) = upper(btrim(coalesce(p.type, '')))
      OR pt.name ILIKE '%' || btrim(coalesce(p.type, '')) || '%'
      OR btrim(coalesce(p.type, '')) ILIKE '%' || pt.name || '%')
LEFT JOIN product_groups pg ON pg.id = pt.group_id
WHERE NOT EXISTS (
  SELECT 1 FROM product_types x
  WHERE x.name = p.type AND x.market_code = p.market_code
)
  AND coalesce(btrim(p.type), '') <> ''
ORDER BY p.product_code, pt.name;

\echo ''
\echo '### 4. O QUE MAIS IMPORTA: algum ja entrou em pedido?'
WITH orfaos AS (
  SELECT p.product_code
  FROM products p
  WHERE NOT EXISTS (
    SELECT 1 FROM product_types pt
    WHERE pt.name = p.type AND pt.market_code = p.market_code
  )
)
SELECT
  oi.product_code,
  count(DISTINCT o.id)    AS pedidos,
  sum(oi.qty)             AS unidades,
  round(sum(oi.qty * oi.unit_price * (1 - oi.discount / 100.0)), 2) AS valor_sem_imposto,
  sum(oi.ipi_value)       AS imposto_cobrado,
  max(oi.ipi_rate)        AS maior_aliquota,
  count(*) FILTER (WHERE oi.ipi_rate = 0) AS linhas_com_aliquota_zero,
  min(o.created_at)::date AS primeiro_pedido,
  max(o.created_at)::date AS ultimo_pedido
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN orfaos ON orfaos.product_code = oi.product_code
GROUP BY oi.product_code
ORDER BY 4 DESC;

\echo ''
\echo '--- detalhe por pedido, para conferir caso a caso ---'
WITH orfaos AS (
  SELECT p.product_code
  FROM products p
  WHERE NOT EXISTS (
    SELECT 1 FROM product_types pt
    WHERE pt.name = p.type AND pt.market_code = p.market_code
  )
)
-- `orders` nao tem coluna `status`: o estado e dois booleanos.
SELECT
  o.code,
  o.market_code,
  o.created_at::date AS data,
  o.is_finalized,
  o.is_cancelled,
  oi.product_code,
  oi.qty,
  oi.unit_price,
  oi.discount,
  oi.ipi_rate,
  oi.ipi_value,
  oi.tax_label
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN orfaos ON orfaos.product_code = oi.product_code
ORDER BY o.created_at DESC, oi.product_code;

\echo ''
\echo '### 5. Contexto: os tipos que EXISTEM, para escolher o certo'
SELECT
  pt.market_code,
  pt.name        AS tipo,
  pg.name        AS grupo,
  pg.ipi         AS ipi_do_grupo
FROM product_types pt
LEFT JOIN product_groups pg ON pg.id = pt.group_id
ORDER BY pt.market_code, pt.name;

\echo ''
\echo '### 6b. Os outros 4 orfaos ja foram vendidos alguma vez?'
-- A secao 4 mostrou so os que tem pedido. Esta confirma o silencio dos demais:
-- se nunca entraram em pedido, o risco e prospectivo, nao retroativo.
SELECT
  p.product_code,
  p.type,
  (SELECT count(*) FROM order_items oi WHERE oi.product_code = p.product_code) AS linhas_em_pedido
FROM products p
WHERE NOT EXISTS (
  SELECT 1 FROM product_types pt
  WHERE pt.name = p.type AND pt.market_code = p.market_code
)
ORDER BY 3 DESC, 1;

\echo ''
\echo '### 6c. Quantos produtos casam o tipo apenas ignorando a caixa?'
-- Se este numero for alto, o problema nao e cadastro pontual: e a comparacao
-- exata em ProductType.name.in_(type_names), que nao normaliza caixa.
SELECT count(*) AS produtos_que_casariam_ignorando_caixa
FROM products p
WHERE NOT EXISTS (
    SELECT 1 FROM product_types pt
    WHERE pt.name = p.type AND pt.market_code = p.market_code
  )
  AND EXISTS (
    SELECT 1 FROM product_types pt
    WHERE upper(btrim(pt.name)) = upper(btrim(p.type))
      AND pt.market_code = p.market_code
  );

\echo ''
\echo '### 6d. Distribuicao de aliquota nos itens de pedido (ha outros zerados?)'
-- A pergunta mais ampla: o IPI zero silencioso atingiu alguem fora destes 5?
SELECT
  oi.tax_label,
  oi.ipi_rate,
  count(*) AS linhas,
  count(DISTINCT oi.order_id) AS pedidos
FROM order_items oi
GROUP BY 1, 2
ORDER BY 1, 2;

\echo ''
\echo '### 7. Ha produto com tipo vazio ou nulo? (caso diferente, mesmo efeito)'
SELECT
  count(*) FILTER (WHERE p.type IS NULL)            AS tipo_nulo,
  count(*) FILTER (WHERE btrim(coalesce(p.type,'')) = '') AS tipo_vazio
FROM products p;

ROLLBACK;
