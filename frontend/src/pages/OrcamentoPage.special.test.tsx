import { beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey } from '../lib/cart'
import type { Client, Order, Product } from '../types'
import { productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

const client: Client = {
  id: 'client-eu-special', name: 'Cliente Portugal', phone: '+351 912 345 678', email: null,
  cpf_cnpj: null, cep: '1000-001', numero: null, address: 'Rua de Teste', city: 'Lisboa',
  state: 'Lisboa', country: 'PT', region: null, tax_id: 'PT123456789', market_code: 'EU',
  price_profile: 'lojista', max_discount: 0, rep_id: null, created_at: '2026-10-27T12:00:00Z',
  updated_at: '2026-10-27T12:00:00Z', last_activity_at: '2026-10-27T12:00:00Z',
}

function specialProduct(): Product {
  return {
    ...productFixture('EU'),
    product_code: 'PAI',
    description: 'Mesa Portugal',
    description_pt_pt: 'Mesa Portugal',
    market_prices: { lojista: 100, corporativo: 90, arquiteto: 80, pvp: 120 },
    optional_applications: [],
  } as Product
}

function installHandlers(product = specialProduct()) {
  server.use(
    http.get('*/products', () => HttpResponse.json([product], {
      headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
    })),
    http.post('*/products/batch', async ({ request }) => {
      const body = await request.json() as { product_codes?: string[] }
      return HttpResponse.json((body.product_codes ?? []).map(code => code === product.product_code ? product : null).filter(Boolean))
    }),
    http.get('*/clients', () => HttpResponse.json([])),
    http.get(`*/clients/${client.id}`, () => HttpResponse.json(client)),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/product-types', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([])),
  )
}

function seedCart(userId: string, market: 'EU' | 'BR' = 'EU') {
  localStorage.setItem(cartStorageKey(userId, market), JSON.stringify([{
    line_id: 'parent-line', product_code: 'PAI', qty: 1, discount: 0,
    opt_categories: {}, optional_choices: [],
  }]))
}

function renderQuote(role: Parameters<typeof productTestUser>[0] = 'admin', market: 'EU' | 'BR' = 'EU') {
  const user = productTestUser(role, market)
  seedCart(user.id, market)
  if (market === 'EU') sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, client.id)
  renderProductPage(<OrcamentoPage />, user)
  return user
}

async function addSpecial() {
  const [button] = await screen.findAllByRole('button', { name: 'Especial' })
  fireEvent.click(button)
  await screen.findAllByText('PAI-E1')
}

describe('OrcamentoPage — especiais EU', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('cria PAI-E1 e PAI-E2 sem remover o item pai', async () => {
    installHandlers()
    const user = renderQuote()

    await addSpecial()
    expect(screen.getAllByText('PAI')).not.toHaveLength(0)
    expect(screen.getAllByText('PAI-E1')).not.toHaveLength(0)

    fireEvent.click(screen.getAllByRole('button', { name: 'Especial' })[0])
    await waitFor(() => expect(screen.getAllByText('PAI-E2')).not.toHaveLength(0))
    expect(JSON.parse(localStorage.getItem(cartStorageKey(user.id, 'EU')) ?? '[]')).toHaveLength(3)
  })

  it('usa Especial (%) nos dois sentidos e mostra a prévia calculada', async () => {
    installHandlers()
    renderQuote()
    await addSpecial()

    expect(screen.getAllByText('Especial (%)').length).toBeGreaterThan(0)
    const fields = screen.getAllByRole('spinbutton', { name: 'Especial em Mesa Portugal' }) as HTMLInputElement[]
    fireEvent.change(fields[0], { target: { value: '15' } })
    expect(screen.getAllByText(/€\s*115,00|115,00\s*€/).length).toBeGreaterThan(0)

    fireEvent.change(fields[0], { target: { value: '-20' } })
    expect(screen.getAllByText(/€\s*80,00|80,00\s*€/).length).toBeGreaterThan(0)
  })

  it('permite salvar o orçamento com especial sem comentário (só a finalização exige)', async () => {
    installHandlers()
    renderQuote()
    await addSpecial()

    let posted = 0
    server.use(http.post('*/orders', async ({ request }) => {
      posted += 1
      const payload = await request.json() as { items: unknown[] }
      return HttpResponse.json({ items: payload.items }, { status: 201 })
    }))
    const submit = await screen.findByRole('button', { name: 'Finalizar Orçamento' })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
    await waitFor(() => expect(posted).toBe(1))
    expect(screen.queryByText(/Adicione um comentário aos especiais/)).toBeNull()

    // O modo de edição salva o rascunho mesmo sem comentário.
    cleanup()
    const editUser = productTestUser('admin', 'EU')
    sessionStorage.setItem(`orcamento_client_id:${editUser.id}:EU`, client.id)
    server.use(http.get('*/orders/edit-special', () => HttpResponse.json({
      id: 'edit-special', code: 'ORC-1', orc_id: 'ORC-1', client_id: client.id, rep_id: null,
      market_code: 'EU', price_list_code: 'lojista', currency: 'EUR', locale: 'pt-PT',
      total_value: 100, total_ipi: 0, total_with_ipi: 100, is_finalized: false,
      is_cancelled: false, finalized_at: null, cancelled_at: null, external_code: null,
      notes: null, history: [], created_at: '2026-01-01', updated_at: '2026-01-01',
      items: [{ id: 'special-item', order_id: 'edit-special', product_code: 'PAI',
        description: 'Mesa Portugal - ESPECIAL', is_special: true, special_code: 'PAI-E1',
        special_percent: 0, qty: 1, unit_price: 100, discount: 0, is_circular: false,
        altura: 0, largura: 1, profundidade: 1, opt_categories: {}, optional_choices: [],
        ipi_rate: 0, ipi_value: 0, tax_label: 'IVA', currency: 'EUR', observacao: null,
        comment: null, created_at: '2026-01-01', updated_at: '2026-01-01' }],
    } as Order)),
    http.put('*/orders/edit-special', () => HttpResponse.json({})),
  )
    renderProductPage(<OrcamentoPage />, editUser, ['/orcamentos?edit=edit-special'])
    const save = await screen.findByRole('button', { name: 'Salvar Alterações' })
    await waitFor(() => expect(save).toBeEnabled())
    fireEvent.click(save)
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })

  it('envia o pai como product_code e os campos especiais no payload', async () => {
    installHandlers()
    renderQuote()
    await addSpecial()
    const specialField = screen.getAllByRole('spinbutton', { name: 'Especial em Mesa Portugal' })[0]
    fireEvent.change(specialField, { target: { value: '15' } })
    fireEvent.click(screen.getAllByRole('button', { name: /Mesa Portugal - ESPECIAL/ })[0])
    fireEvent.change(screen.getAllByPlaceholderText('Escreva um comentário sobre este item')[0], { target: { value: 'Nota' } })

    let body: { items: Array<Record<string, unknown>> } | null = null
    server.use(http.post('*/orders', async ({ request }) => {
      body = await request.json() as { items: Array<Record<string, unknown>> }
      return HttpResponse.json({}, { status: 201 })
    }))
    const finalize = await screen.findByRole('button', { name: 'Finalizar Orçamento' })
    await waitFor(() => expect(finalize).toBeEnabled())
    fireEvent.click(finalize)
    await waitFor(() => expect(body).not.toBeNull())
    const special = body!.items.find(item => item.is_special)
    expect(special).toMatchObject({ product_code: 'PAI', is_special: true, special_code: 'PAI-E1', special_percent: 15, discount: 0 })
  })

  it.each([
    ['BR', 'admin'], ['EU', 'cliente'],
  ] as const)('%s/%s não mostra o botão Especial', async (market, role) => {
    installHandlers()
    renderQuote(role, market)
    await screen.findAllByText('PAI')
    expect(screen.queryByRole('button', { name: 'Especial' })).toBeNull()
  })
})
