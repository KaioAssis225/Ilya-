import assert from 'node:assert/strict'
import test from 'node:test'

import { CADASTRO_EN_KEYS, translateCadastro } from './cadastroText.ts'

test('fora de en-GB todo texto volta identico -- o Brasil nao muda', () => {
  // O LocaleContext responde 'pt-PT' tambem no Brasil. Se qualquer chave fosse
  // alterada em pt, a tela brasileira mudaria de texto.
  for (const key of CADASTRO_EN_KEYS) {
    assert.equal(translateCadastro('pt-PT', key), key, key)
  }
})

test('en-GB traduz e cai para o portugues so quando falta a chave', () => {
  assert.equal(translateCadastro('en-GB', 'Todos os Catálogos'), 'All catalogues')
  assert.equal(translateCadastro('en-GB', 'texto sem traducao'), 'texto sem traducao')
})

test('variaveis reproduzem exatamente o texto antigo em portugues', () => {
  // Antes: `${totalItems} ${label.toLowerCase()} cadastrados`
  assert.equal(
    translateCadastro('pt-PT', '{count} {label} cadastrados', { count: 3, label: 'clientes' }),
    '3 clientes cadastrados',
  )
  assert.equal(
    translateCadastro('en-GB', '{count} {label} cadastrados', { count: 3, label: 'clients' }),
    '3 clients',
  )
})

test('a traducao usa as mesmas variaveis do original', () => {
  // Variavel perdida ou renomeada na traducao viraria "{count}" literal na tela.
  const vars = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()
  for (const key of CADASTRO_EN_KEYS) {
    assert.deepEqual(vars(translateCadastro('en-GB', key)), vars(key), key)
  }
})
