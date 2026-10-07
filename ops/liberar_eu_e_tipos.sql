-- Duas correções pedidas em 06/10, numa transação única.
--
--   A. Liberar os 5 produtos BR que o PR #80 passou a recusar.
--   B. Dar acesso à tela de Portugal para UM usuário nomeado.
--
-- NÃO aprova IVA e NÃO torna Portugal operacional para venda: sem
-- `vat_status='approved'`, `_resolve_eu_vat` segue recusando qualquer pedido EU.
-- Isso é deliberado -- a aprovação fiscal é decisão separada.
--
-- Como rodar: o .ps1 companheiro mostra o ANTES, pede confirmação e só então
-- faz COMMIT. Sem confirmação, faz ROLLBACK e nada muda.
--
-- Uso:
--   .\ops\liberar-eu-e-tipos.ps1 -Email "seu@email"            (so mostra)
--   .\ops\liberar-eu-e-tipos.ps1 -Email "seu@email" -Aplicar   (aplica)

\set ON_ERROR_STOP on

BEGIN;

\echo '=============================================='
\echo 'ANTES'
\echo '=============================================='

\echo ''
\echo '--- A. Os produtos BR com tipo orfao (os 5 bloqueados) ---'
SELECT p.product_code, p.type AS tipo_atual
FROM products p
WHERE NOT EXISTS (
  SELECT 1 FROM product_types pt
  WHERE pt.name = p.type AND pt.market_code = p.market_code
)
ORDER BY p.product_code;

\echo ''
\echo '--- B. Mercado EU e o vinculo do usuario alvo ---'
SELECT code, is_enabled FROM markets WHERE code = 'EU';
SELECT u.email, um.market_code, um.status, coalesce(um.role, '(nulo)') AS role,
       um.linked_client_id, um.rep_id
FROM users u
JOIN user_markets um ON um.user_id = u.id
WHERE lower(u.email) = lower(:'alvo')
ORDER BY um.market_code;

\echo ''
\echo '--- B0. Se a consulta acima veio vazia, o e-mail nao existe. Contas com vinculo EU: ---'
SELECT u.email, u.username, left(u.full_name, 28) AS nome, u.role AS papel_global,
       u.is_active, um.status AS status_eu, coalesce(um.role, '(nulo)') AS role_eu
FROM users u
JOIN user_markets um ON um.user_id = u.id AND um.market_code = 'EU'
ORDER BY u.email;

\echo ''
\echo '--- B0b. Contas admin (caso a sua nao tenha vinculo EU nenhum) ---'
SELECT u.email, u.username, left(u.full_name, 28) AS nome, u.is_active,
       string_agg(um.market_code || '=' || um.status, ', ' ORDER BY um.market_code) AS vinculos
FROM users u
LEFT JOIN user_markets um ON um.user_id = u.id
WHERE u.role = 'admin'
GROUP BY u.email, u.username, u.full_name, u.is_active
ORDER BY u.email;

\echo ''
\echo '--- B0c. Portugal: ha SKU disponivel? (o /activate exige >= 1) ---'
SELECT
  count(*)                                        AS produtos_market_eu,
  count(pm.product_id)                            AS com_linha_product_markets,
  count(*) FILTER (WHERE pm.is_available IS TRUE) AS marcados_disponiveis,
  count(*) FILTER (WHERE pm.vat_status = 'approved' AND pm.vat_rate IS NOT NULL)
                                                  AS com_iva_aprovado
FROM products p
LEFT JOIN product_markets pm
       ON pm.product_id = p.id AND pm.market_code = 'EU'
WHERE p.market_code = 'EU';

\echo ''
\echo '=============================================='
\echo 'APLICANDO'
\echo '=============================================='

-- ---------------------------------------------------------------------------
-- A. Os 5 produtos
-- ---------------------------------------------------------------------------

-- A1. Banquetas: diferenca de caixa. 'Banqueta' -> 'BANQUETA', que ja existe.
--     Nao cria tipo: o tipo correto esta cadastrado, o produto e que divergia.
UPDATE products p
SET type = pt.name
FROM product_types pt
WHERE pt.market_code = p.market_code
  AND upper(btrim(pt.name)) = upper(btrim(p.type))
  AND pt.name <> p.type
  AND NOT EXISTS (
    SELECT 1 FROM product_types x
    WHERE x.name = p.type AND x.market_code = p.market_code
  );
\echo 'A1. produtos com tipo realinhado por caixa (acima):'

-- A2. Ombrelones: o tipo 'CONJUNTO OMBRELONE COM BASE' nao existe. Criado
--     apontando para o MESMO grupo fiscal de 'CONJUNTO' (IPI 3,25%), decidido
--     pelo usuario em 06/10. Preserva a nomenclatura comercial em vez de
--     achatar tres produtos distintos em 'CONJUNTO'.
INSERT INTO product_types (id, market_code, name, group_id)
SELECT gen_random_uuid(), 'BR', 'CONJUNTO OMBRELONE COM BASE', pt.group_id
FROM product_types pt
WHERE pt.market_code = 'BR' AND pt.name = 'CONJUNTO'
ON CONFLICT (market_code, name) DO NOTHING;
\echo 'A2. tipo CONJUNTO OMBRELONE COM BASE criado (0 se ja existia):'

-- ---------------------------------------------------------------------------
-- B. Acesso a tela de Portugal
-- ---------------------------------------------------------------------------

-- B1. A trava de abertura do mercado. allowed_market_accesses exige
--     Market.is_enabled, senao a troca de mercado devolve 403.
UPDATE markets SET is_enabled = true WHERE code = 'EU' AND is_enabled = false;
\echo 'B1. mercado EU habilitado:'

-- B2. O vinculo do usuario. allowed_market_accesses exige status='active' E
--     role NOT NULL -- as duas condicoes, e a rbac_r2a deixou ambas pendentes.
--     Os vinculos comerciais vao a NULL porque ck_user_markets_role_links
--     exige isso para papel 'admin'.
--     Apenas o usuario nomeado: os outros vinculos EU seguem pending, que e o
--     que a R2a pretendia -- revisao nominal, um por um.
UPDATE user_markets um
SET status = 'active',
    role = 'admin',
    linked_client_id = NULL,
    rep_id = NULL
FROM users u
WHERE u.id = um.user_id
  AND lower(u.email) = lower(:'alvo')
  AND um.market_code = 'EU';
\echo 'B2. vinculo EU ativado para o usuario alvo:'

\echo ''
\echo '=============================================='
\echo 'DEPOIS'
\echo '=============================================='

\echo ''
\echo '--- A. Ainda ha produto com tipo orfao? (esperado 0) ---'
SELECT count(*) AS produtos_com_tipo_orfao
FROM products p
WHERE NOT EXISTS (
  SELECT 1 FROM product_types pt
  WHERE pt.name = p.type AND pt.market_code = p.market_code
);

\echo ''
\echo '--- A. Os 5, com o IPI que passam a aplicar ---'
SELECT p.product_code, p.type, pg.name AS grupo, pg.ipi AS ipi
FROM products p
JOIN product_types pt ON pt.name = p.type AND pt.market_code = p.market_code
LEFT JOIN product_groups pg ON pg.id = pt.group_id
WHERE p.product_code IN (
  'IBQ0014', 'IBQ0015',
  'IOM1000 IBA0077', 'IOM1027 BA0103', 'IOM2266 BA0155'
)
ORDER BY p.product_code;

\echo ''
\echo '--- B. Mercado e vinculo do usuario ---'
SELECT code, is_enabled FROM markets WHERE code = 'EU';
SELECT u.email, um.market_code, um.status, coalesce(um.role, '(nulo)') AS role
FROM users u
JOIN user_markets um ON um.user_id = u.id
WHERE lower(u.email) = lower(:'alvo')
ORDER BY um.market_code;

\echo ''
\echo '--- B. Os outros vinculos EU seguem pendentes (por desenho) ---'
SELECT status, coalesce(role, '(nulo)') AS role, count(*) AS vinculos
FROM user_markets WHERE market_code = 'EU'
GROUP BY 1, 2 ORDER BY 1, 2;

\echo ''
\echo '--- B. Portugal NAO esta operacional para venda: SKUs sem IVA aprovado ---'
SELECT count(*) AS skus_disponiveis_sem_iva_aprovado
FROM products p
JOIN product_markets pm ON pm.product_id = p.id AND pm.market_code = 'EU'
WHERE p.market_code = 'EU' AND pm.is_available IS TRUE
  AND (pm.vat_status IS DISTINCT FROM 'approved' OR pm.vat_rate IS NULL);
