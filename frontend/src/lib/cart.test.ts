import assert from 'node:assert/strict'
import { test } from 'vitest'

import { cartStorageKey, configureProductPath, countCartUnits, privateScopeKey, readCartQuantities } from './cart.ts'

test('separa o carrinho por identidade e mercado', () => {
  assert.equal(cartStorageKey('user-1', 'BR'), 'carrinho_orcamento:user-1:BR')
  assert.equal(cartStorageKey('user-1', 'EU'), 'carrinho_orcamento:user-1:EU')
  assert.notEqual(cartStorageKey('user-1', 'BR'), cartStorageKey('user-2', 'BR'))
})

test('conta unidades, não apenas SKUs distintos', () => {
  assert.equal(countCartUnits({ cadeira: 2, mesa: 3 }), 5)
  assert.equal(countCartUnits({ tapete: { qty: 4.5, sold_by_area: true }, cadeira: { qty: 2, sold_by_area: false } }), 3)
  assert.equal(countCartUnits({}), 0)
})

test('lê venda por área e mantém carrinhos antigos como unidades', () => {
  localStorage.setItem(cartStorageKey('user-cart', 'BR'), JSON.stringify([
    { product_code: 'TAP-1', qty: 4.5, sold_by_area: true },
    { product_code: 'CAD-1', qty: 2 },
  ]))

  const quantities = readCartQuantities('user-cart', 'BR')
  assert.deepEqual(quantities, {
    'TAP-1': { qty: 4.5, sold_by_area: true },
    'CAD-1': { qty: 2, sold_by_area: false },
  })
  assert.equal(countCartUnits(quantities), 3)
})

test('a fronteira privada muda ao trocar de mercado', () => {
  // `PrivateApp` usa esta chave como `key` do provider: se ela muda, a árvore
  // privada é desmontada e cache, mutations e estado local das páginas vão com
  // ela. É o que impede BR de renderizar dados carregados em PT.
  assert.notEqual(privateScopeKey('user-1', 'BR'), privateScopeKey('user-1', 'EU'))
  assert.notEqual(privateScopeKey('user-1', 'BR'), privateScopeKey('user-2', 'BR'))
  assert.equal(privateScopeKey('user-1', 'BR'), 'user-1:BR')
})

test('a chave do carrinho acompanha a fronteira privada', () => {
  // As duas precisam concordar: um cache novo com o carrinho antigo mostraria
  // itens do mercado anterior.
  for (const market of ['BR', 'EU'] as const) {
    assert.ok(cartStorageKey('user-1', market).endsWith(privateScopeKey('user-1', market)))
  }
})

test('produto com aplicações abre a configuração na rota real do orçamento', () => {
  assert.equal(configureProductPath('Teste'), '/orcamentos?configure=Teste')
  assert.equal(configureProductPath('SKU 1/2'), '/orcamentos?configure=SKU%201%2F2')
})

test('countCartUnits conta peças de tapete quando informadas', () => {
  assert.equal(countCartUnits({ tapete: { qty: 9.5, sold_by_area: true, area_pieces: 3 }, cadeira: { qty: 2, sold_by_area: false } }), 5)
  assert.equal(countCartUnits({ tapete: { qty: 4.5, sold_by_area: true } }), 1)
})
