import assert from 'node:assert/strict'
import { test } from 'vitest'

import { CADASTRO_EN_KEYS, fichaPt, translateCadastro } from './cadastroText.ts'

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

test('en-GB traduz as tabelas de preco; pt e PVP ficam iguais', () => {
  const names = [['Lojista', 'Retailer'], ['Arquiteto', 'Architect'], ['Corporativo', 'Corporate']]
  for (const [pt, en] of names) {
    assert.equal(translateCadastro('en-GB', pt), en)
    assert.equal(translateCadastro('pt-PT', pt), pt)
  }
  assert.equal(translateCadastro('en-GB', 'PVP'), 'PVP')
  assert.equal(translateCadastro('en-GB', 'Preço Lojista ({currency}) *', { currency: '€' }), 'Retailer price (€) *')
  assert.equal(translateCadastro('en-GB', 'Preço Corporativo ({currency}) *', { currency: '€' }), 'Corporate price (€) *')
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

test('Portugal (pt) troca "cadastro" por "ficha" com o artigo no feminino; Brasil e inglês não mudam', () => {
  assert.equal(translateCadastro('pt-PT', 'Cadastros', undefined, 'EU'), 'Fichas')
  assert.equal(translateCadastro('pt-PT', 'Cadastros', undefined, 'BR'), 'Cadastros')
  assert.equal(translateCadastro('en-GB', 'Cadastros', undefined, 'EU'), 'Records')
  assert.equal(fichaPt('Cadastro anterior ao rastreamento'), 'Ficha anterior ao rastreamento')
  assert.equal(fichaPt('cadastro anterior'), 'ficha anterior')
  assert.equal(fichaPt('ele deve coincidir com o cadastro.'), 'ele deve coincidir com a ficha.')
  assert.equal(fichaPt('Dados do cadastro'), 'Dados da ficha')
  assert.equal(fichaPt('Cadastros de apoio'), 'Fichas de apoio')
  // Só o substantivo: o verbo e o particípio ficam como estão.
  assert.equal(fichaPt('Cadastrar grupo'), 'Cadastrar grupo')
  assert.equal(fichaPt('{count} {label} cadastrados'), '{count} {label} cadastrados')
})
