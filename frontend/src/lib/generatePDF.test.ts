import assert from 'node:assert/strict'
import { beforeEach, test, vi } from 'vitest'
import type { Client, Order, OrderItem, Product } from '../types/index.ts'
import { generateOrderPDF } from './generatePDF.ts'

const renderedTexts: string[] = []
const savedFiles: string[] = []

vi.mock('jspdf', () => {
  class MockJsPDF {
    internal = {
      pageSize: {
        getWidth: () => 210,
      },
    }
    setDrawColor() {}
    setLineWidth() {}
    line() {}
    setFont() {}
    setFontSize() {}
    setTextColor() {}
    setFillColor() {}
    roundedRect() {}
    rect() {}
    addPage() {}
    getNumberOfPages() { return 1 }
    setPage() {}
    addImage() {}
    splitTextToSize(text: string) {
      return [String(text)]
    }
    text(content: string | string[]) {
      if (Array.isArray(content)) {
        renderedTexts.push(...content)
      } else {
        renderedTexts.push(content)
      }
    }
    save(filename: string) {
      savedFiles.push(filename)
    }
  }
  return { default: MockJsPDF }
})

const NOW = '2026-04-19T12:00:00.000Z'

function makeClient(overrides: Partial<Client> = {}): Client {
  return {
    id: 'cli-1',
    name: 'Cliente Teste',
    phone: '+55 11 99999-0000',
    email: 'cliente@example.com',
    cpf_cnpj: '12.345.678/0001-90',
    cep: '01310-100',
    numero: '1000',
    address: 'Av. Paulista',
    city: 'São Paulo',
    state: 'SP',
    country: 'BR',
    region: null,
    tax_id: null,
    market_code: 'BR',
    price_profile: 'lojista',
    max_discount: 10,
    rep_id: null,
    created_at: NOW,
    updated_at: NOW,
    last_activity_at: NOW,
    ...overrides,
  }
}

function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 'prod-1',
    product_code: 'POL-001',
    description: 'Poltrona Ilya',
    description_pt_pt: 'Poltrona Ilya PT',
    description_en: 'Ilya Armchair',
    type: 'Poltronas',
    catalog_id: null,
    catalog: null,
    is_circular: false,
    is_set: false,
    altura: 80,
    largura: 75,
    profundidade: 82,
    price: 5000,
    price_lojista: 5000,
    price_corporativo: 4500,
    market_code: 'BR',
    currency: 'BRL',
    observacao: null,
    all_optionals_categories: null,
    optionals: [],
    set_items: [],
    components: [],
    photo_url: null,
    thumbnail_url: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  }
}

function makeOrderItem(overrides: Partial<OrderItem> = {}): OrderItem {
  return {
    id: 'item-1',
    order_id: 'ord-1',
    product_code: 'POL-001',
    description: 'Poltrona Ilya',
    is_circular: false,
    altura: 80,
    largura: 75,
    profundidade: 82,
    opt_categories: {},
    optional_choices: [],
    qty: 2,
    unit_price: 5000,
    discount: 0,
    ipi_rate: 5,
    ipi_value: 500,
    tax_label: 'IPI',
    currency: 'BRL',
    observacao: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  }
}

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: 'ord-1',
    code: 'PED-0001',
    orc_id: 'ORC-0001',
    market_code: 'BR',
    price_list_code: 'BR_LOJISTA',
    currency: 'BRL',
    locale: 'pt-BR',
    client_id: 'cli-1',
    rep_id: null,
    total_value: 10000,
    total_ipi: 500,
    total_with_ipi: 10500,
    is_finalized: true,
    is_cancelled: false,
    finalized_at: NOW,
    cancelled_at: null,
    external_code: null,
    notes: null,
    items: [makeOrderItem()],
    history: [],
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  }
}

beforeEach(() => {
  renderedTexts.length = 0
  savedFiles.length = 0
})

test('gera PDF BR com marca ILYA, rótulos PEDIDO/IPI e valores em BRL', async () => {
  const client = makeClient()
  const products = [makeProduct()]
  const order = makeOrder()

  await generateOrderPDF(order, client, null, products)

  assert.ok(renderedTexts.includes('ILYA'))
  assert.ok(renderedTexts.includes('PEDIDO'))
  assert.ok(renderedTexts.includes('IPI'))
  assert.ok(renderedTexts.includes('Poltrona Ilya'))
  assert.ok(renderedTexts.some((t) => /R\$/.test(t)))
  assert.deepEqual(savedFiles, ['PED-0001_Cliente_Teste.pdf'])
})

test('gera PDF EU com marca IBTW, rótulos ORDER/VAT e valores em EUR', async () => {
  const client = makeClient({
    name: 'Client Europe',
    country: 'PT',
    city: 'Lisboa',
    state: 'LX',
    region: 'Lisboa',
    cep: '1000-001',
    market_code: 'EU',
    price_profile: 'pvp',
  })
  const products = [
    makeProduct({
      market_code: 'EU',
      currency: 'EUR',
      description: 'Poltrona Ilya',
      description_en: 'Ilya Armchair',
    }),
  ]
  const order = makeOrder({
    code: 'ORD-0002',
    orc_id: 'QUO-0002',
    market_code: 'EU',
    price_list_code: 'EU_PVP',
    currency: 'EUR',
    locale: 'en-GB',
    total_value: 2000,
    total_ipi: 460,
    total_with_ipi: 2460,
    items: [
      makeOrderItem({
        description: 'Ilya Armchair',
        qty: 1,
        unit_price: 2000,
        ipi_rate: 23,
        ipi_value: 460,
        tax_label: 'IVA',
        currency: 'EUR',
      }),
    ],
  })

  await generateOrderPDF(order, client, null, products)

  assert.ok(renderedTexts.includes('IBTW'))
  assert.ok(renderedTexts.includes('LIVING LTD'))
  assert.ok(!renderedTexts.includes('IBTW LIVING LTD.'))
  assert.ok(renderedTexts.includes('ORDER CONFIRMATION'))
  assert.ok(renderedTexts.includes('ORDER'))
  assert.ok(renderedTexts.includes('VAT'))
  assert.ok(renderedTexts.includes('COMPANY'))
  assert.ok(!renderedTexts.includes('SELLER / LEGAL ENTITY'))
  assert.ok(renderedTexts.includes('IBTW LIVING LDA'))
  assert.ok(renderedTexts.includes('NIF: 519635698'))
  assert.ok(renderedTexts.includes('Rua do Multipark I, n.º 43, fração D'))
  assert.ok(renderedTexts.includes('4595-542 Seroa, Paços de Ferreira, Portugal'))
  assert.ok(renderedTexts.includes('VAT / TAX ID: not provided'))
  assert.ok(renderedTexts.includes('Commercial order confirmation. This document is not an invoice.'))
  assert.ok(renderedTexts.includes('Ilya Armchair'))
  assert.ok(renderedTexts.some((t) => /€/.test(t)))
  assert.deepEqual(savedFiles, ['ORD-0002_Client_Europe.pdf'])
})

test('seleção pt-PT gera PDF europeu em português e medidas em milímetros', async () => {
  const client = makeClient({
    name: 'Cliente Portugal', country: 'PT', city: 'Porto', state: 'Porto',
    region: 'Norte', cep: '4000-001', market_code: 'EU', price_profile: 'pvp',
    tax_id: 'PT509876543',
  })
  const products = [makeProduct({
    market_code: 'EU', currency: 'EUR', description: 'Cadeira',
    altura: 0.8, largura: 0.75, profundidade: 0.82,
  })]
  const order = makeOrder({
    code: 'ORD-PT-0001', market_code: 'EU', price_list_code: 'EU_PVP',
    currency: 'EUR', locale: 'en-GB',
    items: [makeOrderItem({
      description: 'Cadeira', altura: 0.8, largura: 0.75, profundidade: 0.82,
      qty: 1, unit_price: 1000, ipi_rate: 23, ipi_value: 230,
      tax_label: 'IVA', currency: 'EUR',
    })],
  })

  await generateOrderPDF(order, client, null, products, (code) => code, 'pt-PT')

  assert.ok(renderedTexts.includes('CONFIRMAÇÃO DE PEDIDO'))
  assert.ok(renderedTexts.includes('IBTW'))
  assert.ok(renderedTexts.includes('LIVING LDA'))
  assert.ok(!renderedTexts.includes('IBTW LIVING LDA.'))
  assert.ok(renderedTexts.includes('PEDIDO'))
  assert.ok(renderedTexts.includes('IVA'))
  assert.ok(renderedTexts.includes('EMPRESA'))
  assert.ok(renderedTexts.includes('Dimensões: L 750 mm × P 820 mm × A 800 mm'))
  assert.ok(!renderedTexts.some((text) => text.includes('″')))
})

test('regressão EU: preserva item.description histórico do snapshot mesmo se product.description_en mudou', async () => {
  const client = makeClient({
    name: 'Client Snapshot',
    country: 'PT',
    city: 'Porto',
    state: 'PRT',
    region: 'Porto',
    cep: '4000-001',
    market_code: 'EU',
    price_profile: 'arquiteto',
  })
  const products = [
    makeProduct({
      product_code: 'POL-001',
      market_code: 'EU',
      currency: 'EUR',
      description: 'Poltrona Renomeada no Catálogo',
      description_en: 'Renamed Catalog Armchair 2026',
    }),
  ]
  const order = makeOrder({
    code: 'ORD-0003',
    orc_id: 'QUO-0003',
    market_code: 'EU',
    price_list_code: 'EU_ARQUITETO',
    currency: 'EUR',
    locale: 'en-GB',
    total_value: 1800,
    total_ipi: 414,
    total_with_ipi: 2214,
    items: [
      makeOrderItem({
        product_code: 'POL-001',
        description: 'Historical Snapshot Armchair 2024',
        qty: 1,
        unit_price: 1800,
        ipi_rate: 23,
        ipi_value: 414,
        tax_label: 'IVA',
        currency: 'EUR',
      }),
    ],
  })

  await generateOrderPDF(order, client, null, products)

  assert.ok(
    renderedTexts.includes('Historical Snapshot Armchair 2024'),
    'deve imprimir o título gravado no snapshot do item do pedido',
  )
  assert.ok(
    !renderedTexts.includes('Renamed Catalog Armchair 2026'),
    'não deve sobrescrever o snapshot com o description_en atual do catálogo',
  )
})

test('separa peças de área: tapete não entra no total de itens e soma os m²', async () => {
  const order = makeOrder({
    items: [
      makeOrderItem({ qty: 2 }),
      makeOrderItem({
        id: 'item-tapete',
        product_code: 'TAP-001',
        description: 'Tapete Amazonas',
        sold_by_area: true,
        qty: 4.5,
        altura: 9,
        largura: 9,
        profundidade: 9,
      }),
    ],
  })

  await generateOrderPDF(order, makeClient(), null, [
    makeProduct(),
    makeProduct({
      id: 'prod-tapete',
      product_code: 'TAP-001',
      description: 'Tapete Amazonas',
      catalog: { id: 'tapetes', name: 'Tapete' },
    }),
  ])

  assert.ok(renderedTexts.includes('4,5 m²'))
  const totalItemsIndex = renderedTexts.indexOf('Total de Itens:')
  assert.equal(renderedTexts[totalItemsIndex + 1], '2')
  const totalAreaIndex = renderedTexts.indexOf('Área total:')
  assert.equal(renderedTexts[totalAreaIndex + 1], '4,5 m²')
  assert.ok(!renderedTexts.some((text) => text.startsWith('DIMENSÕES:') || text.startsWith('DIMENSIONS:')))
})
