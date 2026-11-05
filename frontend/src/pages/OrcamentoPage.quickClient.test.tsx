import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey } from '../lib/cart'
import type { Client, Product } from '../types'
import { productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

// Cliente que o servidor devolve ao cadastro rápido de Portugal.
const createdClient: Client = {
  id: 'client-eu-novo', name: 'Cliente Novo Portugal', phone: '+351 912 345 678', email: null,
  cpf_cnpj: null, cep: '1000-001', numero: null, address: 'Rua Nova 1', city: 'Lisboa',
  state: '--', country: 'PT', region: null, tax_id: null, market_code: 'EU',
  price_profile: 'lojista', max_discount: 0, rep_id: null, created_at: '2026-11-05T10:00:00Z',
  updated_at: '2026-11-05T10:00:00Z', last_activity_at: '2026-11-05T10:00:00Z',
}

function product(): Product {
  return {
    ...productFixture('EU'),
    product_code: 'PAI',
    description: 'Mesa Portugal',
    description_pt_pt: 'Mesa Portugal',
    market_prices: { lojista: 100, corporativo: 90, arquiteto: 80, pvp: 120 },
    optional_applications: [],
    catalog: { id: 'catalog-ibtw', name: 'IBTW' },
  } as Product
}

function installHandlers() {
  const orders: Array<{ client_id: string }> = []
  const clientPosts: unknown[] = []
  // A lista só traz o cliente novo depois que o cadastro rápido o grava.
  let created = false
  server.use(
    http.get('*/products', () => HttpResponse.json([product()], {
      headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
    })),
    http.post('*/products/batch', async ({ request }) => {
      const body = await request.json() as { product_codes?: string[] }
      return HttpResponse.json((body.product_codes ?? []).map(code => code === 'PAI' ? product() : null).filter(Boolean))
    }),
    http.get('*/clients', () => HttpResponse.json(created ? [createdClient] : [])),
    http.get(`*/clients/${createdClient.id}`, () => HttpResponse.json(createdClient)),
    http.post('*/clients', async ({ request }) => {
      clientPosts.push(await request.json())
      created = true
      return HttpResponse.json(createdClient, { status: 201 })
    }),
    http.post('*/orders', async ({ request }) => {
      orders.push(await request.json() as { client_id: string })
      return HttpResponse.json({}, { status: 201 })
    }),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/product-types', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([])),
  )
  return { orders, clientPosts }
}

describe('OrcamentoPage — cadastro rápido de cliente (Portugal)', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('seleciona o cliente recém-cadastrado e deixa finalizar o orçamento com ele', async () => {
    const { orders, clientPosts } = installHandlers()
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([{
      line_id: 'line-1', product_code: 'PAI', qty: 1, discount: 0, opt_categories: {}, optional_choices: [],
    }]))
    renderProductPage(<OrcamentoPage />, user)

    // O formulário tem dois "+": o do representante vem antes e o do cliente depois.
    const addButtons = await screen.findAllByRole('button', { name: 'Cadastrar novo' })
    fireEvent.click(addButtons[1])
    const dialog = await screen.findByRole('dialog', { name: 'Novo Cliente' })
    // Portugal não pede número de morada.
    expect(within(dialog).queryByLabelText('Número')).toBeNull()
    fireEvent.change(within(dialog).getByLabelText('Nome *'), { target: { value: createdClient.name } })
    fireEvent.change(within(dialog).getByLabelText('Telefone *'), { target: { value: createdClient.phone } })
    fireEvent.change(within(dialog).getByLabelText('Código postal *'), { target: { value: '1000001' } })
    fireEvent.change(within(dialog).getByLabelText('Endereço *'), { target: { value: createdClient.address } })
    fireEvent.change(within(dialog).getByLabelText('Localidade *'), { target: { value: createdClient.city } })
    fireEvent.change(within(dialog).getByLabelText('País'), { target: { value: 'PT' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Salvar' }))

    await waitFor(() => expect(clientPosts).toHaveLength(1))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Novo Cliente' })).toBeNull())

    // O cliente criado fica escolhido no orçamento (nome visível, sem o aviso de "Selecione").
    await waitFor(() => expect(screen.getAllByText(`${createdClient.name} — Lisboa/--`).length).toBeGreaterThan(0))
    expect(screen.queryByText('Selecione um cliente para continuar.')).toBeNull()
    expect(sessionStorage.getItem(`orcamento_client_id:${user.id}:EU`)).toBe(createdClient.id)

    const finalize = await screen.findByRole('button', { name: 'Confirmar Orçamento' })
    await waitFor(() => expect(finalize).toBeEnabled())
    fireEvent.click(finalize)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(orders).toHaveLength(1))
    expect(orders[0].client_id).toBe(createdClient.id)
  })
})
