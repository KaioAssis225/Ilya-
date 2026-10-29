import assert from 'node:assert/strict'
import { test } from 'vitest'
import type { Client, Order, OrderItem, Representative } from '../types/index.ts'
import {
  snapshotToBuildInput,
  type OrderPdfProductSnapshot,
  type OrderPdfSnapshot,
} from './orderPdfSnapshot.ts'

const NOW = '2026-04-19T12:00:00.000Z'

function makeSnapshot(overrides: Partial<OrderPdfSnapshot> = {}): OrderPdfSnapshot {
  const client: Client = {
    id: 'cli-1',
    name: 'Cliente Snapshot',
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
  }

  const representative: Representative = {
    id: 'rep-1',
    name: 'Representante Snapshot',
    phone: '+55 11 98888-0000',
    email: 'rep@example.com',
    cpf_cnpj: '98.765.432/0001-10',
    cep: '01310-200',
    numero: '200',
    address: 'Rua Augusta',
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
    relationship_ended_at: null,
  }

  const item: OrderItem = {
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
    qty: 1,
    unit_price: 5000,
    discount: 0,
    ipi_rate: 5,
    ipi_value: 250,
    tax_label: 'IPI',
    currency: 'BRL',
    observacao: null,
    created_at: NOW,
    updated_at: NOW,
  }

  const order: Order = {
    id: 'ord-1',
    code: 'PED-0001',
    orc_id: 'ORC-0001',
    market_code: 'BR',
    price_list_code: 'BR_LOJISTA',
    currency: 'BRL',
    locale: 'pt-BR',
    client_id: 'cli-1',
    rep_id: 'rep-1',
    total_value: 5000,
    total_ipi: 250,
    total_with_ipi: 5250,
    is_finalized: true,
    is_cancelled: false,
    finalized_at: NOW,
    cancelled_at: null,
    external_code: null,
    notes: null,
    items: [item],
    history: [],
    created_at: NOW,
    updated_at: NOW,
  }

  const products: OrderPdfProductSnapshot[] = [
    {
      product_code: 'POL-001',
      type: 'Poltronas',
      is_set: false,
      components: [],
      thumbnail_url: 'data:image/jpeg;base64,/9j/4AAQ',
      photo_url: null,
    },
  ]

  return {
    schema_version: 2,
    locale: 'pt-BR',
    order,
    client,
    representative,
    products,
    category_labels: {
      ALU: 'Alumínio',
      COR: 'Corda Náutica',
    },
    ...overrides,
  }
}

test('snapshotToBuildInput usa o mapa em catLabel e cai no próprio código quando ausente', () => {
  const snapshot = makeSnapshot()
  const input = snapshotToBuildInput(snapshot)

  assert.ok(input.catLabel)
  assert.equal(input.catLabel('ALU'), 'Alumínio')
  assert.equal(input.catLabel('COR'), 'Corda Náutica')
  assert.equal(input.catLabel('TEC'), 'TEC')
})

test('snapshotToBuildInput define documentLocale para pt-BR, pt-PT e en-GB', () => {
  const brInput = snapshotToBuildInput(makeSnapshot({ locale: 'pt-BR' }))
  const ptInput = snapshotToBuildInput(makeSnapshot({ locale: 'pt-PT' }))
  const enInput = snapshotToBuildInput(makeSnapshot({ locale: 'en-GB' }))

  assert.equal(brInput.documentLocale, undefined)
  assert.equal(ptInput.documentLocale, 'pt-PT')
  assert.equal(enInput.documentLocale, 'en-GB')
})

test('snapshotToBuildInput preserva produtos, pedido, cliente e representante', () => {
  const snapshot = makeSnapshot()
  const input = snapshotToBuildInput(snapshot)

  assert.equal(input.order, snapshot.order)
  assert.equal(input.client, snapshot.client)
  assert.equal(input.rep, snapshot.representative)
  assert.equal(input.products.length, 1)
  assert.equal(input.products[0].product_code, 'POL-001')
  assert.equal(input.products[0].thumbnail_url, 'data:image/jpeg;base64,/9j/4AAQ')
})
