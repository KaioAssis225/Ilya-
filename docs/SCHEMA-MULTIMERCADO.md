# Schema multimercado BR/EU

**Estado de referência:** `catalog_dimensions_r6_20261002`

**Mercados:** `BR` e `EU`; a primeira operação de `EU` será Portugal.

**Regra de cadastro:** produtos e dimensões comerciais são independentes por
mercado. A carga dos itens EU será manual.

Este documento descreve o schema final da linha `codex/br-eu-logica`. Ele
substitui, para esta linha, o desenho preliminar baseado em `market_id` e no
código `PT`. A chave persistida é `market_code` e o identificador europeu
continua sendo `EU`.

## 1. Escopo direto por mercado

| Tabela | Coluna/chave | Nulidade e default | Invariante principal |
|---|---|---|---|
| `markets` | `code` PK | obrigatória; sem default | `BR` e `EU` são identidades técnicas; `is_enabled` controla disponibilidade operacional. |
| `user_markets` | PK `(user_id, market_code)` | `market_code` obrigatório | Papel, estado e vínculos comerciais pertencem ao mercado. Um vínculo ativo exige papel. Cliente e representante vinculados devem pertencer ao mesmo mercado. |
| `price_lists` | `market_code` | obrigatório | `code` é único dentro do mercado. |
| `product_markets` | PK `(product_id, market_code)` | obrigatório | Disponibilidade, textos localizados e governança de IVA por produto/mercado. IVA só é faturável com estado `approved`, taxa, aprovador e data. |
| `market_tax_rates` | `market_code` | obrigatório | Taxa única por `(market_code, product_type)`. Não substitui a aprovação explícita exigida para Portugal. |
| `market_order_counters` | PK `(market_code, number_owner_id)` | obrigatório | Numeração de pedido separada por mercado e dono. |
| `market_quote_counters` | PK `market_code` | obrigatório | Numeração de orçamento separada por mercado. |
| `clients` | `market_code` | obrigatória; default legado `BR` | E-mail e documento são únicos por mercado; estado brasileiro só é validado para BR. |
| `representatives` | `market_code` | obrigatória; default legado `BR` | E-mail e documento são únicos por mercado; estado brasileiro só é validado para BR. |
| `orders` | `market_code` | obrigatória; default legado `BR` | `orc_id` e numeração pertencem ao mercado. Moeda, locale, país e rótulo fiscal ficam no snapshot do pedido. |
| `notifications` | `market_code` | obrigatória; default legado `BR` | A consulta é filtrada pelo mercado ativo. |
| `products` | `market_code` | obrigatória; default legado `BR` | `product_code` é único em cada mercado; o mesmo código pode existir como produtos independentes em BR e EU. |
| `catalogs` | `market_code` | obrigatória; default legado `BR` | Nome único dentro do mercado. |
| `product_types` | `market_code` | obrigatória; default legado `BR` | Nome único dentro do mercado. `group_id` continua sendo referência fiscal legada BR e não deve fornecer IVA a EU. |
| `optional_categories` | `market_code` | obrigatória; default legado `BR` | Código único dentro do mercado. |
| `optionals` | `market_code` | obrigatória; default legado `BR` | Índice por mercado e categoria; associações são validadas pela aplicação. |

`Client`, `Representative`, `Order`, `Notification`, `Product`, `Catalog`,
`ProductType`, `OptionalCategory` e `OptionalColor` também recebem o filtro
transversal do ORM conforme `Session.info["active_market"]`. As rotas de escrita
continuam responsáveis por validar o mercado dos relacionamentos antes de
persistir.

## 2. Escopo herdado

As tabelas abaixo não repetem `market_code`; o mercado é determinado pelo pai:

| Tabela | Pai que define o mercado |
|---|---|
| `order_items`, `order_history`, `signature_invitations` | `orders` |
| `product_prices` | produto e lista de preços do mesmo mercado, validado na aplicação |
| `product_set_items`, `product_set_components` | `products` |
| `product_optionals`, `product_set_component_optionals` | produto/conjunto e opcional, validados na aplicação |

`product_markets` preserva os vínculos históricos EU que existiam antes da
separação de `products`. Não há FK composta ligando o mercado do vínculo ao
mercado do produto. As rotas comerciais de catálogo e pedido combinam
`Product.market_code` com `ProductMarket.market_code`; por isso os vínculos EU
que apontam para os produtos legados BR não compõem o catálogo comercial EU.
Eles permanecem visíveis a diagnósticos de plataforma, não criam produtos EU e
não substituem o cadastro manual aprovado para o catálogo europeu.

## 3. Identidade, sessão e autoridade

- `users` é a identidade global. `role`, `linked_id`, `rep_id` e `home_market`
  permanecem como espelho legado durante a transição; a autoridade comercial
  vem de `user_markets`.
- `user_markets.status` aceita `pending`, `active` ou `suspended`. O papel pode
  ser nulo somente quando o vínculo não está ativo.
- `user_platform_permissions` é global e aceita apenas `platform_admin`,
  `activate_market` e `read_outbox`. A migration não concede permissões.
- `refresh_tokens.scope='market'` exige `active_market`; `scope='platform'`
  exige `active_market IS NULL`. Tokens anteriores são classificados como
  sessões de mercado.
- Sessões comerciais e de plataforma são contratos distintos. A identidade de
  plataforma pode operar sem vínculo BR/EU.

## 4. Tabelas globais e exceções

| Tabela/conjunto | Tratamento |
|---|---|
| `users` | Identidade global, com autoridade comercial delegada a `user_markets`. |
| `user_platform_permissions` | Autoridade global de plataforma. |
| `privacy_events`, `privacy_incidents`, `legal_holds`, `retention_reviews` | Governança global, acessível pela autoridade de plataforma. |
| `integration_outbox` | Global e sem `market_code`. Está fora do escopo funcional BR/EU atual; nenhuma integração de Estoque faz parte deste projeto. |
| `product_groups` | Fiscal legado BR. Não pode ser usado como fonte de IVA EU. |
| `order_number_counters` | Contador legado em SQL; a numeração multimercado usa as tabelas `market_*_counters`. |
| `_backup_precos_20261001` | Backup operacional presente em produção e fora do controle do Alembic. |

## 5. Cadeia de migration e recuperação

Partindo do head de produção observado `catalogs_20260911`, a cadeia linear é:

1. `vat_approval_20261001`
2. `rbac_r2a_20261001b`
3. `rbac_r2b_20261001c`
4. `products_market_r4_20261001`
5. `user_market_links_r5_20261002`
6. `catalog_dimensions_r6_20261002`

Os backfills classificam como BR somente os registros já confirmados pelo
responsável e não criam produtos, catálogos, tipos ou opcionais EU. Vínculos de
usuário EU existentes ficam `pending` para revisão nominal. Taxas de IVA
legadas ficam `pending/legacy_unknown` e não se tornam aprovadas por migration.

O `downgrade()` foi ensaiado até `catalogs_20260911`. Ele revoga sessões de
plataforma antes de restaurar o contrato antigo e bloqueia a reversão se já
existirem códigos ou nomes repetidos entre mercados. Depois do cadastro de
dados EU independentes, o snapshot criptografado anterior à migration é o
mecanismo autoritativo de recuperação.

`ops/reconcile_multimarket.sql` é a rotina somente leitura do corte. Ela
verifica coortes, totais de pedidos, vínculos comerciais, sessões, contadores e
resíduos legados sem selecionar PII ou valores individuais. Deve rodar na cópia
restaurada antes do corte e durante a janela de implantação.

## 6. Compatibilidade da versão anterior

A API de `origin/main` foi inicializada contra uma cópia restaurada de produção
já migrada para o head final. Login BR e leitura do catálogo BR funcionaram.
Essa compatibilidade existe para a janela controlada de implantação; a versão
anterior não deve ser usada para cadastrar dados depois que a autoridade por
mercado e as sessões de plataforma forem liberadas.
