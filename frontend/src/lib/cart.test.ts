import assert from 'node:assert/strict'
import test from 'node:test'

import { cartStorageKey, countCartUnits } from './cart.ts'

test('separa o carrinho por identidade e mercado', () => {
  assert.equal(cartStorageKey('user-1', 'BR'), 'carrinho_orcamento:user-1:BR')
  assert.equal(cartStorageKey('user-1', 'EU'), 'carrinho_orcamento:user-1:EU')
  assert.notEqual(cartStorageKey('user-1', 'BR'), cartStorageKey('user-2', 'BR'))
})

test('conta unidades, não apenas SKUs distintos', () => {
  assert.equal(countCartUnits({ cadeira: 2, mesa: 3 }), 5)
  assert.equal(countCartUnits({}), 0)
})
