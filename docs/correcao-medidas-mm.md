# Correção de medidas gravadas em milímetros (CD0033 e similares)

**Status: PROPOSTA — nada aqui foi executado e nenhuma migration altera dados.**
Quem decide se, quando e como aplicar em produção é o dono do produto.

## Contexto

As colunas `altura`, `largura` e `profundidade` de `products` e de
`product_set_components` guardam **metros** (`Numeric(10,2)`). O BR exibe em
metros; o EU multiplica por 1000 e exibe em mm (`frontend/src/lib/measurements.ts`).

O produto **CD0033** (cadeira) ficou com 470 / 490 / 780 — milímetros gravados
onde o sistema espera metros — e o orçamento de Portugal mostrou "L 470000 mm".

A prevenção (limite de **20 m** na API, no CSV e no formulário) está no mesmo PR
deste documento. Ela **não corrige** o que já está no banco: a leitura de
produtos errados continua funcionando de propósito, para que dê para listá-los.

## 1. Consulta de diagnóstico (somente leitura)

Rode primeiro em produção, só `SELECT`. O limite 20 é o mesmo do código
(`MAX_PRODUCT_DIMENSION_M`).

```sql
-- Produtos com qualquer medida acima de 20 m
SELECT p.market_code,
       p.product_code,
       p.description,
       p.altura,
       p.largura,
       p.profundidade,
       p.is_circular,
       p.is_set
FROM products p
WHERE p.altura > 20 OR p.largura > 20 OR p.profundidade > 20
ORDER BY p.market_code, p.product_code;

-- Componentes de conjunto com qualquer medida acima de 20 m
SELECT p.market_code,
       p.product_code AS conjunto,
       c.id           AS componente_id,
       c.description,
       c.altura,
       c.largura,
       c.profundidade,
       c.is_circular
FROM product_set_components c
JOIN products p ON p.id = c.set_id
WHERE c.altura > 20 OR c.largura > 20 OR c.profundidade > 20
ORDER BY p.market_code, p.product_code, c.description;
```

### Itens de pedido/orçamento que copiaram a medida errada

`order_items` guarda um **snapshot** das medidas no momento da venda
(`backend/app/api/routers/orders.py`, criação do item). Corrigir `products` **não**
corrige pedidos e orçamentos já criados — eles continuam com 470 e continuam
saindo como "470000 mm" no PDF. Veja o tamanho do problema (somente leitura):

```sql
SELECT o.market_code,
       o.code        AS pedido,
       o.orc_id,
       i.product_code,
       i.altura,
       i.largura,
       i.profundidade
FROM order_items i
JOIN orders o ON o.id = i.order_id
WHERE i.altura > 20 OR i.largura > 20 OR i.profundidade > 20
ORDER BY o.market_code, o.code, i.product_code;
```

Se houver linhas, é uma segunda decisão (corrigir só orçamentos em aberto? reemitir
PDFs?). **Este documento não propõe `UPDATE` em `order_items`.**

## 2. Antes de qualquer UPDATE: revisar a lista

A regra "passou de 20 → está em mm → dividir por 1000" é uma heurística. Confira a
lista do passo 1 linha a linha antes de aplicar. Atenção a:

- valores acima de 20 000 (dividido por 1000 ainda passaria de 20): o UPDATE abaixo
  **não** toca nessas linhas — corrija à mão;
- produto de área (tapete) grava 0 nessas colunas, então não deve aparecer;
- produtos com medida legitimamente grande (não há nenhum conhecido; os seeds
  chegam a 3,5 m).

## 3. Backup (antes do UPDATE)

Duas camadas, ambas antes de mexer:

1. Dump lógico das duas tabelas (rodado fora do banco, com a connection string de
   produção):

   ```bash
   pg_dump "$DATABASE_URL" --data-only --table=products --table=product_set_components \
     --file=backup_medidas_$(date +%Y%m%d_%H%M%S).sql
   ```

2. Cópia só das linhas que serão alteradas, dentro do próprio banco (facilita o
   rollback linha a linha):

   ```sql
   CREATE TABLE backup_medidas_mm_products AS
   SELECT id, product_code, market_code, altura, largura, profundidade, now() AS salvo_em
   FROM products
   WHERE altura > 20 OR largura > 20 OR profundidade > 20;

   CREATE TABLE backup_medidas_mm_components AS
   SELECT id, set_id, altura, largura, profundidade, now() AS salvo_em
   FROM product_set_components
   WHERE altura > 20 OR largura > 20 OR profundidade > 20;
   ```

## 4. UPDATE proposto (dentro de uma transação)

Divide por 1000 **apenas** a coluna que passou de 20 e só quando o resultado cabe no
limite. Cada coluna é avaliada separadamente (um produto pode ter só a largura em mm).

```sql
BEGIN;

UPDATE products SET
  altura       = CASE WHEN altura       > 20 AND altura       <= 20000 THEN ROUND(altura       / 1000, 2) ELSE altura       END,
  largura      = CASE WHEN largura      > 20 AND largura      <= 20000 THEN ROUND(largura      / 1000, 2) ELSE largura      END,
  profundidade = CASE WHEN profundidade > 20 AND profundidade <= 20000 THEN ROUND(profundidade / 1000, 2) ELSE profundidade END
WHERE altura > 20 OR largura > 20 OR profundidade > 20;

UPDATE product_set_components SET
  altura       = CASE WHEN altura       > 20 AND altura       <= 20000 THEN ROUND(altura       / 1000, 2) ELSE altura       END,
  largura      = CASE WHEN largura      > 20 AND largura      <= 20000 THEN ROUND(largura      / 1000, 2) ELSE largura      END,
  profundidade = CASE WHEN profundidade > 20 AND profundidade <= 20000 THEN ROUND(profundidade / 1000, 2) ELSE profundidade END
WHERE altura > 20 OR largura > 20 OR profundidade > 20;

-- Conferência ANTES de confirmar: não pode sobrar nada acima de 20,
-- e o antes/depois precisa bater com a lista revisada no passo 2.
SELECT count(*) AS produtos_ainda_acima_de_20
FROM products WHERE altura > 20 OR largura > 20 OR profundidade > 20;

SELECT count(*) AS componentes_ainda_acima_de_20
FROM product_set_components WHERE altura > 20 OR largura > 20 OR profundidade > 20;

SELECT p.product_code, b.altura AS altura_antes, p.altura AS altura_depois,
       b.largura AS largura_antes, p.largura AS largura_depois,
       b.profundidade AS prof_antes, p.profundidade AS prof_depois
FROM products p JOIN backup_medidas_mm_products b ON b.id = p.id
ORDER BY p.product_code;

-- Se estiver tudo certo: COMMIT;  Caso contrário: ROLLBACK;
```

Rollback depois do COMMIT (se preciso), a partir das cópias do passo 3:

```sql
UPDATE products p
SET altura = b.altura, largura = b.largura, profundidade = b.profundidade
FROM backup_medidas_mm_products b WHERE b.id = p.id;

UPDATE product_set_components c
SET altura = b.altura, largura = b.largura, profundidade = b.profundidade
FROM backup_medidas_mm_components b WHERE b.id = c.id;
```

O UPDATE acima **não** mexe em `updated_at` nem em `source_version` de `products`;
se o catálogo precisar propagar a correção por esses campos, é parte da decisão
de aplicação.

## 5. Limite de precisão: 2 casas decimais

As colunas são `Numeric(10,2)`, ou seja, **centímetros**. A conversão de mm para m
perde o milímetro:

| mm gravado | metros (2 casas) | mm exibido no EU |
|-----------:|-----------------:|-----------------:|
| 470        | 0,47             | 470              |
| 475        | **0,48**         | **480**          |
| 783        | 0,78             | 780              |

Ou seja, **475 mm vira 0,48 m (480 mm no EU)**. Para a maioria dos móveis isso é
aceitável; se for preciso **precisão ao milímetro**, a alternativa é passar as
colunas para `Numeric(10,3)` em `products`, `product_set_components` (e, por
coerência, `order_items`) — uma migration de esquema, com ajuste dos schemas
(`decimal_places=3`), da exibição e dos testes — e só então converter os dados
com `ROUND(x / 1000, 3)`.

**Decisão do usuário** (não implementada neste PR): manter 2 casas (UPDATE da
seção 4 como está) ou migrar para 3 casas antes de corrigir.
