import assert from 'node:assert/strict'
import test from 'node:test'

import { formatOrderMoney, resolveOrderDocument, resolveOrderPresentation } from './orderPresentation.ts'

test('usa moeda, locale e tributo do snapshot do pedido', () => {
  const br = resolveOrderPresentation({
    market_code: 'BR',
    currency: 'BRL',
    locale: 'pt-BR',
    items: [{ tax_label: 'IPI' }],
  })
  assert.deepEqual(br, { currency: 'BRL', locale: 'pt-BR', taxLabel: 'IPI' })

  const eu = resolveOrderPresentation({
    market_code: 'EU',
    currency: 'EUR',
    locale: 'pt-PT',
    items: [{ tax_label: 'IVA' }],
  })
  assert.deepEqual(eu, { currency: 'EUR', locale: 'pt-PT', taxLabel: 'IVA' })
})

test('o snapshot vence a configuração do mercado atual', () => {
  // Era o defeito: o rótulo saía de `market_code`, então mudar a regra fiscal
  // reescreveria o tributo de pedidos já contratados.
  const presentation = resolveOrderPresentation({
    market_code: 'EU',
    currency: 'BRL',
    locale: 'pt-BR',
    items: [{ tax_label: 'IPI' }],
  })
  assert.equal(presentation.taxLabel, 'IPI', 'o item manda, não o mercado')
  assert.equal(presentation.currency, 'BRL')
  assert.equal(presentation.locale, 'pt-BR')
})

test('pedido anterior às colunas cai no default do mercado', () => {
  assert.deepEqual(resolveOrderPresentation({ market_code: 'BR' }), {
    currency: 'BRL',
    locale: 'pt-BR',
    taxLabel: 'IPI',
  })
  assert.deepEqual(resolveOrderPresentation({ market_code: 'EU' }), {
    currency: 'EUR',
    locale: 'pt-PT',
    taxLabel: 'IVA',
  })
  // Sem mercado algum, BR é o default histórico.
  assert.equal(resolveOrderPresentation({}).currency, 'BRL')
})

test('item sem rótulo não zera o tributo do documento', () => {
  const presentation = resolveOrderPresentation({
    market_code: 'EU',
    items: [{}, { tax_label: 'IVA' }],
  })
  assert.equal(presentation.taxLabel, 'IVA')
})

test('locale en-GB do pedido europeu é preservado', () => {
  const presentation = resolveOrderPresentation({
    market_code: 'EU',
    currency: 'EUR',
    locale: 'en-GB',
    items: [{ tax_label: 'IVA' }],
  })
  assert.equal(presentation.locale, 'en-GB')
})

test('formata o valor na moeda e no locale do pedido', () => {
  const br = formatOrderMoney(1234.5, { currency: 'BRL', locale: 'pt-BR' })
  const eu = formatOrderMoney(1234.5, { currency: 'EUR', locale: 'pt-PT' })
  // Os separadores variam por plataforma/ICU; o que importa é o símbolo e que
  // os dois formatos sejam distintos.
  assert.match(br, /R\$/)
  assert.match(eu, /€/)
  assert.notEqual(br, eu)
})

test('PDF de Portugal sai em inglês com a marca IBTW', () => {
  const doc = resolveOrderDocument({ market_code: 'EU', currency: 'EUR', locale: 'pt-PT', items: [{ tax_label: 'IVA' }] })
  assert.equal(doc.brand, 'IBTW')
  assert.equal(doc.locale, 'en-GB')
  assert.equal(doc.taxLabel, 'VAT')
  assert.equal(doc.labels.order, 'ORDER')
  assert.equal(doc.labels.grandTotal, 'GRAND TOTAL:')
  assert.match(doc.labels.footer, /^IBTW/)
  assert.match(doc.labels.repSignature, /IBTW/)
})

test('PDF do Brasil continua em português com a marca ILYA', () => {
  const doc = resolveOrderDocument({ market_code: 'BR', currency: 'BRL', locale: 'pt-BR', items: [{ tax_label: 'IPI' }] })
  assert.equal(doc.brand, 'ILYA')
  assert.equal(doc.locale, 'pt-BR')
  assert.equal(doc.taxLabel, 'IPI')
  assert.equal(doc.labels.order, 'PEDIDO')
  assert.match(doc.labels.footer, /^Ilya/)
})
