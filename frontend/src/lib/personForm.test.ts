import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizePersonPayload, parseApiError } from './personForm.ts'

test('normaliza país, região e campos opcionais sem inventar dados', () => {
  const normalized = normalizePersonPayload({
    name: '  Cliente PT  ',
    phone: ' 123 ',
    email: ' ',
    cpf_cnpj: '',
    tax_id: ' PT123 ',
    country: ' pt ',
    region: ' Lisboa ',
    cep: ' 1000-001 ',
    numero: ' ',
    address: ' Rua Um ',
    city: ' Lisboa ',
    state: ' lx ',
  })

  assert.equal(normalized.name, 'Cliente PT')
  assert.equal(normalized.email, null)
  assert.equal(normalized.cpf_cnpj, null)
  assert.equal(normalized.tax_id, 'PT123')
  assert.equal(normalized.country, 'PT')
  assert.equal(normalized.region, 'Lisboa')
  assert.equal(normalized.numero, null)
})

test('traduz erro estruturado sem expor o payload inteiro da API', () => {
  assert.equal(
    parseApiError({
      response: { data: { detail: [{ loc: ['body', 'email'], msg: 'invalid' }] } },
    }),
    'E-mail inválido. Informe um e-mail válido (ex: nome@dominio.com).',
  )
})
