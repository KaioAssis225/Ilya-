# Plano — Protótipos (mercado EU / Portugal)

Área para quem desenvolve protótipos: cria o protótipo como um produto normal
(mesmos campos e fotos), com código `PROT-0001`, `PROT-0002`…, mantido fora do
catálogo comum e usado só nos orçamentos da própria pessoa. Vale **só em EU** e
**só para quem recebe a permissão** na Plataforma. Nenhum e-mail ou nome fixo
no código: o acesso é um campo do vínculo de mercado do usuário.

## 1. Decisão de modelo: flag em `products`, não tabela separada

| | Tabela separada (`prototypes`) | Flag `products.is_prototype` |
|---|---|---|
| Fotos, preços por lista, IVA, opcionais (aplicações), PDF, orçamento | tudo duplicado (≈ 6 tabelas e 3 fluxos reescritos) | reaproveita o fluxo de produto EU inteiro |
| Risco de vazar para fora | baixo por construção | **alto se feito "por query"**; baixo com filtro central |
| Código novo | muito (e divergência futura do "produto normal") | pouco |

**Escolha: flag**, com *negação por padrão* no ORM. O risco da flag é esquecer
um `WHERE is_prototype = false` em alguma consulta. Isso é resolvido num ponto
só, em `app/db/market_scope.py`: todo `SELECT` sobre `Product` ganha
`is_prototype = false` automaticamente, igual ao isolamento de mercado que já
existe. Ver um protótipo exige um opt-in explícito
(`execution_options(include_prototypes=<user_id>)` ou
`db.sync_session.info["prototype_owner"]`), que só rotas de protótipo e o
orçamento do próprio dono ligam. `grep include_prototypes` lista todos os
lugares onde protótipo é visível.

Invariantes no banco (migration):
- `products.is_prototype boolean not null default false` e
  `products.created_by_user_id uuid null` (FK `users`, `ON DELETE RESTRICT`).
- `CHECK (NOT is_prototype OR market_code = 'EU')` — protótipo nunca é BR.
- `CHECK (NOT is_prototype OR created_by_user_id IS NOT NULL)`.
- `CHECK (NOT is_prototype OR product_code LIKE 'PROT-%')`: protótipo sempre
  tem o prefixo. A recíproca (produto normal não usa `PROT-`) fica na aplicação
  (criação e renomeação de produto EU recusam com 422): um CHECK nos dois
  sentidos poderia quebrar linha legada que já exista.
- `SEQUENCE prototype_code_seq`: o código sai de `nextval` (sem corrida; um
  rollback pode deixar buraco na numeração, o que é aceitável) formatado com
  4 dígitos (`PROT-0001`; passa de 9999 sem quebrar: `PROT-10000`).
- `user_markets.can_manage_prototypes boolean not null default false` com
  `CHECK (NOT can_manage_prototypes OR market_code = 'EU')`.

Todas as mudanças são aditivas. Downgrade: remove protótipos (e seus filhos,
por `ON DELETE CASCADE`), as constraints, a sequence e as colunas.

## 2. Acesso (RBAC + ownership, no servidor)

- Permissão: `user_markets.can_manage_prototypes` (só EU). O admin liga na
  Plataforma → *Identidades e acessos* (checkbox "Protótipos" ao lado de
  "Aprovar IVA"); exposto em `/auth/me` e em `MarketActor`.
- Dependência `require_prototype_manager`: sessão comercial com mercado ativo
  EU **e** vínculo ativo com a permissão. Sem isso, **404** (a existência da área
  não é revelada) em todas as rotas `/api/v1/prototypes/*`.
- Ownership: cada protótipo pertence a quem criou (`created_by_user_id`).
  Rotas e orçamento só enxergam os **próprios** protótipos; o de outra pessoa
  responde 404. (Recomendação: vale por criador, não compartilhado.)
- Quem perde a permissão perde a visão na hora (a permissão é lida do vínculo a
  cada requisição, como `can_approve_tax`). Os protótipos ficam guardados.

## 3. Rotas (PR A e B)

`/api/v1/prototypes` (router novo, EU + permissão):
`POST` criar · `GET` listar/buscar · `GET /{id}` · `PATCH /{id}` ·
`DELETE /{id}` (desativa: `is_active=false`, o código nunca é reutilizado) ·
fotos: `POST /{id}/photos`, `DELETE /{id}/photos/{photo_id}`,
`PUT /{id}/photos/order`, `PUT /{id}/photos/{photo_id}/primary`.

Os handlers reaproveitam os helpers de `products.py` (`_create_product_for_market`
etc.) em vez de copiar: o corpo é o mesmo `ProductCreate`, sem `product_code`
(gerado no servidor) e com `vat_rate` do próprio protótipo.

## 4. Opcionais do protótipo (PR B)

- **Já cadastrados:** o protótipo usa `ProductOptionalApplication` como qualquer
  produto (categoria + opcionais permitidos), com os grupos existentes.
- **Grupo só daquele protótipo:** `optional_categories.prototype_id` e
  `optionals.prototype_id` (nullable, FK `products(id) ON DELETE CASCADE`).
  Um grupo local é uma categoria + opcionais com `prototype_id` preenchido;
  entram na negação por padrão do ORM (`OptionalCategory`/`OptionalColor`), então
  **não aparecem** na lista geral de opcionais, no BI nem em exportações.
  Cada protótipo só enxerga os próprios grupos.

## 5. Orçamento, pedido, PDF (PR B)

- O orçamento do dono carrega protótipos pelo mesmo caminho dos produtos
  (`_load_products_and_types` com opt-in do dono). Preço da lista escolhida,
  IVA (taxa do protótipo, ver §8), desconto máximo, opcionais e catálogo seguem
  as regras de produto EU, sempre resolvidos no servidor.
- Se não for o dono (ou não tiver mais a permissão), `product_code` PROT-* responde
  404 "Produto não encontrado" — exatamente como produto inexistente.
- O item do orçamento continua sendo **snapshot** por `product_code` (nada muda
  em `order_items`). Cópia/revisão/edição de orçamento com PROT-* funcionam para
  o dono; para os demais, o item já salvo continua legível.
- PDF e e-mail do pedido leem o snapshot; a foto do protótipo é lida com opt-in
  só no job do próprio pedido.

### Orçamento vira pedido?
Pode finalizar normalmente (snapshot imutável, sem mudar nada). **Protótipo nunca
sincroniza com Moloni nem com o Estoque:**
- `enqueue_finalized_eu_order` não cria job se o pedido tiver item PROT-*
  (o pedido registra no histórico "contém protótipo: sem envio ao Moloni").
- `POST /integrations/moloni/orders/{id}/enqueue` recusa (422) e
  `moloni_exporter.deliver_job` recusa por segurança (defesa em profundidade).
- Estoque: hoje só existe o login único (BR) e EU está fora do escopo de
  integração; protótipos são EU-only. Nenhuma mudança no outbox, webhooks ou
  cron do Estoque. Para qualquer leitor cross-database de `products`, a linha de
  protótipo é `market_code='EU'` e `is_prototype=true` (documentado).

## 6. Pontos de exclusão (negação por padrão no ORM)

| Lugar | Como fica fora |
|---|---|
| Catálogo (`GET /products`, `/batch`, `/{id}`, filtros, categorias) | filtro central do ORM |
| BI / dashboard / contagens | filtro central (consultas sobre `Product`); tabelas filhas só são lidas via produto |
| Importação/exportação CSV | filtro central + recusa de código `PROT-*` |
| Moloni (job/exportador/enqueue manual) | bloqueio explícito, §5 |
| Estoque | fora de escopo EU; sem alteração |
| Sets (conjuntos) | `_resolve_set_items` não acha protótipo (filtro) |
| Busca/listas de outros usuários | filtro central + ownership |
| PDFs/e-mails de outros usuários | só leem o snapshot do pedido |
| Lista geral de opcionais | `prototype_id IS NULL` pela negação por padrão |
| Cálculo de IVA por grupo (`_load_eu_group_vat_rates`) | filtro central: protótipo não entra na média do grupo |

## 7. Telas (PR C)

- Plataforma → Identidades e acessos: checkbox **Protótipos** (só no vínculo EU).
- Menu **Protótipos** (só EU e com permissão): lista dos meus protótipos + formulário
  igual ao de produto (descrições PT/EN, tipo, catálogo, medidas, preços por
  lista, IVA, observação, fotos, opcionais). O código aparece como "PROT-xxxx
  (automático)". Editor de **grupo de opcional só deste protótipo**.
- **Produtos** → botão/alternância **"Visualizar protótipo"** (só com permissão):
  mostra os meus protótipos no lugar do catálogo, com o mesmo cartão/detalhe e
  "adicionar ao orçamento".
- Orçamento: protótipo entra como qualquer produto; selo "Protótipo" na linha.

## 8. Premissas (decididas por bom senso; ajustáveis)

1. **Ownership por criador**, não compartilhado entre pessoas com a permissão.
2. **IVA:** o criador informa a taxa do protótipo (padrão 23 % no formulário),
   gravada como aprovada pelo próprio criador (`vat_source='prototype'`). O
   protótipo **não** entra na taxa por grupo e **não** vai ao Moloni. Se o
   financeiro preferir revisão fiscal, basta exigir `can_approve_tax`.
3. **Fora de escopo:** conjuntos com componentes, tecido fornecido e limite de
   área em protótipo (criam-se no produto normal quando o protótipo for
   promovido). Medidas, círculo, preços das 4 listas, fotos e opcionais entram.
4. **Promover protótipo a produto** (virar item de catálogo) não faz parte
   deste trabalho.

## 9. Entrega

1. **PR A** — migration, modelo, permissão, filtro central, CRUD + fotos, código PROT.
2. **PR B** — grupos locais de opcionais, orçamento/pedido/PDF, bloqueio Moloni.
3. **PR C** — frontend (Plataforma, aba Protótipos, "Visualizar protótipo", orçamento).

Testes de integração em Postgres real em cada PR: RBAC (sem permissão = 404),
ownership, sequência PROT (concorrência), exclusão de catálogo/lista/sync/Moloni.
