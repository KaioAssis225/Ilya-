import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey } from '../lib/cart'
import type { Client, Product } from '../types'
import { productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

const client: Client = {
  id: 'client-eu-showroom', name: 'Cliente Portugal', phone: '+351 912 345 678', email: null,
  cpf_cnpj: null, cep: '1000-001', numero: null, address: 'Rua de Teste', city: 'Lisboa',
  state: 'Lisboa', country: 'PT', region: null, tax_id: 'PT123456789', market_code: 'EU',
  price_profile: 'lojista', max_discount: 0, rep_id: null, created_at: '2026-10-27T12:00:00Z',
  updated_at: '2026-10-27T12:00:00Z', last_activity_at: '2026-10-27T12:00:00Z',
}

function stockProduct(): Product {
  return {
    ...productFixture('EU'),
    product_code: 'ICD0106',
    description: 'ALBA - CADEIRA',
    description_pt_pt: 'ALBA - CADEIRA',
    market_prices: { lojista: 100, corporativo: 90, arquiteto: 80, pvp: 120 },
    optional_applications: [],
  } as Product
}

function installHandlers() {
  const product = stockProduct()
  server.use(
    http.get('*/products', () => HttpResponse.json([product], {
      headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
    })),
    http.post('*/products/batch', () => HttpResponse.json([product])),
    http.get('*/clients', () => HttpResponse.json([])),
    http.get(`*/clients/${client.id}`, () => HttpResponse.json(client)),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/product-types', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([])),
    http.get('*/markets/EU/vat-rate', () => HttpResponse.json({ vat_rate: '23.00' })),
  )
}

function renderWithStockLine() {
  const user = productTestUser('admin', 'EU')
  localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([{
    line_id: 'stock-line-1', product_code: 'ICD0106', qty: 2, discount: 0,
    opt_categories: {}, optional_choices: [], attachments: [],
    showroom_source_item_id: 'item-1', showroom_box_name: 'Estoque Portugal',
  }]))
  sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, client.id)
  renderProductPage(<OrcamentoPage />, user)
}

async function confirmQuote() {
  const finalize = await screen.findByRole('button', { name: 'Confirmar Orçamento' })
  await waitFor(() => expect(finalize).toBeEnabled())
  fireEvent.click(finalize)
  fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
}

describe('OrcamentoPage - peça vinda do Estoque', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('avisa que o saldo só baixa ao salvar e envia a referência do estoque', async () => {
    installHandlers()
    renderWithStockLine()
    expect((await screen.findAllByText(/Do estoque: Estoque Portugal/)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/O saldo só baixa quando você salvar/).length).toBeGreaterThan(0)

    let body: { items: Array<Record<string, unknown>> } | null = null
    server.use(http.post('*/orders', async ({ request }) => {
      body = await request.json() as { items: Array<Record<string, unknown>> }
      return HttpResponse.json({}, { status: 201 })
    }))
    await confirmQuote()

    await waitFor(() => expect(body).not.toBeNull())
    expect(body!.items[0]).toMatchObject({ product_code: 'ICD0106', qty: 2, showroom_source_item_id: 'item-1' })
  })

  it('mostra a recusa do servidor quando o saldo não cobre ao salvar', async () => {
    installHandlers()
    renderWithStockLine()
    await screen.findAllByText(/Do estoque: Estoque Portugal/)
    server.use(http.post('*/orders', () => HttpResponse.json(
      { detail: "Saldo insuficiente na box 'Estoque Portugal' para ICD0106: o orçamento pede 2 e há 1." },
      { status: 422 },
    )))

    await confirmQuote()

    expect(await screen.findByText(/Saldo insuficiente na box 'Estoque Portugal'.*há 1/)).toBeInTheDocument()
  })
})
