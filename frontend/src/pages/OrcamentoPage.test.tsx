import { describe, expect, it, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey, writeCartPriceList } from '../lib/cart'
import type { Client, Product, OptionalColor, OptionalApplication, Representative } from '../types'
import {
  renderProductPage,
  productFixture,
  productTestUser,
} from '../test/productTestUtils'
import { server } from '../test/setup'

const CATEGORY_CODE = 'acabamento'
const CATEGORY_ID = 'cat-acabamento'

const OPTIONALS: OptionalColor[] = [
  { id: 'opt-branco', category: CATEGORY_CODE, color_name: 'Branco', photo_url: null },
  { id: 'opt-preto', category: CATEGORY_CODE, color_name: 'Preto', photo_url: null },
]

const OPTIONAL_PHOTO_URL = 'https://example.com/opcionais/canela.jpg'
const OPTIONAL_THUMBNAIL_URL = 'https://example.com/opcionais/canela-thumb.jpg'
const PHOTO_OPTIONALS: OptionalColor[] = [
  { id: 'opt-sem-foto', category: CATEGORY_CODE, color_name: 'Sem foto', photo_url: null },
  {
    id: 'opt-canela',
    category: CATEGORY_CODE,
    color_name: 'Canela',
    photo_url: OPTIONAL_PHOTO_URL,
    thumbnail_url: OPTIONAL_THUMBNAIL_URL,
  },
]

function buildApplications(): OptionalApplication[] {
  return [
    {
      id: 'app-topo',
      category_id: CATEGORY_ID,
      category_code: CATEGORY_CODE,
      category_name: 'Acabamento',
      name: 'Tampo',
      name_en: 'Top',
      required: false,
      display_order: 0,
      allow_all: false,
      allow_repeat: false,
      allowed_optionals: OPTIONALS,
    },
    {
      id: 'app-base',
      category_id: CATEGORY_ID,
      category_code: CATEGORY_CODE,
      category_name: 'Acabamento',
      name: 'Base',
      name_en: 'Base',
      required: false,
      display_order: 1,
      allow_all: false,
      allow_repeat: false,
      allowed_optionals: OPTIONALS,
    },
  ]
}

function buildProduct(market: 'BR' | 'EU', overrides: Partial<Product> = {}): Product {
  return {
    ...productFixture(market),
    product_code: market === 'BR' ? 'SKU-BR' : 'SKU-EU',
    optional_applications: buildApplications(),
    ...overrides,
  } as Product
}

function buildPhotoProduct(): Product {
  return buildProduct('BR', {
    optionals: PHOTO_OPTIONALS,
    optional_applications: buildApplications().map(application => ({
      ...application,
      allowed_optionals: PHOTO_OPTIONALS,
    })),
  })
}

function buildClient(id: string, repId: string | null = null): Client {
  return {
    id,
    name: 'Cliente Portugal',
    phone: '+351 912 345 678',
    email: null,
    cpf_cnpj: null,
    cep: '1000-001',
    numero: null,
    address: 'Rua de Teste',
    city: 'Lisboa',
    state: 'Lisboa',
    country: 'PT',
    region: null,
    tax_id: 'PT123456789',
    market_code: 'EU',
    price_profile: 'lojista',
    max_discount: 0,
    rep_id: repId,
    created_at: '2026-10-27T12:00:00Z',
    updated_at: '2026-10-27T12:00:00Z',
    last_activity_at: '2026-10-27T12:00:00Z',
  }
}

function buildRepresentative(id: string, name: string): Representative {
  return {
    ...buildClient(`client-${id}`),
    id,
    name,
    relationship_ended_at: null,
  }
}

function installOrcamentoHandlers(products: Product[]) {
  server.use(
    http.get('*/products', () => {
      return HttpResponse.json(products, {
        headers: {
          'X-Total-Count': String(products.length),
          'X-Has-More': 'false',
          'X-Page-Size': String(products.length),
        },
      })
    }),
    http.post('*/products/batch', async ({ request }) => {
      const payload = (await request.json()) as unknown
      let codes: string[] = []
      if (Array.isArray(payload)) codes = payload.map(String)
      else if (payload && typeof payload === 'object') {
        const obj = payload as Record<string, unknown>
        const maybe = obj.product_codes ?? obj.codes ?? obj.items
        if (Array.isArray(maybe)) codes = maybe.map(String)
      }
      const byCode = new Map(products.map((p) => [p.product_code, p]))
      const result = codes.map((code) => byCode.get(code)).filter(Boolean)
      return HttpResponse.json(result)
    }),
    http.get('*/clients', () => HttpResponse.json([])),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.get('*/optional-categories', () =>
      HttpResponse.json([{ id: CATEGORY_ID, code: CATEGORY_CODE, name: 'Acabamento' }]),
    ),
    http.get('*/product-types', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([])),
  )
}

async function pickProduct(sku: string) {
  const inputs = await screen.findAllByLabelText(
    /Buscar produto para adicionar ao orçamento/i,
  )
  const input = inputs[0] as HTMLInputElement
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: sku } })
  await screen.findAllByText(sku, {}, { timeout: 3000 })
  const li = await waitFor(() => {
    const found = screen
      .getAllByText(sku)
      .map((el) => el.closest('li'))
      .find(Boolean)
    expect(found).toBeTruthy()
    return found
  })
  fireEvent.mouseDown(li as HTMLElement)
}

function selectChoice(label: string, optionName: string) {
  fireEvent.click(screen.getAllByRole('combobox', { name: label })[0])
  fireEvent.click(screen.getByRole('option', { name: optionName }))
}

function clickAdd() {
  const buttons = screen.getAllByRole('button', { name: /ADICIONAR AO ORÇAMENTO/i })
  fireEvent.click(buttons[0])
}

function expectItemSubtotal(item: HTMLElement, formattedValue: string) {
  const subtotalLabel = within(item).getByText('Subtotal')
  expect(subtotalLabel.parentElement?.textContent).toContain(formattedValue)
}

describe('OrcamentoPage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('não funde linhas quando o mesmo SKU é adicionado duas vezes com escolhas diferentes', async () => {
    const user = productTestUser('admin', 'BR')
    const product = buildProduct('BR')
    installOrcamentoHandlers([product])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    await waitFor(() => {
      expect(screen.getAllByLabelText('Acabamento: Tampo').length).toBeGreaterThan(0)
    })
    selectChoice('Acabamento: Tampo', 'Branco')
    selectChoice('Acabamento: Base', 'Preto')
    clickAdd()

    await waitFor(() => {
      const raw = localStorage.getItem(cartStorageKey(user.id, 'BR'))
      expect(raw).not.toBeNull()
      const parsed = JSON.parse(raw as string) as Array<{
        product_code: string
        qty: number
        optional_choices: Array<{ application_id: string; optional_id: string }>
      }>
      expect(parsed).toHaveLength(1)
      expect(parsed[0].product_code).toBe('SKU-BR')
      expect(parsed[0].qty).toBe(1)
      const choiceMap = Object.fromEntries(
        parsed[0].optional_choices.map((c) => [c.application_id, c.optional_id]),
      )
      expect(choiceMap['app-topo']).toBe('opt-branco')
      expect(choiceMap['app-base']).toBe('opt-preto')
    })

    await pickProduct('SKU-BR')
    await waitFor(() => {
      expect(screen.getAllByLabelText('Acabamento: Tampo').length).toBeGreaterThan(0)
    })
    selectChoice('Acabamento: Tampo', 'Preto')
    selectChoice('Acabamento: Base', 'Branco')
    clickAdd()

    await waitFor(() => {
      const raw = localStorage.getItem(cartStorageKey(user.id, 'BR'))
      expect(raw).not.toBeNull()
      const parsed = JSON.parse(raw as string) as Array<{
        product_code: string
        qty: number
        optional_choices: Array<{ application_id: string; optional_id: string }>
      }>
      expect(parsed).toHaveLength(2)
      expect(parsed.every((item) => item.product_code === 'SKU-BR')).toBe(true)
      expect(parsed.every((item) => item.qty === 1)).toBe(true)

      const firstChoice = Object.fromEntries(
        parsed[0].optional_choices.map((c) => [c.application_id, c.optional_id]),
      )
      expect(firstChoice['app-topo']).toBe('opt-branco')
      expect(firstChoice['app-base']).toBe('opt-preto')

      const secondChoice = Object.fromEntries(
        parsed[1].optional_choices.map((c) => [c.application_id, c.optional_id]),
      )
      expect(secondChoice['app-topo']).toBe('opt-preto')
      expect(secondChoice['app-base']).toBe('opt-branco')
    })
  })

  it('carrinho persistido de usuário BR não aparece no mercado EU', async () => {
    const brUser = productTestUser('admin', 'BR')
    const euUser = {
      ...brUser,
      active_market: 'EU' as const,
      allowed_markets: ['BR', 'EU'] as Array<'BR' | 'EU'>,
    }
    const brProduct = buildProduct('BR')
    const euProduct = buildProduct('EU')

    localStorage.setItem(
      cartStorageKey(brUser.id, 'BR'),
      JSON.stringify([
        {
          line_id: 'line-br-1',
          product_code: brProduct.product_code,
          qty: 2,
          discount: 0,
          opt_categories: {},
          optional_choices: [],
        },
      ]),
    )

    installOrcamentoHandlers([euProduct, brProduct])

    renderProductPage(<OrcamentoPage />, euUser)

    await waitFor(() => {
      const inputs = screen.getAllByLabelText(
        /Buscar produto para adicionar ao orçamento/i,
      ) as HTMLInputElement[]
      expect(inputs[0].disabled).toBe(false)
    })

    await waitFor(() => {
      expect(screen.queryAllByText('SKU-BR')).toHaveLength(0)
      expect(screen.queryAllByText('SKU-EU')).toHaveLength(0)
    })

    const brRaw = localStorage.getItem(cartStorageKey(brUser.id, 'BR'))
    expect(brRaw).not.toBeNull()
    const brParsed = JSON.parse(brRaw as string) as Array<{ product_code: string }>
    expect(brParsed).toHaveLength(1)
    expect(brParsed[0].product_code).toBe('SKU-BR')

    const euRaw = localStorage.getItem(cartStorageKey(euUser.id, 'EU'))
    if (euRaw) {
      const euParsed = JSON.parse(euRaw) as Array<{ product_code: string }>
      expect(
        euParsed.some(
          (item) =>
            item.product_code === 'SKU-BR' ||
            item.product_code === 'SKU-EU',
        ),
      ).toBe(false)
    }
  })

  it('REG-PROD-03: orçamento EU restaura a tabela escolhida no catálogo e usa seu preço', async () => {
    const user = productTestUser('admin', 'EU')
    const product = buildProduct('EU', { optional_applications: [] })
    localStorage.setItem(
      cartStorageKey(user.id, 'EU'),
      JSON.stringify([{
        line_id: 'line-eu-arquiteto',
        product_code: product.product_code,
        qty: 1,
        discount: 0,
        opt_categories: {},
        optional_choices: [],
      }]),
    )
    writeCartPriceList(user.id, 'EU', 'arquiteto')
    installOrcamentoHandlers([product])

    renderProductPage(<OrcamentoPage />, user)

    const selector = await screen.findByRole('combobox', { name: 'Tabela de preço do orçamento' })
    expect(selector).toHaveValue('arquiteto')
    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    const expectedSubtotal = new Intl.NumberFormat('pt-PT', {
      style: 'currency',
      currency: 'EUR',
    }).format(80)
    expectItemSubtotal(item, expectedSubtotal)
  })

  it('REG-PROD-03: envia a tabela EU escolhida no contrato de criação do pedido', async () => {
    const user = productTestUser('admin', 'EU')
    const product = buildProduct('EU', { optional_applications: [] })
    const quoteClient: Client = {
      id: 'client-eu-price-list',
      name: 'Cliente Portugal',
      phone: '+351 912 345 678',
      email: null,
      cpf_cnpj: null,
      cep: '1000-001',
      numero: null,
      address: 'Rua de Teste',
      city: 'Lisboa',
      state: 'Lisboa',
      country: 'PT',
      region: null,
      tax_id: 'PT123456789',
      market_code: 'EU',
      price_profile: 'lojista',
      max_discount: 0,
      rep_id: null,
      created_at: '2026-10-27T12:00:00Z',
      updated_at: '2026-10-27T12:00:00Z',
      last_activity_at: '2026-10-27T12:00:00Z',
    }
    localStorage.setItem(
      cartStorageKey(user.id, 'EU'),
      JSON.stringify([{
        line_id: 'line-eu-contract',
        product_code: product.product_code,
        qty: 1,
        discount: 0,
        opt_categories: {},
        optional_choices: [],
      }]),
    )
    writeCartPriceList(user.id, 'EU', 'corporativo')
    sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, quoteClient.id)
    installOrcamentoHandlers([product])
    let posted: Record<string, unknown> | null = null
    server.use(
      http.get(`*/clients/${quoteClient.id}`, () => HttpResponse.json(quoteClient)),
      http.post('*/orders', async ({ request }) => {
        posted = await request.json() as Record<string, unknown>
        return HttpResponse.json({}, { status: 201 })
      }),
    )

    renderProductPage(<OrcamentoPage />, user)

    const submit = await screen.findByRole('button', { name: 'Finalizar Orçamento' })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toMatchObject({
      client_id: quoteClient.id,
      price_list_code: 'corporativo',
    })
  })

  it('envia L × P do tapete sem qty e bloqueia tapete sem medidas', async () => {
    const user = productTestUser('admin', 'EU')
    const rug = buildProduct('EU', {
      product_code: 'TAP-EU', description: 'Tapete PT',
      catalog_id: 'tapetes', catalog: { id: 'tapetes', name: 'Tapete' },
      optional_applications: [],
    })
    const quoteClient = {
      id: 'client-eu-rug', name: 'Cliente Tapete', phone: '+351 912 345 678', email: null, cpf_cnpj: null,
      cep: '1000-001', numero: null, address: 'Rua de Teste', city: 'Lisboa', state: 'Lisboa', country: 'PT',
      region: null, tax_id: 'PT123456789', market_code: 'EU', price_profile: 'lojista', max_discount: 0,
      rep_id: null, created_at: '2026-10-28T12:00:00Z', updated_at: '2026-10-28T12:00:00Z',
      last_activity_at: '2026-10-28T12:00:00Z',
    } as Client
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([
      { line_id: 'rug-sized', product_code: 'TAP-EU', qty: 4.2, sold_by_area: true, area_width_m: 2.05, area_depth_m: 2.05, discount: 0, opt_categories: {}, optional_choices: [] },
      { line_id: 'rug-empty', product_code: 'TAP-EU', qty: 1, sold_by_area: true, area_width_m: null, area_depth_m: null, discount: 0, opt_categories: {}, optional_choices: [] },
    ]))
    sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, quoteClient.id)
    installOrcamentoHandlers([rug])
    let posted: { items: Array<Record<string, unknown>> } | null = null
    server.use(
      http.get(`*/clients/${quoteClient.id}`, () => HttpResponse.json(quoteClient)),
      http.post('*/orders', async ({ request }) => {
        posted = await request.json() as { items: Array<Record<string, unknown>> }
        return HttpResponse.json({}, { status: 201 })
      }),
    )

    renderProductPage(<OrcamentoPage />, user)

    const submit = await screen.findByRole('button', { name: 'Finalizar Orçamento' })
    // A segunda linha ainda não tem L × P: o servidor recusaria, então o botão trava.
    await waitFor(() => expect(submit).toBeDisabled())
    fireEvent.click(screen.getAllByRole('button', { name: /Remover Tapete PT do orçamento/ })[1])
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
    await waitFor(() => expect(posted).not.toBeNull())
    const [line] = posted!.items
    expect(line).toMatchObject({ product_code: 'TAP-EU', area_width_m: 2.05, area_depth_m: 2.05 })
    expect(line).not.toHaveProperty('qty')
  })

  it('mantém o administrador e fixa seu representante nos pedidos novos', async () => {
    const fixedRep = buildRepresentative('rep-james', 'James IBTW')
    const user = {
      ...productTestUser('admin', 'EU'),
      order_rep_id: fixedRep.id,
    }
    const product = buildProduct('EU', { optional_applications: [] })
    const client = buildClient('client-james')
    localStorage.setItem(
      cartStorageKey(user.id, 'EU'),
      JSON.stringify([{
        line_id: 'line-james',
        product_code: product.product_code,
        qty: 1,
        discount: 0,
        opt_categories: {},
        optional_choices: [],
      }]),
    )
    sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, client.id)
    installOrcamentoHandlers([product])
    let posted: Record<string, unknown> | null = null
    server.use(
      http.get(`*/clients/${client.id}`, () => HttpResponse.json(client)),
      http.get(`*/representatives/${fixedRep.id}`, () => HttpResponse.json(fixedRep)),
      http.post('*/orders', async ({ request }) => {
        posted = await request.json() as Record<string, unknown>
        return HttpResponse.json({}, { status: 201 })
      }),
    )

    renderProductPage(<OrcamentoPage />, user)

    expect((await screen.findAllByText('James IBTW — Lisboa/Lisboa')).length).toBeGreaterThan(0)
    expect(screen.queryAllByPlaceholderText('Buscar representante...')).toHaveLength(0)
    const submit = await screen.findByRole('button', { name: 'Finalizar Orçamento' })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toMatchObject({
      client_id: client.id,
      rep_id: fixedRep.id,
    })
  })

  it('ao editar, preserva o representante do pedido em vez do vínculo fixo do administrador', async () => {
    const fixedRep = buildRepresentative('rep-james', 'James IBTW')
    const orderRep = buildRepresentative('rep-original', 'Representante do pedido')
    const user = {
      ...productTestUser('admin', 'EU'),
      order_rep_id: fixedRep.id,
    }
    const product = buildProduct('EU', { optional_applications: [] })
    const client = buildClient('client-edit', orderRep.id)
    const orderId = 'order-edit-fixed-rep'
    installOrcamentoHandlers([product])
    let updated: Record<string, unknown> | null = null
    server.use(
      http.get(`*/orders/${orderId}`, () => HttpResponse.json({
        id: orderId,
        code: 'PED-EU-0001',
        client_id: client.id,
        rep_id: orderRep.id,
        price_list_code: 'lojista',
        notes: null,
        items: [{
          id: 'item-edit',
          product_code: product.product_code,
          qty: 1,
          sold_by_area: false,
          discount: 0,
          opt_categories: {},
          optional_choices: [],
          comment: null,
        }],
      })),
      http.get(`*/clients/${client.id}`, () => HttpResponse.json(client)),
      http.get(`*/representatives/${orderRep.id}`, () => HttpResponse.json(orderRep)),
      http.put(`*/orders/${orderId}`, async ({ request }) => {
        updated = await request.json() as Record<string, unknown>
        return HttpResponse.json({}, { status: 200 })
      }),
    )

    renderProductPage(<OrcamentoPage />, user, [`/orcamentos?edit=${orderId}`])

    expect((await screen.findAllByText('Representante do pedido — Lisboa/Lisboa')).length).toBeGreaterThan(0)
    expect(screen.getAllByPlaceholderText('Buscar representante...').length).toBeGreaterThan(0)
    const submit = await screen.findByRole('button', { name: 'Salvar Alterações' })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
    await waitFor(() => expect(updated).not.toBeNull())
    expect(updated).toMatchObject({ rep_id: orderRep.id })
  })

  it('mantém subtotal e remoção no mesmo item e remove a linha do orçamento', async () => {
    const user = productTestUser('admin', 'BR')
    const product = buildProduct('BR')
    installOrcamentoHandlers([product])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    clickAdd()

    const item = await screen.findByRole('listitem', { name: 'SKU-BR Mesa BR' })
    const itemQueries = within(item)
    const removeButtons = itemQueries.getAllByRole('button', {
      name: 'Remover Mesa BR do orçamento',
    })
    const expectedSubtotal = new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(100)

    expect(removeButtons).toHaveLength(1)
    expectItemSubtotal(item, expectedSubtotal)

    fireEvent.click(removeButtons[0])

    await waitFor(() => {
      expect(screen.queryByRole('listitem', { name: 'SKU-BR Mesa BR' })).toBeNull()
      expect(screen.queryByText('Mesa BR')).toBeNull()
      expect(screen.getByText('Seu orçamento ainda está vazio.')).toBeTruthy()
    })
  })

  it('orçamento EU oculta o IVA por item e só o mostra no fecho (Subtotal → IVA → Total)', async () => {
    const user = productTestUser('admin', 'EU')
    const product = buildProduct('EU', { optional_applications: [], vat_rate: '23.00' })
    localStorage.setItem(
      cartStorageKey(user.id, 'EU'),
      JSON.stringify([{
        line_id: 'line-eu-vat',
        product_code: product.product_code,
        qty: 1,
        discount: 0,
        opt_categories: {},
        optional_choices: [],
      }]),
    )
    writeCartPriceList(user.id, 'EU', 'arquiteto')
    installOrcamentoHandlers([product])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    expect(within(item).queryByText('23%')).not.toBeInTheDocument()
    const eur = (value: number) => new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(value)
    // A linha mostra o valor sem IVA; o imposto não é embutido item a item.
    expect(item.textContent).toContain(eur(80))
    expect(item.textContent).not.toContain(eur(80 * 1.23))
    const summary = screen.getByText('Total do Orçamento:').parentElement?.textContent
    expect(summary).toContain(`Subtotal: ${eur(80)}`)
    expect(summary).toContain(`IVA: ${eur(80 * 0.23)}`)
    expect(summary).toContain(eur(80 * 1.23))
  })

  it('recalcula o subtotal do item ao alterar a quantidade', async () => {
    const user = productTestUser('admin', 'BR')
    const price = 1234.56
    const product = buildProduct('BR', {
      price,
      price_lojista: price,
      market_prices: { lojista: price, corporativo: price },
    })
    installOrcamentoHandlers([product])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    clickAdd()

    const item = await screen.findByRole('listitem', { name: 'SKU-BR Mesa BR' })
    const quantity = within(item).getByLabelText('Qtd — Mesa BR')
    const expectedSubtotal = new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(price * 3)

    fireEvent.change(quantity, { target: { value: '3' } })

    await waitFor(() => {
      expectItemSubtotal(item, expectedSubtotal)
    })
  })

  it('não renderiza tabela quando há itens no carrinho', async () => {
    const user = productTestUser('admin', 'BR')
    const product = buildProduct('BR')
    installOrcamentoHandlers([product])

    const { container } = renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    clickAdd()

    await screen.findByRole('listitem', { name: 'SKU-BR Mesa BR' })
    expect(container.querySelector('table')).toBeNull()
  })

  it('expõe no title o nome completo do acabamento selecionado', async () => {
    const user = productTestUser('admin', 'BR')
    const longFinish = 'Nogueira Natural Envelhecida de Veios Contínuos'
    const product = buildProduct('BR', {
      optionals: [
        ...OPTIONALS,
        {
          id: 'opt-nogueira-natural',
          category: CATEGORY_CODE,
          color_name: longFinish,
          photo_url: null,
        },
      ],
    })
    installOrcamentoHandlers([product])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    clickAdd()

    const item = await screen.findByRole('listitem', { name: 'SKU-BR Mesa BR' })
    const finishCombobox = within(item).getByRole('combobox', { name: 'Acabamento' })
    fireEvent.click(finishCombobox)
    fireEvent.click(screen.getByRole('option', { name: longFinish }))

    await waitFor(() => {
      expect(finishCombobox.title).toBe(longFinish)
    })
  })

  it('mostra a miniatura do opcional na lista aberta', async () => {
    const user = productTestUser('admin', 'BR')
    installOrcamentoHandlers([buildPhotoProduct()])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    const combobox = screen.getAllByRole('combobox', { name: 'Acabamento: Tampo' })[0]
    fireEvent.click(combobox)

    const option = screen.getByRole('option', { name: 'Canela' })
    expect(option.querySelector('img')?.getAttribute('src')).toBe(OPTIONAL_THUMBNAIL_URL)
  })

  it('seleciona um opcional com foto e abre a imagem ampliada', async () => {
    const user = productTestUser('admin', 'BR')
    installOrcamentoHandlers([buildPhotoProduct()])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    const combobox = screen.getAllByRole('combobox', { name: 'Acabamento: Tampo' })[0]
    fireEvent.click(combobox)
    fireEvent.click(screen.getByRole('option', { name: 'Canela' }))

    expect(combobox.textContent).toContain('Canela')
    const dialog = screen.getByRole('dialog')
    expect(dialog.querySelector(`img[src="${OPTIONAL_PHOTO_URL}"]`)).toBeTruthy()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('seleciona um opcional sem foto sem abrir o lightbox', async () => {
    const user = productTestUser('admin', 'BR')
    installOrcamentoHandlers([buildPhotoProduct()])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    const combobox = screen.getAllByRole('combobox', { name: 'Acabamento: Tampo' })[0]
    fireEvent.click(combobox)
    fireEvent.click(screen.getByRole('option', { name: 'Sem foto' }))

    expect(combobox.textContent).toContain('Sem foto')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('permite escolher pelo teclado e Escape fecha a lista sem mudar o valor', async () => {
    const user = productTestUser('admin', 'BR')
    installOrcamentoHandlers([buildPhotoProduct()])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    const combobox = screen.getAllByRole('combobox', { name: 'Acabamento: Tampo' })[0]
    fireEvent.keyDown(combobox, { key: 'ArrowDown' })
    expect(combobox.getAttribute('aria-expanded')).toBe('true')
    fireEvent.keyDown(combobox, { key: 'ArrowDown' })
    fireEvent.keyDown(combobox, { key: 'Enter' })

    expect(combobox.textContent).toContain('Sem foto')
    expect(combobox.getAttribute('aria-expanded')).toBe('false')

    fireEvent.keyDown(combobox, { key: 'ArrowDown' })
    fireEvent.keyDown(combobox, { key: 'ArrowDown' })
    fireEvent.keyDown(combobox, { key: 'Escape' })

    expect(combobox.getAttribute('aria-expanded')).toBe('false')
    expect(combobox.textContent).toContain('Sem foto')
  })

  it('abre novamente o lightbox pela miniatura do opcional selecionado', async () => {
    const user = productTestUser('admin', 'BR')
    installOrcamentoHandlers([buildPhotoProduct()])

    renderProductPage(<OrcamentoPage />, user)

    await pickProduct('SKU-BR')
    selectChoice('Acabamento: Tampo', 'Canela')
    fireEvent.keyDown(document, { key: 'Escape' })

    const previewButtons = screen.getAllByRole('button', { name: 'Ver foto de Canela' })
    fireEvent.click(previewButtons[0])

    const dialog = screen.getByRole('dialog')
    expect(dialog.querySelector(`img[src="${OPTIONAL_PHOTO_URL}"]`)).toBeTruthy()
  })

  it('tapete pede L × P em metros, mostra a área e avisa acima do limite', async () => {
    const user = productTestUser('admin', 'BR')
    const product = buildProduct('BR', {
      product_code: 'TAP-001',
      description: 'Tapete Amazonas',
      catalog_id: 'tapetes',
      catalog: { id: 'tapetes', name: 'Tapete' },
      area_limit_enabled: true,
      max_area_m2: '12.5',
      altura: 9,
      largura: 9,
      profundidade: 9,
      optional_applications: [],
    })
    installOrcamentoHandlers([product])

    renderProductPage(<OrcamentoPage />, user)
    await pickProduct('TAP-001')
    clickAdd()

    const item = await screen.findByRole('listitem', { name: 'TAP-001 Tapete Amazonas' })
    expect(within(item).queryByText(/L 9/)).not.toBeInTheDocument()
    // Sem medidas a linha pede L × P e o orçamento não pode ser salvo.
    expect(within(item).getByText('Informe L × P')).toBeInTheDocument()
    const widthInput = within(item).getByLabelText('Largura em metros')
    const depthInput = within(item).getByLabelText('Profundidade em metros')
    fireEvent.change(widthInput, { target: { value: '2.05' } })
    fireEvent.change(depthInput, { target: { value: '2.05' } })

    // Prévia arredondada (4,2025 → 4,20 m²); o valor final vem do servidor.
    expect(await within(item).findByText('= 4,2 m²')).toBeInTheDocument()
    const expectedSubtotal = new Intl.NumberFormat('pt-BR', {
      style: 'currency', currency: 'BRL',
    }).format(420)
    expectItemSubtotal(item, expectedSubtotal)
    expect(Array.from(document.querySelectorAll('div')).some((node) => node.textContent === 'Itens: 1')).toBe(true)

    fireEvent.change(widthInput, { target: { value: '5' } })
    fireEvent.change(depthInput, { target: { value: '3' } })
    await waitFor(() => expect(within(item).getAllByText('máx. 12,5 m²').some((node) => node.className.includes('text-warning'))).toBe(true))

    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem(cartStorageKey(user.id, 'BR')) ?? '[]') as Array<{ sold_by_area?: boolean; area_width_m?: number; area_depth_m?: number }>
      expect(saved[0]).toMatchObject({ sold_by_area: true, area_width_m: 5, area_depth_m: 3 })
    })
  })
})
