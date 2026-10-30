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
    'W 1200 mm × D 500 mm × H 750 mm',
  )
  assert.equal(
    formatDimensions(
      { is_circular: true, largura: 1, profundidade: 0.5, altura: 0.75 },
      'EU',
      'en-GB',
    ),
    'Ø 1000 mm × H 750 mm',
  )
})

test('mm ≥ 1000 saem sem separador de milhar, com o mesmo número em en-GB e pt-PT', () => {
  const sofa = { is_circular: false, largura: 1.2, profundidade: 0.8, altura: 0.755 }
  assert.equal(formatDimensions(sofa, 'EU', 'en-GB'), 'W 1200 mm × D 800 mm × H 755 mm')
  assert.equal(formatDimensions(sofa, 'EU', 'pt-PT'), 'L 1200 mm × P 800 mm × A 755 mm')
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
