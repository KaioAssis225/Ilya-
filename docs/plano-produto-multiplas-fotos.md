# Plano — várias fotos por produto, com foto principal

Status: **só plano**. Nenhum código, migration, commit ou PR foi feito.
Base: `main` em `ac49a96b`. Head do Alembic hoje: `supplied_fabric_eu_r42`.

## 1. O que o usuário pediu (interpretação)

1. Um produto passa a ter **N fotos** (galeria), não só uma.
2. Na tela **Produtos** (catálogo, `/produtos`): o card externo indica que há várias fotos e, ao clicar no card, abre uma **galeria navegável**.
3. Na aba de produtos, o usuário escolhe qual foto é a **principal**. A principal é a que continua aparecendo em todo lugar que hoje usa a foto única (orçamento, PDF, miniaturas, conjuntos).

> Atenção: existem duas "abas de produtos". `/produtos` (nav "Produto") só **exibe**. A edição e o upload de foto ficam em `/cadastros` → sub-aba **Produtos** (`CadastroPage.tsx`). Ver pergunta Q1.

## 2. Como a foto é guardada hoje (levantamento)

### Banco
- `products.photo_path` — `String(255)`, nulo. Guarda `object://products/<uuid>.<ext>` (BR), `object://eu-products/<uuid>.<ext>` (EU) ou caminho local (dev/teste). `backend/app/models/product.py:55`.
- **Não existe coluna de miniatura.** A miniatura é derivada da chave: `products/<uuid>.jpg` → `product-thumbnails/<uuid>.jpg.webp` (`eu-product-thumbnails/…` no EU). Toda foto nova ganha miniatura de graça, sem schema novo.
- `products.source_version` existe para o Ilya Estoque ler "frescor". O upload de foto **não** incrementa `source_version` hoje. O plano mantém isso (Q8).
- Pedidos **não** guardam foto. O item do pedido só tem `product_code`; as telas leem a foto do catálogo vivo. Só o job de e-mail do PDF congela `photo_path` num snapshot (`services/order_email_jobs.py:134`).

### Armazenamento (`backend/app/core/uploads.py`)
- `persist_upload(content, directory, ext, market=)` grava original + miniatura WebP 320 px no bucket certo. O bucket é decidido **pelo prefixo da chave** (`eu-*` → bucket EU). Sem bucket (dev/teste) cai em disco, sob `eu/` para EU.
- `sanitize_image_upload` valida extensão, pixels (`MAX_IMAGE_PIXELS` 25 MP), regrava a imagem e limita o lado a `MAX_IMAGE_DIMENSION` 2560. Limite de tamanho: `MAX_UPLOAD_SIZE_MB` = 5.
- `delete_upload(path, market=)` apaga original + miniatura (+ variantes de opcional). Com `market`, **não apaga** arquivo do outro mercado (foto BR emprestada por produto EU).
- `build_photo_url` / `build_thumbnail_url` devolvem URL assinada (HMAC, curta) a partir de um `photo_path`; não precisam mudar.

### Endpoints (`backend/app/api/routers/products.py`)
- `POST /products/{id}/upload-photo` (L1280) — papéis `_ADMIN_VENDEDOR` (admin, vendedor, produtos). Carrega o produto do mercado ativo (ativo + disponível), **403 se o produto EU também está disponível no BR** ("Altere as fotos do catálogo-base no mercado Brasil."), sanitiza, grava, troca `photo_path`, commit; se o commit falha apaga o arquivo novo; depois `delete_upload_if_unreferenced(old, market=)`.
- `DELETE /products/{id}/photo` (L1342) — zera `photo_path` e apaga o arquivo só se ninguém mais referencia.
- `POST /products/platform/EU/{id}/upload-photo` (L1388) — wrapper de plataforma (preparação do EU fechado) que reaproveita `upload_photo`.
- Leitura: `_to_read` (L107) preenche `photo_url`/`thumbnail_url` do produto e dos `set_items`. Todas as listagens passam por `_to_market_reads` (`GET ""`, `/batch`, `GET /{id}`, `POST`, `PATCH`…).

### Exclusão segura (`backend/app/core/media_orphans.py`)
- `is_upload_referenced` varre **todas** as colunas texto/JSON (≥ 36 caracteres) por `ILIKE` do UUID; falha ⇒ "referenciado" (na dúvida, o arquivo fica). `delete_upload_if_unreferenced` roda **depois** do commit.
- `scan_photo_references` (inventário de órfãs EU) também varre todas as colunas. **Uma tabela nova com coluna `photo_path` varchar/text já é coberta sem mudar código** — mas precisamos de teste que prove isso, e vale pôr a tabela em `_PRIORITY_TABLES` (só otimização).
- Esse mecanismo já protege o snapshot do e-mail: a foto citada em `order_email_documents` (JSON) não é apagada.

### Sincronização EU (`backend/app/api/routers/markets.py:288-347`)
- Copia fotos emprestadas do BR para o bucket EU, **produto a produto, olhando só `Product.photo_path`**. Com galeria, precisa copiar também as fotos extras (§4.1).

### Quem lê a foto (todos usam a foto "única")
| Lugar | Arquivo | Muda? |
|---|---|---|
| Card do catálogo + detalhe | `ProdutosPage.tsx` (`CatalogImage`, `FullProductImage`, L811, L1523) | **Sim** (galeria) |
| Itens de conjunto no detalhe | `ProdutosPage.tsx:896` (`set_items[].photo_url`) | Não (principal) |
| Cadastro > Produtos (tabela, detalhe expandido, formulário, upload em lote por nome) | `CadastroPage.tsx` L742, L1303, L1410-1475, L2175-2210 | **Sim** (gerenciador) |
| Orçamento (linha, seletor, modal) | `OrcamentoPage.tsx` L1026, L2340, L2364, L2582 | Não (principal) — ver Q4 |
| Pedidos (miniatura do item) | `PedidosPage.tsx:670` | Não |
| PDF no navegador | `lib/generatePDF.ts:170` (`thumbnail_url ?? photo_url`) | Não (principal) |
| PDF no servidor | `services/pdf_renderer.py:65` (snapshot `photo_path` → data URL) | Não (principal) |
| Snapshot do PDF | `lib/orderPdfSnapshot.ts`, `order_email_jobs.py:134` | Não |
| Backup do site | `backup_site.py:87` (varre qualquer chave `*photo*` do JSON da API) | Não — `photos[].photo_url` entra sozinho |
| Tipos / fixtures | `types/index.ts`, `test/productTestUtils.tsx`, `lib/demo.ts` | Sim (campo novo opcional) |

**Conclusão:** se `photo_url`/`thumbnail_url`/`photo_path` continuarem significando "a principal", **nenhum consumidor existente quebra**, o bundle do PDF (`backend/app/pdf_bundle/pdf-render.js`) **não precisa ser regenerado** e os snapshots de pedido seguem imutáveis.

## 3. Modelo proposto

### Recomendação: tabela `product_photos` + `products.photo_path` mantido como espelho da principal

```
product_photos
  id          uuid PK
  product_id  uuid FK products(id) ON DELETE CASCADE, NOT NULL
  photo_path  varchar(255) NOT NULL        -- mesma convenção de products.photo_path
  position    integer NOT NULL             -- 0..N-1, ordem da galeria
  is_primary  boolean NOT NULL DEFAULT false
  created_at, updated_at (TimestampMixin)

  UNIQUE  (product_id, photo_path)
  UNIQUE  (product_id) WHERE is_primary          -- no máximo 1 principal (índice parcial)
  INDEX   (product_id, position)
```

Invariante (mantida **em um único serviço**, nunca espalhada): se o produto tem fotos, exatamente uma é principal e `products.photo_path` é o `photo_path` dela; se não tem fotos, `photo_path` é `NULL`.

**Por que assim**
- API e UI **uniformes**: toda foto tem `id` e flag `is_primary`; "definir principal" é trocar uma flag, não trocar caminhos de lugar.
- **Zero quebra**: tudo que lê `photo_path` (PDF, snapshots, conjuntos, orçamento, sync EU, backup, leitores externos como o Estoque) continua certo.
- **Exclusão segura de graça**: `is_upload_referenced` e o inventário de órfãs já varrem a tabela nova.
- Sem coluna de mercado: o mercado vem do produto (como `product_supplied_fabric`). Toda rota carrega o `Product` pela consulta com mercado ativo (barreira ORM, `db/market_scope.py`) **antes** de tocar nas fotos. A tabela **não** entra em `MARKET_SCOPED_MODELS`.

**Alternativas descartadas**
- *Só a tabela, removendo `photo_path`*: quebra todos os consumidores e leitores externos; migration arriscada.
- *Principal = `photo_path`, galeria = tabela só de extras* (sem backfill, menor risco): a API fica assimétrica (a principal não tem `id`; "definir principal" vira troca de valores entre coluna e linha). É o **plano B** se o time preferir o menor risco de migration; o custo é API/UI menos limpas.

### Migration Alembic (aditiva, compatível com a API anterior)
- `down_revision = "supplied_fabric_eu_r42"`, nova revision (ex.: `product_photos_r43`).
- `create_table` + índices; **backfill idempotente**: `INSERT … SELECT gen_random_uuid(), id, photo_path, 0, true FROM products WHERE photo_path IS NOT NULL AND NOT EXISTS (…)`. Não move arquivo nenhum.
- `downgrade`: antes do `drop_table`, regrava `products.photo_path` com a principal (garante a coluna certa) e remove a tabela.
- Atualizar `tests/test_order_stage_migration.py:49` (`script.get_heads() == [...]`) para o novo head.
- Deploy: o `preDeployCommand` roda a migration antes de subir a API nova; na janela, a API **antiga** pode gravar `photo_path` sem refletir na tabela. Mitigação: o serviço "cura" a divergência (se a linha principal diverge de `products.photo_path`, corrige antes de mutar) e o backfill pode ser reexecutado com segurança.

## 4. API (backend)

Mesmo RBAC de hoje: `_ADMIN_VENDEDOR` (admin, vendedor, produtos). Cliente/executivo/representante → 403. Mercado: consulta do produto com `market_code == principal.code`, ativo e disponível (reaproveitar o `select` de `upload_photo`); fora do mercado ⇒ 404. EU compartilhado com BR ⇒ **403 em toda mutação** (mesma regra e mensagem atuais). Extrair `_load_product_for_photo_edit(...)` para os endpoints novos e os legados.

| Método e rota | Efeito |
|---|---|
| (leitura) `ProductRead.photos` | Lista ordenada `[{id, position, is_primary, photo_url, thumbnail_url}]`, mais `photo_count`. Vem em `GET ""`, `/batch`, `GET /{id}`. `photo_url`/`thumbnail_url` do produto = principal (inalterado). |
| `POST /products/{id}/photos` (multipart `file`) | Adiciona ao fim. Se for a primeira, vira principal. Limite de N fotos. Devolve `ProductRead`. |
| `DELETE /products/{id}/photos/{photo_id}` | Remove a linha; se era a principal, promove a próxima por `position` (ou zera `photo_path` se acabou). Reindexa `position`. Depois do commit: `delete_upload_if_unreferenced(path, market=)`. |
| `PUT /products/{id}/photos/order` body `{photo_ids:[…]}` | Reordena. Exige o **conjunto exato** de ids do produto (faltando/sobrando/de outro produto → 422). |
| `PUT /products/{id}/photos/{photo_id}/primary` | Marca principal (desmarca a anterior na mesma transação) e atualiza `products.photo_path`. Não mexe em arquivo. |
| **Legados mantidos** `POST /upload-photo`, `DELETE /photo` | `upload-photo` = "**substitui a principal**" (comportamento de hoje, usado pelo upload em lote por código): cria a nova como principal no lugar da antiga e remove a antiga. `DELETE /photo` = remove a principal (promove a próxima). |
| `POST /products/platform/EU/{id}/photos` | Wrapper fino de plataforma, igual ao `upload-photo` EU atual (preparação com mercado fechado). |

Regras comuns
- **Concorrência**: `SELECT … FOR UPDATE` na linha do produto durante a mutação (serializa contagem, `position` e troca de principal).
- **Atomicidade de arquivo**: gravar arquivo → inserir/commitar; se o commit falhar, apagar o arquivo novo (padrão atual). Em remoção, commit primeiro e só então `delete_upload_if_unreferenced(..., market=product.market_code)`.
- **Upload**: um arquivo por requisição (o front envia em fila, 2-3 em paralelo, como o upload em lote já faz — comentário "evita estouro de buffer no Railway"). Mesmos limites: 5 MB, jpg/png/webp, 25 MP.
- **Limite proposto**: 10 fotos por produto (constante/config; `409` ao exceder). Ver Q2.
- `PATCH /products/{id}` **não** aceita `photos`/`photo_path` (evita mass assignment).
- `source_version`: não incrementar, igual ao upload atual (Q8). Nada de Estoque/outbox/webhook é tocado.
- Desempenho: `Product.photos = relationship(order_by=position, lazy="selectin", cascade="all, delete-orphan")` (mesma convenção de `optionals`/`set_items`); medir uma página de 24 produtos × 10 fotos (payload e nº de queries).

### 4.1 Sincronização EU e órfãs
- `markets.py` (cópia BR→EU): iterar `product_photos` de produtos EU cujo caminho não é `eu-*`, copiar cada um, atualizar a linha **e** `products.photo_path` se for a principal; manter `remaining`/`failed`.
- `media_orphans.py`: incluir `"product_photos"` em `_PRIORITY_TABLES`. Nenhuma outra mudança.
- `_delete_upload`/`persist_upload`/`build_*`: **sem mudança**.

## 5. Frontend

### 5.1 Tela Produtos (`/produtos`, `ProdutosPage.tsx`)
- **Card externo** (`CatalogImage`): continua mostrando a miniatura principal (sem custo extra na grade). Se `photo_count > 1`: selo discreto com ícone + contagem (ex.: "3") no canto da foto e, no desktop, pontinhos de posição. Alternar miniaturas no hover/foco é fase 2, só se a medição de rolagem permitir. Sem mudar o `aspect-square`/`object-contain`.
- **Detalhe ao clicar** (`FullProductImage` → novo `ProductGallery`):
  - imagem grande (mantém o efeito miniatura→original) + faixa de miniaturas (horizontal, rolável);
  - setas ←/→ e teclado (←/→, Home/End), contador "2/5", **swipe** no celular (scroll-snap), pré-carregar a próxima/anterior;
  - `aria-label`/`aria-current` nas miniaturas, foco gerenciado dentro do diálogo que já existe (`role="dialog"`), respeita `prefers-reduced-motion`;
  - sem fotos: mantém "Sem foto"; com 1 foto: layout atual (sem setas).
  - (Opcional, Q1) botão **"Definir como principal"** na miniatura, só para papéis que editam (admin/vendedor/produtos) — chama `PUT …/primary`.

### 5.2 Cadastro > Produtos (`CadastroPage.tsx`) — onde se gerencia
- Trocar a caixa única "Foto" (L2175-2210) por `ProductPhotosManager`: grade de miniaturas com selo **Principal**, ações **Definir como principal**, **Remover**, **mover ← →** (botões acessíveis; arrastar é bônus), **Adicionar fotos** (`input multiple`, envio em fila com progresso e erro por arquivo).
- Produto **existente**: cada ação é uma requisição própria (aplica na hora; botão desabilitado enquanto pende; o 403 de EU compartilhado exibe a mensagem do servidor).
- Produto **novo** (ainda sem id): fotos ficam em fila local; após `create`, sobem em ordem e a escolhida como principal é marcada ao final.
- Tabela e detalhe expandido: miniatura principal + selo de quantidade.
- Upload em lote por nome de arquivo (L742): fica no comportamento atual ("substitui a principal"); alternativa "adicionar à galeria" é a Q5.
- Hooks novos em `hooks/useProducts.ts` (`useAddProductPhoto`, `useRemoveProductPhoto`, `useReorderProductPhotos`, `useSetPrimaryProductPhoto`) com `invalidateQueries(['products'])`. `types/index.ts`: `ProductPhoto`, `Product.photos?`, `photo_count?` (opcionais ⇒ cache/API antiga não quebra). Fixtures: `productTestUtils.tsx`, `demo.ts`.
- Mobile: gerenciador em grade de 3 colunas, alvos de toque ≥ 44 px, ações sempre visíveis (sem depender de hover).
- Textos novos em `lib/cadastroText.ts` (PT/EN) — o EU usa a mesma tela traduzida.

### 5.3 PDF / orçamento / pedidos
- **Sem mudança** (usam a principal). Portanto **não regenerar** `pdf-render.js`. Se a Q4 mudar isso: `npm run build:pdf-bundle` + `npm run check:pdf-bundle`, e o snapshot v2 continua só com a principal (pedido imutável).

## 6. Testes a criar

**Backend**
- Migration: head novo (`test_order_stage_migration.py`); backfill cria 1 linha principal por produto com foto, produto sem foto fica sem linha; reexecução não duplica; downgrade restaura `photo_path`.
- Endpoints (padrão de `integration/test_media_storage.py` e `test_shared_photo_not_deleted.py`): primeira foto vira principal; limite e `409` acima; remover principal promove a próxima e espelha `photo_path`; remover a última zera `photo_path`; reordenar exige conjunto exato (id alheio/faltando → 422); definir principal troca flag e `photo_path`; índice parcial impede 2 principais.
- RBAC/escopo: admin/vendedor/produtos ok; cliente/executivo/representante 403; sem token 401; produto de outro mercado 404; EU compartilhado com BR → 403 em **todas** as mutações; rota de plataforma exige `platform_admin`.
- Arquivo: troca/remoção só apaga se não referenciado; foto emprestada do BR não é apagada pelo EU; foto citada em snapshot de e-mail (`order_email_documents`) não é apagada; falha de commit apaga o arquivo recém-gravado; >5 MB / tipo inválido / pixels acima do limite rejeitados.
- Órfãs: foto referenciada **só** por `product_photos` não é órfã (`test_eu_media_orphans.py`); sync EU copia a galeria e mantém `photo_path` da principal.
- Legado: `upload-photo` substitui a principal e preserva as extras; `DELETE /photo` remove a principal.
- Contrato: `test_openapi_contract.py` expõe as rotas novas; `ProductRead` traz `photos` e `photo_count`; nº de queries da listagem não cresce por produto (sem N+1).
- Invariante: teste de consistência `photo_path == principal` após cada operação.

**Frontend** (Vitest/RTL, padrão de `ProdutosPage.test.tsx` e `CadastroPage.media.test.tsx`)
- Galeria: setas, teclado, miniatura troca imagem, contador, 0/1/N fotos, foco no diálogo, falha de imagem.
- Card: selo só com `photo_count > 1`; sem regressão de `thumbnail_url`/retry (`useImageRetry`).
- Gerenciador: adicionar várias (fila/erro parcial), remover, definir principal, reordenar, produto novo (fila pós-create), mensagem do 403 EU.
- Testes existentes que montam `Product` continuam passando (campos novos opcionais).
- Verificação visual no celular (375 px) do gerenciador e da galeria na fase de implementação.

## 7. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| `photo_path` e tabela divergirem (API antiga durante o deploy, script, `seed.py`) | Serviço único de mutação; auto-cura antes de mutar; teste de consistência; backfill reexecutável |
| Apagar arquivo ainda usado (PDF em fila, EU emprestando do BR) | Mantém `delete_upload_if_unreferenced(..., market=)` depois do commit; testes citados |
| Upload de várias fotos estourar buffer/threads | 1 arquivo por requisição, fila com 2-3 paralelas, semáforo de imagem já existente |
| Payload da listagem maior | Limite de 10 fotos; medir 24×10; se pesar, a listagem leva só `photo_count` e o detalhe busca `GET /{id}` |
| Rolagem lenta no catálogo | Card segue com 1 imagem; alternância no hover só na fase 2 |
| Regressão no PDF/pedido | Nada muda neles; bundle não regenerado; testes existentes de snapshot rodam |
| Mexer em Estoque por engano | Fora de escopo: sem `source_version`, sem outbox/webhook |

## 8. Divisão em PRs pequenos

1. **PR 1 — Backend base (aditivo)**: modelo + migration/backfill + serviço de fotos + schema `photos`/`photo_count` + endpoints + legados reescritos sobre o serviço + sync EU + `_PRIORITY_TABLES` + testes. O front antigo continua funcionando intacto.
2. **PR 2 — Front: ver**: types, selo no card, `ProductGallery` no detalhe de `/produtos`, testes. Só leitura.
3. **PR 3 — Front: gerenciar**: `ProductPhotosManager` no Cadastro, hooks de mutação, textos PT/EN, atalho "definir principal" no detalhe se aprovado, testes.
4. **PR 4 (opcional, só se Q4)**: galeria no orçamento/PDF com regeneração do bundle.

Ordem: PR 1 → 2 → 3. O PR 1 pode ir a produção sozinho (migration aditiva, compatível com a API anterior).

## 9. Perguntas em aberto para o usuário

- **Q1.** "Aba de produtos": o gerenciamento (adicionar/remover/ordenar/**principal**) fica no **Cadastro > Produtos** (onde já se edita), com a tela **Produtos** só mostrando a galeria? Ou também quer "definir como principal" direto na galeria de `/produtos`? *(Recomendado: gerenciar no Cadastro + atalho opcional na galeria só para quem edita.)*
- **Q2.** Limite de fotos por produto: **10** está bom? O tamanho continua 5 MB por foto?
- **Q3.** Quem gerencia: manter os mesmos de hoje (admin, vendedor, produtos)? *(Recomendado: sim.)*
- **Q4.** A galeria deve aparecer também no **orçamento** e/ou no **PDF**, ou só na tela Produtos? *(Recomendado: só Produtos; orçamento/PDF seguem com a principal.)*
- **Q5.** O **upload em lote por código** deve continuar **substituindo a principal** ou passar a **adicionar à galeria**? *(Recomendado: manter substituir; oferecer "adicionar" depois.)*
- **Q6.** Portugal (EU): produtos EU compartilhados com o BR continuam bloqueados para alterar fotos (403 atual), ou a galeria EU deve ser independente do BR?
- **Q7.** Ao remover a foto principal, promover automaticamente a próxima? *(Recomendado: sim.)*
- **Q8.** Trocar a principal / adicionar foto deve incrementar `products.source_version` (aviso de "produto mudou" para o Estoque)? Hoje o upload de foto **não** incrementa; a decisão é de quem cuida da integração — este plano não toca em Estoque.
- **Q9.** No card do catálogo basta o selo com a contagem, ou quer também alternar as fotos ao passar o mouse / deslizar no celular direto no card?
