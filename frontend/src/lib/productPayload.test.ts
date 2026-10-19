import assert from 'node:assert/strict'
import { test } from 'vitest'

import { withMarketProductNames } from './productPayload.ts'
import type { ProductCreate } from '../types/index.ts'

const baseProduct: ProductCreate = {
  product_code: 'TEST-EU',
  description: '  Nome principal  ',
  description_en: '  English name  ',
  is_circular: false,
  altura: 1,
  largura: 1,
  profundidade: 1,
  price: 1,
}

test('cadastro EU usa o nome principal também no campo português exigido pela API', () => {
  const payload = withMarketProductNames(baseProduct, true)

  assert.equal(payload.description, 'Nome principal')
  assert.equal(payload.description_pt_pt, 'Nome principal')
  assert.equal(payload.description_en, 'English name')
})

test('cadastro BR não inclui campos de tradução EU', () => {
  const payload = withMarketProductNames(baseProduct, false)

  assert.equal(payload, baseProduct)
  assert.equal(payload.description_pt_pt, undefined)
})
