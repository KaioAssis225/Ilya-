# Reestruturação de layout — Cadastros e Orçamento (FRN-17, FRN-18, FRN-25)

**Data:** 2026-10-23 · **Branch:** `codex/layout-cadastros-orcamento` (base `origin/main` = `9a2e3e82`) ·
**Baseline da auditoria:** `93baae7e` — preservada; as três páginas-alvo eram idênticas entre `93baae7e` e `9a2e3e82`.
**Pacote de origem:** `Documents\ChatGPT\Ilya\auditoria-frontend-2026-10-21\PACOTE-PARA-FABLE-EXECUCAO`.
**Execução:** Fable 5.1 (orquestração, revisão final e correções) · Codex CLI `gpt-5.6-sol` (implementação, effort high nos FRN-17/25 e medium no FRN-18) · Opus 5.5 (leitura do pacote e revisão independente) · DeepSeek V4 Pro (harness de capturas e revisão independente).

## O que mudou

### FRN-17 — Cadastro de Produtos (`frontend/src/pages/CadastroPage.tsx`, `frontend/src/lib/productColumns.ts`)
- Workspace de Cadastros ampliado de `max-w-7xl` (1280px) para 1680px; painel com `p-4 xl:p-6`.
- Menu lateral **recolhível**: rail de 72px (ícone + contagem) por padrão abaixo de 1680px, completo (220px) acima; botão com `aria-expanded`/`aria-controls`; preferência do usuário persistida em `localStorage['cadastros_sidebar_collapsed']` (sem o TTL de 5 min do estado de aba).
- Tabela desktop com **colunas primárias**: [detalhes] · Código · Descrição (com miniatura 40px) · Tipo · Lojista · Corporativo · PVP/Arquiteto (EU) · Ações. Preços alinhados à direita, `tabular-nums`, nunca quebram.
- **Linha de detalhe expansível** por produto (botão com `aria-expanded`, Enter/Espaço): dimensões, opcionais/aplicações, EAN, categoria de artigo e foto 96px. Nenhum dado de negócio saiu da tela.
- **Auto-ajuste das larguras ao container** (callback ref + `ResizeObserver` + `useLayoutEffect`) respeitando mínimos (`PRODUCT_COLUMN_MIN_WIDTHS`); o estado inicial não depende mais de "Ajustar à tela". Quando os mínimos não cabem, a coluna Ações fica `sticky` à direita (fundo opaco) e aparece a pista "Role para ver mais colunas →". Arrastar/duplo clique pausam o auto-ajuste; "Ajustar à tela" reativa; "Restaurar" volta às larguras padrão fixas.
- Cabeçalhos ordenáveis (Código, Descrição, Lojista) agora são `<button>` com `aria-sort` no `<th>`.

### FRN-18 — Clientes/Representantes (`CadastroPage.tsx`, componente `PeopleTab` e `Th`)
- `table-fixed` com `colgroup` (mínimos 812px com "Criado por", 682 sem): Nome · Contato (telefone em linha própria, `whitespace-nowrap`; e-mail abaixo) · Cidade · UF (mesma célula) · Desc. máx. · Criado por · Ações (`sticky right-0`, sempre alcançáveis).
- `Th` renderiza **botões de ordenação** focáveis com `aria-sort` no `<th>` (atende FRN-14 neste trecho); os cabeçalhos agrupados mantêm as seis ordenações existentes (Telefone/E-mail, Cidade/UF).

### FRN-25 — Orçamento (`frontend/src/pages/OrcamentoPage.tsx`)
- **Hipótese A** escolhida: a `<table min-w-[920px]>` desktop virou lista de itens (`<ul>/<li>`). Cada item tem bloco de identidade (foto, código, descrição, componentes, dimensões, seletores de acabamento e aplicações) e uma **faixa numérica** com rótulos (Qtd, Preço base, Desconto, IPI/IVA, Subtotal, Remover) que reflui (`flex-wrap`): abaixo da identidade em `lg` (1024–1279), à direita em `xl+`. Subtotal e Remover ficam sempre juntos e visíveis, sem rolagem horizontal.
  - B (painel recolhível/abaixo) foi descartada: continuaria exigindo ~920px e esconderia cliente/representante/finalizar atrás de interação.
- Container `max-w-[1600px]`; painel lateral 320px em `lg`, 360px em `xl+`.
- Acabamento: `<select>` de `OptionalSelectors` perdeu o teto de 100px (`flex-1 max-w-[240px]`, chip `max-w-full`) e ganhou `title` com o nome completo — vale para desktop e mobile; textos de acabamento com `break-words`.
- Fórmulas (`effectivePrice`, `subtotal`, `subtotalWithIpi`), callbacks, persistência do carrinho, edição, PDF, `OrderForm`, barra fixa móvel, `BottomDrawer` e `MobileCartCard` intactos.

### Outros
- `frontend/src/lib/cadastroText.ts`: traduções en-GB dos textos novos.
- FRN-06 (navegação móvel): **não tocado** — não interferiu nas três superfícies.
- Modais canônicos (`QuickRegisterModal`, `PhotoLightbox`, `BottomDrawer`): **não migrados** para `Dialog` — o pacote é vago sobre quais, e a estrutura móvel devia ser preservada.

## Validação local (worktree em disco local, Node 26, npm ci)
| Comando | Resultado |
|---|---|
| `npm run lint` | passou (0 avisos) |
| `npm run build` | passou |
| `npm run test` | 20 arquivos, 105 testes, todos passando (baseline `9a2e3e82`: 18 arquivos, 92 testes) |
| `npm run test:e2e` | **não executado** — exige Docker Compose + seed; no drive de rede o compose falha nos bind mounts (ver limitações) |

Testes novos: `CadastroPage.layout.test.tsx` (detalhe expansível por clique e teclado, menu persistido e relido, PVP/Arquiteto no EU, `fittedProductColumnWidths`), `CadastroPage.people.test.tsx` (telefone íntegro + e-mail na mesma célula, ações por linha, ordenação por teclado com `aria-sort` e `sort_dir=desc` no request), `OrcamentoPage.test.tsx` (+4: remoção dentro do item, subtotal × quantidade, ausência de `<table>`, `title` do acabamento).

### Capturas antes/depois (harness Playwright com API mockada, fixtures sintéticas BR/EU)
Matriz 1920/1440/1280/1024/768/390 × BR/EU × {produtos, clientes, representantes, orçamento} = 96 PNG "antes" (build de `9a2e3e82`) e 96 "depois", mais orçamento com 50 itens (1440/390). Arquivos em `Documents\ChatGPT\Ilya\auditoria-frontend-2026-10-21\EXECUCAO-FABLE-2026-10-23\`.

Conferido visualmente: produtos BR 1440 (todas as colunas e ações visíveis, antes só "LC"/"R$"), produtos EU 1440 (4 preços + ações), produtos EU 1280 (rolagem com ações fixas e pista), clientes BR 1440 (telefone inteiro, nome em 2 linhas no máximo, ações alinhadas), representantes EU 1024, orçamento BR/EU 1440 e 1280 (subtotal + lixeira juntos, acabamento longo legível), orçamento 1024 (faixa abaixo da identidade), orçamento 390 (estrutura móvel igual ao antes), produtos BR 1920 (menu completo).

## FRN resolvidos × não resolvidos
| FRN | Estado |
|---|---|
| FRN-17 | Corrigido no código, validado localmente. Residual: em **EU a 1280px** (mínimos 1206px vs ~1070 úteis) e em **BR a 1024px** a tabela ainda rola na horizontal, com ações fixas e pista — PVP/Arquiteto exigem rolagem nessa faixa. |
| FRN-18 | Corrigido no código, validado localmente (1024–1920). |
| FRN-25 | Corrigido no código, validado localmente (1024–1920, 390 preservado). |
| FRN-14 | Parcialmente atendido (ordenação por teclado e `aria-sort` nas tabelas de pessoas e produtos); cards móveis sem equivalente, como antes. |
| FRN-06, FRN-22, FRN-01/02 | Não tocados (fora do lote). FRN-01/02 continuam dependentes de correção funcional própria; a lista de itens nova não altera `removeItem`, "Limpar" nem o submit. |

## Riscos e limites conhecidos
- `aria-controls` do botão de detalhes aponta para a `<tr>` só quando expandida (padrão comum, mas não ideal para alguns leitores).
- Badge de contagem no rail cobre o ícone com 3+ dígitos.
- A célula de ações fixa não acompanha o `hover` da linha; o autoajuste por duplo clique da coluna Descrição não soma a miniatura (fica ~52px estreito).
- Tabela de pessoas não tem pista de rolagem (só a coluna fixa) — cabe a partir de 1024px com o menu em rail; com o menu expandido manualmente em 1024px ela rola.
- Testes não exercitam `ResizeObserver` nem medem pixels (jsdom): o encaixe é coberto por teste unitário de `fittedProductColumnWidths` e pelas capturas.
- Sem alegação de WCAG, performance (P12/P13) ou homologação em produção: tudo acima é **implementado e verificado localmente**, não implantado.

## Ambiente e bloqueios reais encontrados
- `X:\Ilya` é drive de rede: `npm run test` falha por timeout dos workers do vitest e `npm run dev`/compose quebram; o trabalho foi feito no worktree local `Documents\ChatGPT\Ilya\.worktrees\layout-cadastros-orcamento`.
- Codex CLI com sandbox `workspace-write` recusa caminhos de rede e caminhos 8.3 (`MATHEU~1.CAR`); funcionou no worktree com caminho canônico.
- E2E Playwright do repositório não rodou (sem backend/seed disponíveis aqui); as capturas usam mocks de API, não o backend real.
