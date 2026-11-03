# ADR 0003 — Abas "Orçamento" e "Pedido"

## Status

Aceito.

## Contexto

Um orçamento (`ORC-…`) vira pedido (`PED-…`) ao ser finalizado
(`POST /orders/{id}/finalize`). Até aqui a aba "Orçamento" (`/pedidos`) listava
orçamentos e pedidos juntos, distinguidos só por um selo de status.

## Decisão

| Aba | Rota | Lista (`GET /orders?status=`) |
| --- | --- | --- |
| Orçamento | `/pedidos` (inalterada) | `not_finalized`: em andamento **e** cancelados |
| Pedido | `/pedidos-finalizados` | `finalized` |

- **Mesmo componente.** `PedidosPage` recebe `scope="quotes" | "orders"`; não há
  segunda página. O detalhe, o PDF, a aba E-mails e a auditoria geral funcionam
  nos dois escopos.
- **Filtro no servidor.** `status` ganhou o valor `not_finalized`. Os valores
  antigos (`in_progress`, `finalized`, `cancelled`) mantêm o contrato. RBAC,
  isolamento por mercado e paginação por cursor continuam aplicados junto do
  filtro de status. Sem `status`, o endpoint segue listando tudo.
- **Mover ao finalizar.** `useFinalizeOrder` já invalida `['orders']`; a lista de
  Orçamento é refeita com `not_finalized` e o item sai, aparecendo em Pedido. A
  tela de Orçamento mostra um aviso com o botão "Ver em Pedido".
- **Acesso.** As duas abas usam `canSeeOrcamentoPedidos` (mesmas regras de papel).

### Cancelados

Só orçamento **não finalizado** pode ser cancelado (`POST /orders/{id}/cancel`
responde 409 para finalizado), e um cancelado não pode ser finalizado. Logo, um
cancelado nunca foi pedido: **fica em Orçamento**, com o selo "Cancelado" e o
filtro de status (Todos / Em andamento / Cancelados). Pedido nunca contém
cancelados.

### Revisões

`POST /orders/{id}/revision` só aceita pedido finalizado e cria um **novo
orçamento** em andamento (`supersedes_order_id` aponta para o original,
`revision_number + 1`). A revisão aparece em **Orçamento** até ser finalizada; o
pedido original permanece intacto em **Pedido**. Ao finalizar a revisão, ela
também vai para Pedido.

## Consequências

- Links antigos para `/pedidos` continuam válidos; passam a mostrar só
  orçamentos não finalizados.
- Quem tinha costume de achar um pedido finalizado em Orçamento passa a procurá-lo
  em Pedido.
