-- Separa o catálogo de Portugal do brasileiro.
--
-- Estado de partida, apurado em 06/10: os 122 SKUs de Portugal existiam só como
-- produtos BR. Preços em EUR, nomes pt-PT/inglês e IVA estavam em linhas EU
-- penduradas nos produtos BR (`product_markets`, `product_prices`). O catálogo
-- EU filtra `products.market_code = 'EU'` -- e nenhum produto era EU, então a
-- tela de Portugal abria vazia.
--
-- O que este script faz, numa transação:
--   1. cria no EU o catálogo, os tipos (sem grupo fiscal: tipo EU não herda
--      IPI), as categorias de opcional e os opcionais usados por esses SKUs;
--   2. cria os 122 produtos EU, cópias dos BR, com id próprio;
--   3. refaz os vínculos de opcionais e os componentes dos conjuntos;
--   4. MOVE para o produto EU as linhas EU que estavam no produto BR: preços em
--      EUR e `product_markets` (com o IVA 23% aprovado e os nomes corrigidos).
--
-- O que NÃO faz: tocar o Brasil. Os produtos BR, suas linhas BR, seus preços em
-- BRL, tipos, catálogos e opcionais ficam exatamente como estão.
--
-- Fotos: o produto EU nasce apontando para a foto do BR. A cópia para o bucket
-- europeu é feita depois, pela rota POST /api/v1/markets/EU/media/sync (o
-- código já impede que trocar ou apagar a foto EU alcance o arquivo do BR).
--
-- Nomes: o marcador dentro do INSERT em `alvo` é substituído pelo .ps1 com os
-- nomes pt-PT e inglês revisados (ops/nomes-eu-corrigidos.csv).
--
-- Uso:
--   .\ops\separar-catalogo-eu.ps1            (ensaio, termina em ROLLBACK)
--   .\ops\separar-catalogo-eu.ps1 -Aplicar   (grava)

\set ON_ERROR_STOP on

BEGIN;

CREATE TEMP TABLE alvo (
  product_code text PRIMARY KEY,
  pt text NOT NULL,
  en text NOT NULL
) ON COMMIT DROP;
INSERT INTO alvo (product_code, pt, en) VALUES
--NOMES--
;

-- ---------------------------------------------------------------------------
-- Guardas: abortam antes de escrever se o ponto de partida não é o esperado.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  n_alvo int; n_br int; n_eu int; n_pm int; n_sets int;
BEGIN
  SELECT count(*) INTO n_alvo FROM alvo;
  SELECT count(*) INTO n_br FROM alvo a
    JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR';
  SELECT count(*) INTO n_eu FROM alvo a
    JOIN products p ON p.product_code = a.product_code AND p.market_code = 'EU';
  SELECT count(*) INTO n_pm FROM alvo a
    JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR'
    JOIN product_markets pm ON pm.product_id = p.id AND pm.market_code = 'EU';
  SELECT count(*) INTO n_sets FROM alvo a
    JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR'
    JOIN product_set_items si ON si.set_id = p.id;
  IF n_br <> n_alvo THEN
    RAISE EXCEPTION 'Esperado % SKUs no BR, encontrados %', n_alvo, n_br;
  END IF;
  IF n_eu <> 0 THEN
    RAISE EXCEPTION 'Ja existem % desses SKUs no EU -- script ja aplicado?', n_eu;
  END IF;
  IF n_pm <> n_alvo THEN
    RAISE EXCEPTION 'Esperado % linhas EU em product_markets, encontradas %', n_alvo, n_pm;
  END IF;
  IF n_sets <> 0 THEN
    RAISE EXCEPTION 'Ha % itens de kit (product_set_items); este script nao os copia', n_sets;
  END IF;
  -- Acento perdido no caminho (pipe em ASCII) chega como '?'. Nenhum nome
  -- legítimo da lista tem '?', então qualquer um é sinal de texto corrompido.
  IF EXISTS (SELECT 1 FROM alvo WHERE pt LIKE '%?%' OR en LIKE '%?%') THEN
    RAISE EXCEPTION 'Nomes chegaram com "?": codificacao corrompida no envio';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM alvo WHERE pt LIKE '%Ç%') THEN
    RAISE EXCEPTION 'Nenhum nome com "Ç": acentos nao chegaram em UTF-8';
  END IF;
END $$;

\echo '=============================================='
\echo 'ANTES'
\echo '=============================================='
SELECT 'products EU' AS item, count(*) FROM products WHERE market_code = 'EU'
UNION ALL SELECT 'catalogs EU', count(*) FROM catalogs WHERE market_code = 'EU'
UNION ALL SELECT 'product_types EU', count(*) FROM product_types WHERE market_code = 'EU'
UNION ALL SELECT 'optional_categories EU', count(*) FROM optional_categories WHERE market_code = 'EU'
UNION ALL SELECT 'optionals EU', count(*) FROM optionals WHERE market_code = 'EU'
UNION ALL SELECT 'products BR', count(*) FROM products WHERE market_code = 'BR'
UNION ALL SELECT 'precos BR (listas BRL)', count(*) FROM product_prices pp
  JOIN price_lists pl ON pl.id = pp.price_list_id WHERE pl.market_code = 'BR';

-- ---------------------------------------------------------------------------
-- Mapas BR -> EU
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE mapa_produto ON COMMIT DROP AS
SELECT p.id AS br_id, gen_random_uuid() AS eu_id, a.product_code, a.pt, a.en
FROM alvo a
JOIN products p ON p.product_code = a.product_code AND p.market_code = 'BR';

-- Tipos: mesmo nome do BR (a tela traduz o tipo na exibição), com a grafia
-- corrigida onde ela impedia a tradução de casar: LUMINARIA, SOFA.
CREATE TEMP TABLE mapa_tipo ON COMMIT DROP AS
SELECT DISTINCT p.type AS br_name,
       CASE upper(btrim(p.type))
         WHEN 'LUMINARIA' THEN 'LUMINÁRIA'
         WHEN 'SOFA' THEN 'SOFÁ'
         ELSE p.type
       END AS eu_name
FROM mapa_produto m JOIN products p ON p.id = m.br_id;

CREATE TEMP TABLE mapa_opcional ON COMMIT DROP AS
SELECT br_id, gen_random_uuid() AS eu_id FROM (
  SELECT po.optional_id AS br_id
  FROM product_optionals po JOIN mapa_produto m ON m.br_id = po.product_id
  UNION
  SELECT link.optional_id
  FROM product_set_component_optionals link
  JOIN product_set_components c ON c.id = link.component_id
  JOIN mapa_produto m ON m.br_id = c.set_id
) usados;

CREATE TEMP TABLE mapa_componente ON COMMIT DROP AS
SELECT c.id AS br_id, gen_random_uuid() AS eu_id, m.eu_id AS eu_set_id
FROM product_set_components c JOIN mapa_produto m ON m.br_id = c.set_id;

\echo ''
\echo '=============================================='
\echo 'APLICANDO'
\echo '=============================================='

-- 1. Catálogo
INSERT INTO catalogs (id, market_code, name)
SELECT gen_random_uuid(), 'EU', c.name
FROM (SELECT DISTINCT p.catalog_id FROM mapa_produto m JOIN products p ON p.id = m.br_id
      WHERE p.catalog_id IS NOT NULL) usados
JOIN catalogs c ON c.id = usados.catalog_id
WHERE NOT EXISTS (SELECT 1 FROM catalogs x WHERE x.market_code = 'EU' AND x.name = c.name);
\echo '1. catalogos EU criados:'

CREATE TEMP TABLE mapa_catalogo ON COMMIT DROP AS
SELECT br.id AS br_id, eu.id AS eu_id
FROM catalogs br JOIN catalogs eu ON eu.name = br.name AND eu.market_code = 'EU'
WHERE br.market_code = 'BR';

-- 2. Tipos -- sem grupo fiscal: a API recusa tipo EU com grupo ("Tipo EU não
--    pode herdar grupo fiscal brasileiro"); o imposto EU vem do IVA por SKU.
INSERT INTO product_types (id, market_code, name, group_id)
SELECT gen_random_uuid(), 'EU', t.eu_name, NULL
FROM (SELECT DISTINCT eu_name FROM mapa_tipo) t
WHERE NOT EXISTS (SELECT 1 FROM product_types x WHERE x.market_code = 'EU' AND x.name = t.eu_name);
\echo '2. tipos EU criados:'

-- 3. Categorias de opcional -- `code` igual ao BR (é o que `optionals.category`
--    referencia); só o nome de exibição recebe acento onde faltava.
INSERT INTO optional_categories (id, market_code, name, code)
SELECT gen_random_uuid(), 'EU',
       replace(replace(replace(oc.name, 'SINTETICA', 'SINTÉTICA'), 'CERAMICA', 'CERÂMICA'), 'ALUMINIO', 'ALUMÍNIO'),
       oc.code
FROM optional_categories oc
WHERE oc.market_code = 'BR'
  AND oc.code IN (SELECT o.category FROM optionals o JOIN mapa_opcional mo ON mo.br_id = o.id)
  AND NOT EXISTS (SELECT 1 FROM optional_categories x WHERE x.market_code = 'EU' AND x.code = oc.code);
\echo '3. categorias de opcional EU criadas:'

-- 4. Opcionais
INSERT INTO optionals (id, market_code, category, color_name, photo_path)
SELECT mo.eu_id, 'EU', o.category, o.color_name, o.photo_path
FROM optionals o JOIN mapa_opcional mo ON mo.br_id = o.id;
\echo '4. opcionais EU criados:'

-- 5. Produtos. Preço em EUR vem das listas EU que já existiam; `price` espelha o
--    lojista (Bloco 62); `custo_desativado` está em BRL e não é lido -- zero.
INSERT INTO products (
  id, market_code, product_code, description, type, catalog_id,
  is_circular, is_set, altura, largura, profundidade,
  price, price_lojista, custo_desativado, price_corporativo,
  observacao, all_optionals_categories, photo_path, source_version, is_active
)
SELECT
  m.eu_id, 'EU', p.product_code, m.pt, mt.eu_name, mc.eu_id,
  p.is_circular, p.is_set, p.altura, p.largura, p.profundidade,
  coalesce(eu.lojista, 0), coalesce(eu.lojista, 0), 0, coalesce(eu.corporativo, 0),
  p.observacao, p.all_optionals_categories, p.photo_path, 1, p.is_active
FROM mapa_produto m
JOIN products p ON p.id = m.br_id
JOIN mapa_tipo mt ON mt.br_name = p.type
LEFT JOIN mapa_catalogo mc ON mc.br_id = p.catalog_id
LEFT JOIN LATERAL (
  SELECT max(pp.amount) FILTER (WHERE pl.code = 'lojista')     AS lojista,
         max(pp.amount) FILTER (WHERE pl.code = 'corporativo') AS corporativo
  FROM product_prices pp JOIN price_lists pl ON pl.id = pp.price_list_id
  WHERE pp.product_id = p.id AND pl.market_code = 'EU'
) eu ON true;
\echo '5. produtos EU criados:'

-- 6. Vínculos com opcionais
INSERT INTO product_optionals (product_id, optional_id)
SELECT m.eu_id, mo.eu_id
FROM product_optionals po
JOIN mapa_produto m ON m.br_id = po.product_id
JOIN mapa_opcional mo ON mo.br_id = po.optional_id;
\echo '6. vinculos produto-opcional EU:'

-- 7. Componentes dos conjuntos, com a mesma correção dos nomes de produto:
--    acento (SOFÁ), digitação (SEATLLE) e o termo pt-PT que o catálogo de
--    Portugal já usa para poltrona (CADEIRÃO).
INSERT INTO product_set_components (
  id, set_id, description, is_circular, altura, largura, profundidade, qty
)
SELECT mc.eu_id, mc.eu_set_id,
       btrim(regexp_replace(regexp_replace(regexp_replace(
         replace(replace(replace(replace(replace(c.description,
           'BRACOS', 'BRAÇOS'), 'ESPREGUICADEIRA', 'ESPREGUIÇADEIRA'),
           'C/ BCS', 'COM BRAÇOS'), 'S/ BCS', 'SEM BRAÇOS'), 'SEATLLE', 'SEATTLE'),
         '^SOFA\M', 'SOFÁ'),
         '^POLTRONA\M', 'CADEIRÃO'),
         '\s+', ' ', 'g')),
       c.is_circular, c.altura, c.largura, c.profundidade, c.qty
FROM product_set_components c JOIN mapa_componente mc ON mc.br_id = c.id;
\echo '7. componentes EU:'

INSERT INTO product_set_component_optionals (component_id, optional_id)
SELECT mc.eu_id, mo.eu_id
FROM product_set_component_optionals link
JOIN mapa_componente mc ON mc.br_id = link.component_id
JOIN mapa_opcional mo ON mo.br_id = link.optional_id;
\echo '7b. opcionais de componentes EU:'

-- 8. MOVE a linha EU de disponibilidade/IVA/nomes para o produto EU. O IVA 23%
--    aprovado (autor e data) vai junto -- não é reaprovado, é a mesma decisão.
UPDATE product_markets pm
SET product_id = m.eu_id,
    description_pt_pt = m.pt,
    description_en = m.en,
    updated_at = now()
FROM mapa_produto m
WHERE pm.product_id = m.br_id AND pm.market_code = 'EU';
\echo '8. linhas EU movidas para o produto EU:'

-- 9. MOVE os preços em EUR (listas EU) para o produto EU. Preços BRL ficam.
UPDATE product_prices pp
SET product_id = m.eu_id, updated_at = now()
FROM mapa_produto m, price_lists pl
WHERE pp.product_id = m.br_id
  AND pl.id = pp.price_list_id
  AND pl.market_code = 'EU';
\echo '9. precos EUR movidos:'

-- ---------------------------------------------------------------------------
-- Conferência: aborta se qualquer número divergir do esperado.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  n_alvo int; v int;
BEGIN
  SELECT count(*) INTO n_alvo FROM alvo;

  SELECT count(*) INTO v FROM products WHERE market_code = 'EU'
    AND product_code IN (SELECT product_code FROM alvo);
  IF v <> n_alvo THEN RAISE EXCEPTION 'produtos EU: % (esperado %)', v, n_alvo; END IF;

  SELECT count(*) INTO v FROM products p
    JOIN product_markets pm ON pm.product_id = p.id AND pm.market_code = 'EU'
   WHERE p.market_code = 'EU' AND pm.is_available
     AND pm.vat_status = 'approved' AND pm.vat_rate = 23.00
     AND p.product_code IN (SELECT product_code FROM alvo);
  IF v <> n_alvo THEN RAISE EXCEPTION 'EU disponivel com IVA 23 aprovado: % (esperado %)', v, n_alvo; END IF;

  SELECT count(*) INTO v FROM (
    SELECT p.id FROM products p
    JOIN product_prices pp ON pp.product_id = p.id
    JOIN price_lists pl ON pl.id = pp.price_list_id AND pl.market_code = 'EU'
    WHERE p.market_code = 'EU' AND p.product_code IN (SELECT product_code FROM alvo)
    GROUP BY p.id HAVING count(*) = 3
  ) x;
  IF v <> n_alvo THEN RAISE EXCEPTION 'EU com as 3 listas: % (esperado %)', v, n_alvo; END IF;

  -- os bloqueios que activate_europe verifica
  SELECT count(*) INTO v FROM products p
    WHERE p.market_code = 'EU'
      AND NOT EXISTS (SELECT 1 FROM product_types t WHERE t.market_code = 'EU' AND t.name = p.type);
  IF v <> 0 THEN RAISE EXCEPTION 'produto EU com tipo fora do EU: %', v; END IF;

  SELECT count(*) INTO v FROM products p
    WHERE p.market_code = 'EU' AND p.catalog_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM catalogs c WHERE c.id = p.catalog_id AND c.market_code = 'EU');
  IF v <> 0 THEN RAISE EXCEPTION 'produto EU com catalogo fora do EU: %', v; END IF;

  SELECT count(*) INTO v FROM product_optionals po
    JOIN products p ON p.id = po.product_id AND p.market_code = 'EU'
    JOIN optionals o ON o.id = po.optional_id AND o.market_code <> 'EU';
  IF v <> 0 THEN RAISE EXCEPTION 'produto EU com opcional fora do EU: %', v; END IF;

  SELECT count(*) INTO v FROM product_set_components c
    JOIN products p ON p.id = c.set_id AND p.market_code = 'EU'
    JOIN product_set_component_optionals l ON l.component_id = c.id
    JOIN optionals o ON o.id = l.optional_id AND o.market_code <> 'EU';
  IF v <> 0 THEN RAISE EXCEPTION 'componente EU com opcional fora do EU: %', v; END IF;

  -- o Brasil não pode ter perdido nada
  SELECT count(*) INTO v FROM products p
    WHERE p.market_code = 'BR' AND p.product_code IN (SELECT product_code FROM alvo);
  IF v <> n_alvo THEN RAISE EXCEPTION 'produtos BR da lista: % (esperado %)', v, n_alvo; END IF;
END $$;

\echo ''
\echo '=============================================='
\echo 'DEPOIS'
\echo '=============================================='
SELECT 'products EU' AS item, count(*) FROM products WHERE market_code = 'EU'
UNION ALL SELECT 'catalogs EU', count(*) FROM catalogs WHERE market_code = 'EU'
UNION ALL SELECT 'product_types EU', count(*) FROM product_types WHERE market_code = 'EU'
UNION ALL SELECT 'optional_categories EU', count(*) FROM optional_categories WHERE market_code = 'EU'
UNION ALL SELECT 'optionals EU', count(*) FROM optionals WHERE market_code = 'EU'
UNION ALL SELECT 'products BR', count(*) FROM products WHERE market_code = 'BR'
UNION ALL SELECT 'precos BR (listas BRL)', count(*) FROM product_prices pp
  JOIN price_lists pl ON pl.id = pp.price_list_id WHERE pl.market_code = 'BR';

\echo ''
\echo '--- Residuo BR->EU restante (esperado: so os 14 indisponiveis fora da lista) ---'
SELECT p.market_code AS mercado_produto, pm.market_code AS mercado_linha,
       pm.is_available, count(*) AS linhas
FROM product_markets pm JOIN products p ON p.id = pm.product_id
WHERE p.market_code <> pm.market_code
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

\echo ''
\echo '--- Tipos EU ---'
SELECT name FROM product_types WHERE market_code = 'EU' ORDER BY 1;

\echo ''
\echo '--- Categorias de opcional EU ---'
SELECT code, name FROM optional_categories WHERE market_code = 'EU' ORDER BY 1;

\echo ''
\echo '--- Nomes dos opcionais EU (revisar grafia) ---'
SELECT category, color_name FROM optionals WHERE market_code = 'EU' ORDER BY 1, 2;

\echo ''
\echo '--- Componentes EU (revisar grafia) ---'
SELECT DISTINCT c.description FROM product_set_components c
JOIN products p ON p.id = c.set_id AND p.market_code = 'EU' ORDER BY 1;

\echo ''
\echo '--- Amostra do catalogo EU como a tela vai mostrar ---'
SELECT p.product_code, p.type, left(pm.description_pt_pt, 34) AS pt,
       left(pm.description_en, 34) AS en, p.price_lojista AS eur_lojista, pm.vat_rate AS iva
FROM products p JOIN product_markets pm ON pm.product_id = p.id AND pm.market_code = 'EU'
WHERE p.market_code = 'EU' ORDER BY p.product_code LIMIT 10;
