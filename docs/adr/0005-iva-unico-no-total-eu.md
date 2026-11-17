# 0005 — IVA único de Portugal, aplicado só no total

Status: aceito (17/11/2026)

## Contexto

O IVA do mercado EU era tratado como o ICMS/IPI do Brasil: uma taxa **por
produto** (`product_markets.vat_rate`), com aprovação nominal por SKU/grupo, e o
pedido somava o imposto linha a linha. Em Portugal o IVA é uma taxa única,
cobrada **uma vez sobre o total** do documento.

## Decisão

- A taxa vive em `markets.vat_rate` (só o EU; BR fica `NULL` e segue com IPI por
  grupo). Valor inicial: 23,00 (a taxa já usada em todos os SKUs aprovados).
  Escolhida em vez de uma tabela de configuração porque `markets` já é a
  fonte única do mercado (moeda, rótulo do imposto, ativação): uma coluna
  aditiva, sem tabela nova de leitura no caminho do pedido.
- Quem altera: admin do mercado EU (`PUT /api/v1/markets/EU/vat-rate`) ou
  `platform_admin` (`.../platform`). O servidor valida 0–100 com duas casas.
  Toda mudança grava `market_vat_rate_events` (quem, quando, de → para).
- **Cálculo**: as linhas EU não levam IVA (`ipi_rate = 0`, `ipi_value = 0`). O
  IVA do documento é `round_half_up(subtotal × taxa / 100, 2)` — **um só
  arredondamento, na base total** — onde `subtotal` é a soma das linhas (já com
  descontos, cada uma arredondada a 2 casas como sempre). Isento (`vat_exempt`)
  zera o IVA, com o motivo de sempre, mas o documento ainda guarda a taxa.
- **Snapshot**: `orders.vat_rate` guarda a taxa usada. Mudar a taxa nunca altera
  pedido finalizado. Orçamento aberto só passa a usar a taxa nova quando é
  recalculado ou editado (`PUT /orders/{id}` com itens) ou revisado. Documento
  anterior a esta decisão fica com `vat_rate = NULL` e IVA por linha, intocado.
- O IVA por produto (colunas de `product_markets`) deixa de ser lido para vender,
  ativar o mercado, importar CSV ou criar protótipo. As colunas e os dados ficam
  (remoção por migração fica para depois).
- **Moloni**: o Moloni exige imposto por linha; cada linha (e o artigo novo)
  leva a mesma taxa única do pedido. O Moloni arredonda o IVA linha a linha,
  então o total dele pode diferir do nosso por centavos.

## Consequências

- O BR não muda.
- Sem taxa configurada o pedido EU é recusado (422): nunca se fatura com 0%
  por omissão. A ativação do mercado EU também exige a taxa.
