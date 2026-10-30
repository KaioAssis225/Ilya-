import assert from 'node:assert/strict'
import { test } from 'vitest'

import { formatDimensions, metresToMillimetres } from './measurements.ts'

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

test('mostra a apresentação europeia em inglês em milímetros, com rótulos W/D/H', () => {
  assert.equal(
    formatDimensions(
      { is_circular: false, largura: 1.2, profundidade: 0.5, altura: 0.75 },
      'EU',
      'en-GB',
    ),
    'W 1,200 mm × D 500 mm × H 750 mm',
  )
  assert.equal(
    formatDimensions(
      { is_circular: true, largura: 1, profundidade: 0.5, altura: 0.75 },
      'EU',
      'en-GB',
    ),
    'Ø 1,000 mm × H 750 mm',
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
