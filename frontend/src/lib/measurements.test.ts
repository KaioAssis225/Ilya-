import assert from 'node:assert/strict'
import { test } from 'vitest'

import { formatDimensions, metresToInches, metresToMillimetres } from './measurements.ts'

test('mantém metros e rótulos brasileiros no mercado BR', () => {
  assert.equal(
    formatDimensions(
      { is_circular: false, largura: 1.2, profundidade: 0.5, altura: 0.75 },
      'BR',
      'pt-BR',
    ),
    'L 1,20 × P 0,50 × A 0,75 m',
  )
})

test('converte a apresentação europeia para polegadas sem alterar o valor canónico', () => {
  assert.equal(metresToInches(1), 39.3700787402)
  assert.equal(
    formatDimensions(
      { is_circular: true, largura: 1, profundidade: 0.5, altura: 0.75 },
      'EU',
      'en-GB',
    ),
    'Ø 39.37″ × H 29.53″',
  )
})

test('converte a apresentação europeia em português para milímetros', () => {
  assert.equal(metresToMillimetres(1), 1000)
  assert.equal(
    formatDimensions(
      { is_circular: false, largura: 1.2, profundidade: 0.5, altura: 0.75 },
      'EU',
      'pt-PT',
    ),
    'L 1200 mm × P 500 mm × A 750 mm',
  )
})
