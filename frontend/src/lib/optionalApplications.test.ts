import assert from 'node:assert/strict'
import { test } from 'vitest'

import { allowsCustomFor, allowsCustomOption, CUSTOM_LEGACY_VALUE, formatChoice, nextApplicationChoices, offersSuppliedFabric, orderOptionalSlots, requiredApplicationProgress, suppliedFabricLine, validateApplicationChoices } from './optionalApplications.ts'
import type { OptionalApplication, OptionalColor, OrderItem, Product } from '../types'

const option = (id: string, category: string, brand: 'ILYA' | 'IBTW' = 'ILYA'): OptionalColor => ({ id, category, color_name: id, brand }) as OptionalColor
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

test('finalização exige todas as aplicações, independentemente de escolhas legadas', () => {
  const optional = application('Almofada', 'TECIDO', false)
  assert.match(
    validateApplicationChoices(product([optional]), [], [option('taupe', 'TECIDO')], true)[0],
    /Almofada: escolha pendente/,
  )
  assert.match(
    validateApplicationChoices(product([optional]), [], [option('taupe', 'TECIDO')], true, { MADEIRA: 'Canela' })[0],
    /Almofada: escolha pendente/,
  )
  assert.deepEqual(validateApplicationChoices(
    product([optional]),
    [{ application_id: optional.id, optional_id: 'taupe' }],
    [option('taupe', 'TECIDO')],
    true,
  ), [])
  assert.deepEqual(validateApplicationChoices(product([optional]), [], [option('taupe', 'TECIDO')]), [])
})

test('finalização exige cada categoria legada configurada', () => {
  const item = {
    ...product([]),
    optionals: [option('taupe', 'PINTURA')],
    all_optionals_categories: ' TECIDO ',
  } as Product
  assert.match(validateApplicationChoices(item, [], [], true)[0], /PINTURA: escolha pendente/)
  assert.deepEqual(validateApplicationChoices(
    item, [], [], true, { PINTURA: 'Taupe', TECIDO: 'Linho' },
  ), [])
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

test('Customizado sem texto preenche a aplicação obrigatória IBTW', () => {
  const app = { ...application('Pés'), allowed_optionals: [option('taupe', 'PINTURA', 'IBTW')] }
  const available = [option('taupe', 'PINTURA', 'IBTW')]
  const custom = [{ application_id: app.id, custom_text: '' }]
  assert.deepEqual(validateApplicationChoices(product([app]), custom, available), [])
  assert.deepEqual(requiredApplicationProgress(product([app]), custom, available), { filled: 1, total: 1, missing: 0 })
})

test('seletor com algum opcional ILYA não aceita Customizado', () => {
  assert.equal(allowsCustomFor([option('a', 'MADEIRA', 'IBTW')]), true)
  assert.equal(allowsCustomFor([option('a', 'MADEIRA', 'IBTW'), option('b', 'MADEIRA', 'ILYA')]), false)
  assert.equal(allowsCustomFor([option('b', 'MADEIRA', 'ILYA')]), false)
  const app = application('Pés')
  const custom = [{ application_id: app.id, custom_text: '' }]
  assert.match(validateApplicationChoices(product([app]), custom, [option('taupe', 'PINTURA')])[0], /Customizado indisponível/)
  assert.deepEqual(requiredApplicationProgress(product([app]), custom, [option('taupe', 'PINTURA')]), { filled: 0, total: 1, missing: 1 })
})

test('Customizado aparece no pedido, no PDF e no seletor antigo, com o texto dos pedidos anteriores', () => {
  const choice = { application_name: 'Pintura dos pés', application_name_en: 'Leg paint', component_name: null, optional_name: 'Customizado', custom_text: 'Pés em latão' }
  assert.equal(formatChoice(choice as Parameters<typeof formatChoice>[0], false), 'Pintura dos pés: Customizado: Pés em latão')
  assert.equal(formatChoice(choice as Parameters<typeof formatChoice>[0], true), 'Leg paint: Custom: Pés em latão')
  const plain = { ...choice, custom_text: '' }
  assert.equal(formatChoice(plain as Parameters<typeof formatChoice>[0], false), 'Pintura dos pés: Customizado')
  const slots = orderOptionalSlots({ opt_categories: { CORDA: CUSTOM_LEGACY_VALUE, SISAL: 'Customizado: Corda azul', COURO: 'Natural' }, optional_choices: [] }, true, code => code)
  assert.deepEqual(slots.map(slot => slot.value), ['Custom', 'Custom: Corda azul', 'Natural'])
  assert.equal(allowsCustomOption('EU'), true)
  assert.equal(allowsCustomOption('BR'), false)
})

test('Portugal salva o orçamento incompleto, mas ainda rejeita escolha inválida', () => {
  const app = application('Pés')
  const optionals = [option('taupe', 'PINTURA')]
  assert.deepEqual(validateApplicationChoices(product([app]), [], optionals, false, {}, true), [])
  assert.deepEqual(validateApplicationChoices(product([app]), [], optionals, true, {}, true), [])
  assert.match(
    validateApplicationChoices(product([app]), [{ application_id: app.id, optional_id: 'preto' }], optionals, false, {}, true)[0],
    /indisponível/,
  )
  // Sem a flag (Brasil) a exigência continua.
  assert.match(validateApplicationChoices(product([app]), [], optionals, true)[0], /Pés: escolha pendente/)
})

// ── TECIDO FORNECIDO (Portugal) ───────────────────────────────────────────────

const fabricApp = (id: string) => application(id, 'TECIDOS_IBTW', false)
const fabricProduct = (market: 'EU' | 'BR' = 'EU', withData = true): Product => ({
  market_code: market,
  optional_applications: [fabricApp('tecido'), fabricApp('almofadas'), application('Pés')],
  components: [],
  supplied_fabric: withData ? { linear_meters: '13.20', prices: { lojista: '700.10', pvp: 800 } } : null,
}) as unknown as Product

test('a opção só é oferecida em produto EU com dado, na categoria de tecidos IBTW', () => {
  const item = fabricProduct()
  assert.equal(offersSuppliedFabric(item, fabricApp('x')), true)
  assert.equal(offersSuppliedFabric(item, application('Pés')), false)
  assert.equal(offersSuppliedFabric(fabricProduct('EU', false), fabricApp('x')), false)
  assert.equal(offersSuppliedFabric(fabricProduct('BR'), fabricApp('x')), false)
})

test('suppliedFabricLine dá metragem e preço da tabela só quando há escolha de tecido fornecido', () => {
  const item = fabricProduct()
  assert.equal(suppliedFabricLine(item, [], 'lojista'), null)
  assert.equal(suppliedFabricLine(item, [{ application_id: 'tecido', optional_id: 'taupe' } as never], 'lojista'), null)
  const line = suppliedFabricLine(item, [{ application_id: 'tecido', supplied_fabric: true }], 'lojista')
  assert.deepEqual(line, { meters: 13.2, price: 700.1 })
  assert.equal(suppliedFabricLine(item, [{ application_id: 'tecido', supplied_fabric: true }], 'pvp')?.price, 800)
  // Tabela sem preço visível: a prévia cai para o preço normal (price null), o servidor decide.
  assert.equal(suppliedFabricLine(item, [{ application_id: 'tecido', supplied_fabric: true }], 'corporativo')?.price, null)
  // Escolha numa aplicação que não oferece a opção não conta.
  assert.equal(suppliedFabricLine(item, [{ application_id: 'Pés', supplied_fabric: true }], 'lojista'), null)
})

test('tecido fornecido vale para todos os tecidos IBTW do produto e desfaz ao trocar', () => {
  const item = fabricProduct()
  const marked = nextApplicationChoices(item, [{ application_id: 'almofadas', optional_id: 'taupe' }, { application_id: 'Pés', optional_id: 'taupe' }], 'tecido', { application_id: 'tecido', supplied_fabric: true })
  assert.deepEqual(marked.map(choice => [choice.application_id, choice.supplied_fabric ?? false, choice.optional_id ?? null]).sort(), [
    ['Pés', false, 'taupe'], ['almofadas', true, null], ['tecido', true, null],
  ])
  const back = nextApplicationChoices(item, marked, 'tecido', { application_id: 'tecido', optional_id: 'taupe' })
  assert.deepEqual(back.map(choice => choice.application_id).sort(), ['Pés', 'tecido'])
  assert.deepEqual(nextApplicationChoices(item, marked, 'tecido', null).map(choice => choice.application_id), ['Pés'])
})

test('validação: tecido fornecido exige a oferta e não mistura com outro tecido IBTW', () => {
  const item = fabricProduct()
  const optionals = [option('taupe', 'TECIDOS_IBTW')]
  assert.deepEqual(validateApplicationChoices(item, [{ application_id: 'tecido', supplied_fabric: true }, { application_id: 'almofadas', supplied_fabric: true }], optionals, true, {}, true), [])
  assert.match(validateApplicationChoices(item, [{ application_id: 'tecido', supplied_fabric: true }, { application_id: 'almofadas', optional_id: 'taupe' }], optionals, false, {}, true).join(';'), /todos os tecidos IBTW/)
  assert.match(validateApplicationChoices(item, [{ application_id: 'Pés', supplied_fabric: true }], optionals, false, {}, true)[0], /indisponível/)
  assert.match(validateApplicationChoices(fabricProduct('EU', false), [{ application_id: 'tecido', supplied_fabric: true }], optionals, false, {}, true)[0], /indisponível/)
  // Aplicação obrigatória conta como preenchida com tecido fornecido.
  const required = { ...fabricProduct(), optional_applications: [application('tecido', 'TECIDOS_IBTW', true)] } as unknown as Product
  assert.equal(requiredApplicationProgress(required, [{ application_id: 'tecido', supplied_fabric: true }], optionals).missing, 0)
})

test('pedido e PDF mostram TECIDO FORNECIDO e a metragem do item', () => {
  const item = {
    opt_categories: {},
    supplied_fabric_meters: '13.20',
    optional_choices: [{ id: '1', application_id: 'tecido', optional_id: null, application_name: 'Tecido', application_name_en: 'Fabric', category_code: 'TECIDOS_IBTW', category_name: 'Tecidos IBTW', optional_name: 'TECIDO FORNECIDO', supplied_fabric: true, component_name: null, display_order: 0 }],
  } as unknown as Pick<OrderItem, 'opt_categories' | 'optional_choices'>
  assert.deepEqual(orderOptionalSlots(item, false, code => code).map(slot => slot.value), ['TECIDO FORNECIDO', '13,2 m'])
  assert.deepEqual(orderOptionalSlots(item, true, code => code).map(slot => [slot.label, slot.value]), [['Fabric', 'SUPPLIED FABRIC'], ['Fabric required', '13.2 m']])
})
