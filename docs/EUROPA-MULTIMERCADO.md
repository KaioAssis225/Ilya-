# Ilya Brasil e Europa

## Estado e limites da primeira liberação

`BR` e `EU` são mercados comerciais independentes. A chave `EU` permanece
porque o produto poderá atender outros países europeus; a primeira liberação
aceita somente cadastros de Portugal (`country = PT`). A inclusão de outro país
exige regras fiscais, documentais e cadastrais próprias antes de alterar
`EU_LAUNCH_COUNTRY`.

O mercado EU permanece inacessível enquanto qualquer uma destas travas estiver
fechada:

1. `EUROPE_MARKET_ENABLED=false` no backend;
2. `markets.is_enabled=false` no banco;
3. nenhum produto EU disponível;
4. produto disponível sem Lojista, Corporativo e PVP em EUR;
5. produto disponível sem IVA explícito e aprovado nominalmente;
6. cliente ou representante EU ativo fora de Portugal;
7. produto EU referenciando catálogo, tipo, categoria ou opcional de BR.

## Identidade, plataforma e mercados

- `users` é a identidade global de login.
- `user_markets` é a fonte autoritativa de papel, estado, cliente,
  representante, Dashboard e aprovação fiscal dentro de cada mercado.
- Uma identidade pode ter BR, EU, ambos ou nenhum vínculo comercial.
- Administrador comercial não recebe outro mercado automaticamente.
- A sessão comercial assina `scope=market` e um único `market` no JWT.
- A troca de mercado exige vínculo ativo persistido e emite um novo token.
- A sessão `/platform` usa `scope=platform`, cookie e refresh próprios, sem
  `active_market`.
- Capacidades globais ficam em `user_platform_permissions`. Ativação de mercado,
  gestão de identidades, outbox e governança LGPD não derivam de papel BR/EU.
- A remoção de um vínculo revoga sessões comerciais e preserva a sessão de
  plataforma quando a identidade e suas capacidades continuam válidas.

## Produto, catálogo e preços

Produtos são independentes por mercado. `products` usa unicidade
`(market_code, product_code)`, então BR e EU podem ter o mesmo SKU sem
compartilhar descrição, foto, dimensões, observação, componentes ou vínculos.

Também pertencem a um mercado:

- `catalogs`;
- `product_types`;
- `optional_categories`;
- `optionals`;
- `product_markets`, `price_lists` e `product_prices`.

As rotas validam que catálogo, tipo, categorias, opcionais e componentes
pertencem ao mesmo mercado do produto. A barreira ORM aplica o mercado ativo às
leituras dessas entidades.

Grupos de produto (`product_groups`) também são por mercado desde a revisão
`eu_product_groups_r13_20261008` (decisão de 08/10/2026). No Brasil o grupo
carrega o IPI e sua manutenção segue a guarda fiscal (admin BR) com evento de
auditoria. Em Portugal o grupo só organiza o catálogo: o banco exige `ipi = 0`
(`ck_product_groups_eu_sem_ipi`) e o pedido EU continua usando o IVA aprovado de
`product_markets`, nunca o grupo. A FK composta
`fk_product_types_group_same_market` impede tipo de um mercado em grupo do outro.

A migration R6 classifica as dimensões legadas como BR para preservar o
catálogo-base confirmado. Ela não cria dimensões, produtos, vínculos nem preços
EU. A preparação manual com EU fechado usa os endpoints `/platform/EU` de
catálogos, tipos, categorias, opcionais e produtos.

## IVA e importação EU

`POST /api/v1/markets/EU/import` exige `vat_rate` em cada linha. Valor vazio,
ausente ou fora de 0 a 100 rejeita o lote inteiro. A importação nunca lê IPI nem
taxa de grupo e grava a decisão como `pending`.

Uma taxa só pode entrar em pedido quando o vínculo `product_markets` contém:

- `vat_status = approved`;
- `vat_rate` explícito, inclusive quando a taxa aprovada é zero;
- `approved_by_user_id`;
- `approved_at`.

A aprovação exige `can_approve_tax` no vínculo EU do aprovador. Além da decisão
por produto, quem tem essa permissão pode aplicar e aprovar uma taxa em todos os
produtos dos subgrupos de um grupo EU (`PUT /api/v1/markets/EU/groups/{id}/vat`,
botão Editar do grupo; decisão de 08/10/2026). Cada produto continua registrando
quem aprovou e quando. Percentuais e a
seleção final de itens são decisões manuais do responsável e não são inferidos
pelo sistema.

## Pedidos, documentos e mídia

- ORC e PED usam contadores separados por mercado.
- O pedido preserva mercado, lista, moeda e locale.
- Cada item preserva preço, desconto, taxa, valor do imposto, rótulo e moeda.
- BR usa BRL, pt-BR e IPI. A primeira liberação EU usa EUR, pt-PT ou en-GB e IVA.
- Clientes e representantes EU só podem ser criados ou usados em pedidos com
  `country = PT`.
- O PDF usa código postal, localidade, região e país para endereços portugueses;
  não concatena `cidade/UF`.
- Fotos locais e em object storage são servidas pela mesma rota com URL HMAC de
  curta duração. Chave conhecida sem assinatura válida recebe 403. O diretório
  de uploads não possui mount público.

## Sequência de implantação

1. Manter EU desabilitado no banco e no ambiente.
2. Fazer backup restaurável e testar a restauração em ambiente isolado.
3. Aplicar, em ordem, as revisions após `catalogs_20260911`:
   `vat_approval_20261001`, `rbac_r2a_20261001b`,
   `rbac_r2b_20261001c`, `products_market_r4_20261001`,
   `user_market_links_r5_20261002` e
   `catalog_dimensions_r6_20261002`.
4. Publicar o backend e o frontend compatíveis com o novo head.
5. Provisionar a conta inicial de plataforma e confirmar login em `/platform`.
6. Cadastrar manualmente dimensões, produtos, preços e IVA de Portugal.
7. Aprovar individualmente o IVA e revisar o PDF de amostra.
8. Executar a ativação EU; o endpoint revalida todas as travas persistidas.
9. Habilitar `EUROPE_MARKET_ENABLED` e testar login, catálogo, orçamento, pedido,
   PDF e fotos em homologação antes de produção.

Rollback operacional: desabilitar EU no banco e no ambiente. Não executar
downgrade automático após a criação de dados independentes em mais de um
mercado.

## Fora do escopo

Inventário físico e integração com Estoque não participam desta entrega. A
seleção de SKUs, valores e taxas concretas de Portugal permanece manual.
