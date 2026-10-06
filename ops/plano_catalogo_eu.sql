-- O que precisa ser criado no EU para receber os 122 SKUs da lista.
--
-- Contexto: `import_europe_catalog` preenche preço e IVA de produtos EU que já
-- existam -- a docstring é explícita, "a importação nunca cria ou copia um
-- produto BR", e SKU inexistente rejeita o arquivo inteiro. Então antes dela
-- precisam existir no mercado EU: as três listas de preço, os tipos, os
-- catálogos e os próprios produtos.
--
-- Esta consulta levanta exatamente o que falta, a partir do que os 122 SKUs
-- usam hoje no BR. Não escreve nada.
--
-- A lista de códigos entra por \copy FROM PSTDIN, logo após o BEGIN.
--
-- Somente leitura: READ ONLY + ROLLBACK.
--
-- Uso:
--   .\ops\plano-catalogo-eu.ps1

BEGIN TRANSACTION READ ONLY;

-- A lista entra como VIEW sobre VALUES: `READ ONLY` recusa CREATE TEMP TABLE,
-- e uma view temporaria tambem seria escrita. O .ps1 substitui o marcador
-- abaixo pelos codigos.

\echo '### 1. Os codigos da lista existem no BR?'
SELECT
  (SELECT count(*) FROM (SELECT unnest(ARRAY[--SKUS--])) x)                                    AS codigos_na_lista,
  (SELECT count(*) FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a JOIN products p
     ON p.product_code = a.product_code AND p.market_code = 'BR') AS encontrados_no_br,
  (SELECT count(*) FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a JOIN products p
     ON p.product_code = a.product_code AND p.market_code = 'EU') AS ja_existem_no_eu;

\echo ''
\echo '--- Codigos da lista que NAO existem no BR (esperado: nenhum) ---'
SELECT a.product_code
FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a
WHERE NOT EXISTS (
  SELECT 1 FROM products p
  WHERE p.product_code = a.product_code AND p.market_code = 'BR'
)
ORDER BY 1;

\echo ''
\echo '### 2. Tipos que precisam existir no EU'
SELECT p.type AS tipo_no_br, count(*) AS skus,
       (SELECT count(*) FROM product_types pt
         WHERE pt.market_code = 'EU' AND pt.name = p.type) AS ja_existe_no_eu
FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a
JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR'
GROUP BY p.type
ORDER BY 2 DESC, 1;

\echo ''
\echo '### 3. Catalogos que precisam existir no EU'
SELECT coalesce(c.name, '(sem catalogo)') AS catalogo_no_br, count(*) AS skus,
       (SELECT count(*) FROM catalogs c2
         WHERE c2.market_code = 'EU' AND c2.name = c.name) AS ja_existe_no_eu
FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a
JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR'
LEFT JOIN catalogs c ON c.id = p.catalog_id
GROUP BY c.name
ORDER BY 2 DESC, 1;

\echo ''
\echo '### 4. Listas de preco: as tres EU em EUR existem?'
SELECT market_code, code, name, currency FROM price_lists
ORDER BY market_code, code;

\echo ''
\echo '### 5. Opcionais: quantos da lista tem opcional vinculado?'
-- Produto EU com opcional de outro mercado bloqueia a ativacao
-- (activate_europe verifica isso). Se o numero for alto, os opcionais tambem
-- precisam ser cadastrados no EU antes.
SELECT
  count(DISTINCT p.id) FILTER (WHERE po.product_id IS NOT NULL) AS skus_com_opcional,
  count(DISTINCT o.id)                                          AS opcionais_distintos
FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a
JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR'
LEFT JOIN product_optionals po ON po.product_id = p.id
LEFT JOIN optionals o ON o.id = po.optional_id;

\echo ''
\echo '### 6. Precos BR atuais (referencia para definir o preco em EUR)'
SELECT
  count(*) FILTER (WHERE p.price_lojista IS NOT NULL)     AS com_preco_lojista,
  count(*) FILTER (WHERE p.price_corporativo IS NOT NULL) AS com_preco_corporativo,
  min(p.price_lojista)  AS menor_lojista,
  max(p.price_lojista)  AS maior_lojista
FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a
JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR';

\echo ''
\echo '### 7. A lista com tipo, catalogo e precos BR'
SELECT p.product_code, left(p.description, 30) AS descricao, p.type,
       coalesce(c.name, '-') AS catalogo,
       p.price_lojista, p.price_corporativo
FROM (SELECT unnest(ARRAY[--SKUS--]) AS product_code) a
JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR'
LEFT JOIN catalogs c ON c.id = p.catalog_id
ORDER BY p.product_code;

ROLLBACK;
