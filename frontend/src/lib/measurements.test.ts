import assert from 'node:assert/strict'
import test from 'node:test'

import { formatDimensions, metresToInches } from './measurements.ts'

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
