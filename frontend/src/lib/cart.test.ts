import assert from 'node:assert/strict'
import test from 'node:test'

import { cartStorageKey, countCartUnits, privateScopeKey } from './cart.ts'

test('separa o carrinho por identidade e mercado', () => {
  assert.equal(cartStorageKey('user-1', 'BR'), 'carrinho_orcamento:user-1:BR')
  assert.equal(cartStorageKey('user-1', 'EU'), 'carrinho_orcamento:user-1:EU')
  assert.notEqual(cartStorageKey('user-1', 'BR'), cartStorageKey('user-2', 'BR'))
})

test('conta unidades, não apenas SKUs distintos', () => {
  assert.equal(countCartUnits({ cadeira: 2, mesa: 3 }), 5)
  assert.equal(countCartUnits({}), 0)
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
