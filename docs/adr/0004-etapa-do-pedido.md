# ADR 0004 — Etapa do pedido: Produção e Entregue

## Status

Aceito. Quem pode mudar a etapa é um padrão adotado sem especificação do
usuário e pode ser ajustado (ver "Permissões").

## Contexto

Na aba "Pedido" (ADR 0003) todo pedido finalizado mostrava o selo "Finalizado".
Depois de finalizado, o pedido não tinha como indicar se já foi entregue.

## Decisão

O pedido finalizado ganha uma **etapa**, uma camada a mais sobre `is_finalized`
(que continua `true`; snapshot imutável, numeração PED, Moloni e e-mail por fila
não mudam):

| Etapa | Valor | Como entra |
| --- | --- | --- |
| Produção | `production` | Automática, no `POST /orders/{id}/finalize` |
| Entregue | `delivered` | Manual, em `POST /orders/{id}/stage` |

- **Voltar para Produção** é permitido (engano), pelo mesmo endpoint.
- **Dados.** `orders.order_stage` (texto + CHECK, sem enum Postgres, para o
  downgrade ser trivial), `production_started_at` e `delivered_at`. Orçamento em
  andamento ou cancelado tem `order_stage = NULL`. Constraints: valor válido,
  etapa só em pedido finalizado, `delivered_at` presente se, e somente se, a
  etapa for `delivered`.
- **Migration `order_stage_r34`.** Aditiva. Pedidos já finalizados (e não
  cancelados) entram em **Produção**, com `production_started_at = finalized_at`.
- **Histórico.** Cada mudança grava `OrderHistory` com `action = "stage_changed"`,
  `details = "production -> delivered"` (ou o inverso), quem e quando.
- **Versões.** A mudança incrementa `source_version` (frescor para consumidores
  externos) e **não** `document_version`: o documento/PDF não muda.
- **Idempotência.** Pedir a etapa em que o pedido já está devolve 200 sem
  histórico nem incremento de versão.
- **Listagem.** `GET /orders?stage=production|delivered`; a resposta traz
  `order_stage`, `production_started_at` e `delivered_at`.
- **Interface.** Na aba Pedido o selo "Finalizado" dá lugar à etapa (Produção /
  Entregue; en-GB "In production" / "Delivered"). A ação não pede confirmação
  por ser reversível e auditada: a tela avisa e oferece "Desfazer". Há filtro
  "Etapa" no lugar de "Status" (que só existe em Orçamento). O PDF não muda.

## Permissões

Mesma regra de quem opera o pedido hoje (`_can_operate_order`): admin,
representante, produtos e operador interno de vendas. O representante só mexe nos
pedidos da própria carteira. A conta de cliente final **nunca** muda a etapa (403
antes de consultar o pedido); só vê o selo. Pedido de outro mercado, de outra
carteira ou inexistente responde 404 com a mesma mensagem. Pedido não finalizado
ou cancelado responde 409. O endpoint tem limite de 30 requisições por minuto por
usuário.

## Consequências

- Cancelamento segue as regras atuais (só orçamento não finalizado é cancelado).
- Voltar para Produção é uma ação explícita e fica no histórico.
- O papel `produtos` passa a poder marcar entrega, porque já opera o ciclo de
  vida do pedido. Se isso não for desejado, restringir `_can_operate_order` neste
  endpoint.
