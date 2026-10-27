import assert from 'node:assert/strict'
import { test } from 'vitest'

import { allowsCustomOption, formatChoice, legacyCustomText, legacyCustomValue, orderOptionalSlots, requiredApplicationProgress, validateApplicationChoices } from './optionalApplications.ts'
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

test('progresso considera somente aplicações obrigatórias preenchidas', () => {
  const first = application('Pés')
  const second = application('Encosto')
  const optional = application('Almofada', 'TECIDO', false)
  const item = product([first, second, optional])
  const available = [option('taupe', 'PINTURA'), option('taupe', 'TECIDO')]
  assert.deepEqual(requiredApplicationProgress(item, [], available), { filled: 0, total: 2, missing: 2 })
  assert.deepEqual(requiredApplicationProgress(item, [
    { application_id: first.id, optional_id: 'taupe' },
    { application_id: optional.id, optional_id: 'taupe' },
  ], available), { filled: 1, total: 2, missing: 1 })
  assert.deepEqual(requiredApplicationProgress(item, [
    { application_id: first.id, optional_id: 'removed-option' },
  ], available), { filled: 0, total: 2, missing: 2 })
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
    { label: 'ROPE', value: 'Natural' },
    { label: 'Leg paint', value: 'Taupe' },
    { label: 'Poltrona — Seat leather', value: 'Caramel' },
  ])
  assert.equal(orderOptionalSlots(item, false, category => category)[2].value, 'Caramelo')
  assert.equal(item.optional_choices?.[1].optional_name, 'Caramelo')
})

test('Customizado preenche a aplicação obrigatória só com texto descrito', () => {
  const app = application('Pés')
  const available = [option('taupe', 'PINTURA')]
  const empty = [{ application_id: app.id, custom_text: '  ' }]
  assert.match(validateApplicationChoices(product([app]), empty, available)[0], /descreva a customização/)
  assert.deepEqual(requiredApplicationProgress(product([app]), empty, available), { filled: 0, total: 1, missing: 1 })
  const filled = [{ application_id: app.id, custom_text: 'Pés em latão' }]
  assert.deepEqual(validateApplicationChoices(product([app]), filled, available), [])
  assert.deepEqual(requiredApplicationProgress(product([app]), filled, available), { filled: 1, total: 1, missing: 0 })
})

test('Customizado aparece com o texto no pedido, no PDF e no seletor antigo', () => {
  const choice = { application_name: 'Pintura dos pés', application_name_en: 'Leg paint', component_name: null, optional_name: 'Customizado', custom_text: 'Pés em latão' }
  assert.equal(formatChoice(choice as Parameters<typeof formatChoice>[0], false), 'Pintura dos pés: Customizado: Pés em latão')
  assert.equal(formatChoice(choice as Parameters<typeof formatChoice>[0], true), 'Leg paint: Custom: Pés em latão')
  const slots = orderOptionalSlots({ opt_categories: { CORDA: legacyCustomValue('Corda azul') }, optional_choices: [] }, true, code => code)
  assert.deepEqual(slots.map(slot => slot.value), ['Custom: Corda azul'])
  assert.equal(legacyCustomText('Customizado: '), '')
  assert.equal(legacyCustomText('Natural'), null)
  assert.equal(allowsCustomOption('EU'), true)
  assert.equal(allowsCustomOption('BR'), false)
})
