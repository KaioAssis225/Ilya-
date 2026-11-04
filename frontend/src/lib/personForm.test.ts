import assert from 'node:assert/strict'
import { test } from 'vitest'

import { normalizePersonPayload, parseApiError } from './personForm.ts'

test('normaliza país, região e campos opcionais sem inventar dados', () => {
  const normalized = normalizePersonPayload({
    name: '  Cliente PT  ',
    phone: ' 123 ',
    email: ' ',
    cpf_cnpj: '',
    tax_id: ' PT123 ',
    contact_name: '  Maria Silva  ',
    observation: '  Prefere contato por telefone.  ',
    country: ' Portugal ',
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
  assert.equal(normalized.contact_name, 'Maria Silva')
  assert.equal(normalized.observation, 'Prefere contato por telefone.')
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
