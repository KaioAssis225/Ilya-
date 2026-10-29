import assert from 'node:assert/strict'
import { test } from 'vitest'

import { areaLimit, formatArea, formatRugPieces, formatRugSize, isAreaCatalogName, isAreaProduct, normalizeAreaQty, normalizeRugPieces, previewArea } from './areaProduct.ts'

test('reconhece somente os nomes normalizados do catálogo de tapetes', () => {
  assert.equal(isAreaCatalogName(' Tapete '), true)
  assert.equal(isAreaCatalogName('TAPETES'), true)
  assert.equal(isAreaCatalogName('Tapéte'), true)
  assert.equal(isAreaCatalogName('Carpet'), false)
  assert.equal(isAreaCatalogName(null), false)
  assert.equal(isAreaProduct({ catalog: { id: 'cat-1', name: 'Tapete' } }), true)
  assert.equal(isAreaProduct({ catalog: null }), false)
})

test('retorna limite apenas quando está ativo e é positivo', () => {
  const base = { catalog: null, area_limit_enabled: true }
  assert.equal(areaLimit({ ...base, max_area_m2: '12.5' }), 12.5)
  assert.equal(areaLimit({ ...base, max_area_m2: 0 }), null)
  assert.equal(areaLimit({ ...base, area_limit_enabled: false, max_area_m2: 12.5 }), null)
  assert.equal(areaLimit({ ...base, max_area_m2: null }), null)
})

test('normaliza m² para duas casas com mínimo de 0,01', () => {
  assert.equal(normalizeAreaQty(4.567), 4.57)
  assert.equal(normalizeAreaQty('4.504'), 4.5)
  assert.equal(normalizeAreaQty(0), 0.01)
  assert.equal(normalizeAreaQty(-10), 0.01)
})

test('formata área em português e inglês com zero a duas casas', () => {
  assert.equal(formatArea(4.5, 'pt-BR'), '4,5 m²')
  assert.equal(formatArea(4.5, 'pt-PT'), '4,5 m²')
  assert.equal(formatArea(4.5, 'en-GB'), '4.5 m²')
  assert.equal(formatArea(4, 'pt-BR'), '4 m²')
})

test('prévia de área calcula área mínima e ignora medidas inválidas', () => {
  assert.equal(previewArea(2.05, 2.05), 4.2)
  assert.equal(previewArea(0.05, 0.05), 0.01)
  assert.equal(previewArea(null, 2), null)
  assert.equal(previewArea(0, 3), null)
  assert.equal(previewArea(undefined, 1), null)
})

test('formatRugSize mostra medidas e área quando há dimensões válidas', () => {
  assert.equal(
    formatRugSize(2.05, 2.05, 4.2, 'pt-BR'),
    '2,05 × 2,05 m = 4,2 m²',
  )
  assert.equal(
    formatRugSize(null, undefined, 4.2, 'pt-BR'),
    '4,2 m²',
  )
  assert.equal(
    formatRugSize(0, 2, 4.2, 'pt-BR'),
    '4,2 m²',
  )
})

test('formatRugSize com múltiplas peças em pt-BR', () => {
  assert.equal(
    formatRugSize(2, 3, 12, 'pt-BR', 2),
    '2 × 3 m = 6 m² × 2 peças = 12 m²',
  )
  assert.equal(
    formatRugSize(null, null, 12, 'pt-BR', 2),
    '6 m² × 2 peças = 12 m²',
  )
})

test('formatRugSize com múltiplas peças em en-GB', () => {
  assert.equal(
    formatRugSize(2, 3, 12, 'en-GB', 3),
    '2 × 3 m = 4 m² × 3 pieces = 12 m²',
  )
  assert.equal(
    formatRugSize(null, null, 12, 'en-GB', 3),
    '4 m² × 3 pieces = 12 m²',
  )
})

test('normalizeRugPieces arredonda e limita o intervalo', () => {
  assert.equal(normalizeRugPieces(0), 1)
  assert.equal(normalizeRugPieces(2.6), 3)
  assert.equal(normalizeRugPieces(5000), 1000)
  assert.equal(normalizeRugPieces(Number.NaN), 1)
})

test('formatRugPieces usa plural correto por locale', () => {
  assert.equal(formatRugPieces(1, 'pt-BR'), '1 peça')
  assert.equal(formatRugPieces(3, 'pt-BR'), '3 peças')
  assert.equal(formatRugPieces(1, 'en-GB'), '1 piece')
  assert.equal(formatRugPieces(3, 'en-GB'), '3 pieces')
})
