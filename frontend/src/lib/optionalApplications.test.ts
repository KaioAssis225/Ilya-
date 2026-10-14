import assert from 'node:assert/strict'
import test from 'node:test'

import { formatChoice, orderOptionalSlots, validateApplicationChoices } from './optionalApplications.ts'
import type { OptionalApplication, OptionalColor, OrderItem, Product } from '../types'

const option = (id: string, category: string): OptionalColor => ({ id, category, color_name: id }) as OptionalColor
const application = (id: string, category = 'PINTURA', required = true, allowRepeat = true): OptionalApplication => ({
  id, category_id: category, category_code: category, category_name: category,
  name: id, name_en: `${id} EN`, required, allow_repeat: allowRepeat,
  allow_all: false, allowed_optionals: [option('taupe', category)], display_order: 0,
})
const product = (applications: OptionalApplication[]): Product => ({
  optional_applications: applications, components: [],
}) as unknown as Product

test('sem aplicações não exige escolha; uma aplicação obrigatória exige', () => {
  assert.deepEqual(validateApplicationChoices(product([]), [], []), [])
  const app = application('Pés')
  assert.match(validateApplicationChoices(product([app]), [], [option('taupe', 'PINTURA')])[0], /Pés/)
  assert.deepEqual(validateApplicationChoices(product([app]), [{ application_id: app.id, optional_id: 'taupe' }], [option('taupe', 'PINTURA')]), [])
})

test('duas aplicações da mesma categoria preservam escolhas independentes e repetição configurada', () => {
  const first = application('Pés')
  const second = application('Encosto')
  const choices = [first, second].map(app => ({ application_id: app.id, optional_id: 'taupe' }))
  assert.deepEqual(validateApplicationChoices(product([first, second]), choices, [option('taupe', 'PINTURA')]), [])
  second.allow_repeat = false
  assert.match(validateApplicationChoices(product([first, second]), choices, [option('taupe', 'PINTURA')])[0], /repetida/)
})

test('categoria diferente, aplicação opcional e opção não autorizada', () => {
  const paint = application('Pés')
  const leather = application('Assento', 'COURO', false)
  assert.deepEqual(validateApplicationChoices(product([paint, leather]), [{ application_id: paint.id, optional_id: 'taupe' }], [option('taupe', 'PINTURA')]), [])
  assert.match(validateApplicationChoices(product([paint]), [{ application_id: paint.id, optional_id: 'preto' }], [option('preto', 'PINTURA')])[0], /indisponível/)
})

test('snapshot usa nome em inglês quando disponível e inclui o componente', () => {
  const choice = { application_name: 'Pintura dos pés', application_name_en: 'Leg paint', component_name: 'Cadeira', optional_name: 'Taupe' }
  assert.equal(formatChoice(choice as Parameters<typeof formatChoice>[0], true), 'Cadeira — Leg paint: Taupe')
  assert.equal(formatChoice(choice as Parameters<typeof formatChoice>[0], false), 'Cadeira — Pintura dos pés: Taupe')
})

test('PDF mantém opcionais legados e aplicações independentes na ordem da linha', () => {
  const item = {
    opt_categories: { CORDA: 'Natural' },
    optional_choices: [
      { application_name: 'Pintura dos pés', application_name_en: 'Leg paint', component_name: null, optional_name: 'Taupe' },
      { application_name: 'Couro do assento', application_name_en: 'Seat leather', component_name: 'Poltrona', optional_name: 'Caramelo' },
    ],
  } as unknown as OrderItem
  assert.deepEqual(orderOptionalSlots(item, true, category => category), [
    { label: 'CORDA', value: 'Natural' },
    { label: 'Leg paint', value: 'Taupe' },
    { label: 'Poltrona — Seat leather', value: 'Caramelo' },
  ])
})
