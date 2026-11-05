import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey } from '../lib/cart'
import type { Client, Order, Product } from '../types'
import { productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

const client: Client = {
  id: 'client-eu-copy', name: 'Cliente Portugal', phone: '+351 912 345 678', email: null,
  cpf_cnpj: null, cep: '1000-001', numero: null, address: 'Rua de Teste', city: 'Lisboa',
  state: 'Lisboa', country: 'PT', region: null, tax_id: 'PT123456789', market_code: 'EU',
  price_profile: 'lojista', max_discount: 0, rep_id: null, created_at: '2026-10-27T12:00:00Z',
  updated_at: '2026-10-27T12:00:00Z', last_activity_at: '2026-10-27T12:00:00Z',
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

const line = (extra: Record<string, unknown>) => ({
  order_id: 'src-1', product_code: 'PAI', description: 'Mesa Portugal', is_special: false,
  special_code: null, special_percent: null, qty: 1, unit_price: 100, discount: 0, is_circular: false,
  altura: 0, largura: 1, profundidade: 1, opt_categories: {}, optional_choices: [], ipi_rate: 0,
  ipi_value: 0, tax_label: 'IVA', currency: 'EUR', observacao: null, comment: null,
  created_at: '2026-01-01', updated_at: '2026-01-01', ...extra,
})

const sourceOrder = {
  id: 'src-1', code: 'ORC-0007', orc_id: 'ORC-0007', client_id: client.id, rep_id: null,
  market_code: 'EU', price_list_code: 'corporativo', currency: 'EUR', locale: 'pt-PT',
  catalog_name: 'IBTW', total_value: 100, total_ipi: 0, total_with_ipi: 100, is_finalized: true,
  is_cancelled: false, finalized_at: '2026-01-02', cancelled_at: null, external_code: null,
  notes: 'nota do pedido antigo', history: [], created_at: '2026-01-01', updated_at: '2026-01-01',
  items: [
    line({ id: 'item-a', qty: 3, comment: 'comentário A' }),
    line({
      id: 'item-special', description: 'ESPECIAL - Mesa Portugal', is_special: true, special_code: 'PAI-E1',
      special_percent: 15, comment: 'Tampo sob medida',
    }),
  ],
} as unknown as Order

function installHandlers() {
  const posts: Array<Record<string, unknown>> = []
  server.use(
    http.get('*/products', () => HttpResponse.json([product()], {
      headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
    })),
    http.post('*/products/batch', async ({ request }) => {
      const body = await request.json() as { product_codes?: string[] }
      return HttpResponse.json((body.product_codes ?? []).map(code => code === 'PAI' ? product() : null).filter(Boolean))
    }),
    http.get('*/clients', () => HttpResponse.json([])),
    http.get(`*/clients/${client.id}`, () => HttpResponse.json(client)),
    http.get('*/orders/src-1', () => HttpResponse.json(sourceOrder)),
    http.post('*/orders', async ({ request }) => {
      posts.push(await request.json() as Record<string, unknown>)
      return HttpResponse.json({ id: 'novo-1', copy_skipped: [] }, { status: 201 })
    }),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/product-types', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([])),
  )
  return posts
}

function renderCopy(search = '?copy=src-1&items=item-a,item-special') {
  const user = productTestUser('admin', 'EU')
  renderProductPage(<OrcamentoPage />, user, [`/orcamentos${search}`])
  return user
}

describe('OrcamentoPage — copiar como orçamento novo', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('abre como orçamento NOVO (Confirmar Orçamento, sem Salvar Alterações) com os itens escolhidos', async () => {
    installHandlers()
    renderCopy()

    expect(await screen.findByText('ORC-0007')).toBeInTheDocument()
    expect(await screen.findAllByText('PAI-E1')).not.toHaveLength(0)
    expect(screen.getByText(/Novo orçamento copiado de/)).toBeInTheDocument()
    expect(screen.queryByText(/Editando Pedido/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Salvar Alterações' })).toBeNull()
    expect(await screen.findByRole('button', { name: 'Confirmar Orçamento' })).toBeInTheDocument()
    // Observações do pedido antigo não vêm junto.
    expect(screen.queryByDisplayValue('nota do pedido antigo')).toBeNull()
  })

  it('leva só os itens marcados no modal', async () => {
    installHandlers()
    renderCopy('?copy=src-1&items=item-special')

    await screen.findAllByText('PAI-E1')
    expect(screen.queryByDisplayValue('comentário A')).toBeNull()
    expect(screen.queryAllByText('PAI')).toHaveLength(0)
  })

  it('só cria ao Confirmar Orçamento: pop-up do catálogo, Voltar não cria, Confirmar cria com copy_source', async () => {
    const posts = installHandlers()
    renderCopy()
    await screen.findAllByText('PAI-E1')
    const confirm = await screen.findByRole('button', { name: 'Confirmar Orçamento' })
    await waitFor(() => expect(confirm).toBeEnabled())
    // Nada foi criado só por abrir a cópia.
    expect(posts).toHaveLength(0)

    fireEvent.click(confirm)
    const dialog = await screen.findByRole('dialog', { name: 'Confirmar o catálogo' })
    expect(dialog).toHaveTextContent('Este orçamento será feito no catálogo IBTW, tabela Corporativo. Está correto?')
    expect(posts).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Voltar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(posts).toHaveLength(0)

    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar Orçamento' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(posts).toHaveLength(1))

    const body = posts[0] as { copy_source_order_id: string; client_id: string; price_list_code: string; items: Array<Record<string, unknown>> }
    expect(body.copy_source_order_id).toBe('src-1')
    expect(body.client_id).toBe(client.id)
    expect(body.price_list_code).toBe('corporativo')
    // Especial mantém código, percentual e comentário, ligado ao item de origem.
    expect(body.items).toHaveLength(2)
    expect(body.items[0]).toMatchObject({ product_code: 'PAI', qty: 3, source_order_item_id: 'item-a', comment: 'comentário A', is_special: false })
    expect(body.items[1]).toMatchObject({
      product_code: 'PAI', is_special: true, special_code: 'PAI-E1', special_percent: 15,
      comment: 'Tampo sob medida', source_order_item_id: 'item-special',
    })
  })

  it('não mexe no rascunho do carrinho guardado e volta ao orçamento em branco depois de criar', async () => {
    const posts = installHandlers()
    const user = productTestUser('admin', 'EU')
    const draft = JSON.stringify([{
      line_id: 'draft-1', product_code: 'PAI', qty: 9, discount: 0, opt_categories: {}, optional_choices: [],
    }])
    localStorage.setItem(cartStorageKey(user.id, 'EU'), draft)
    renderProductPage(<OrcamentoPage />, user, ['/orcamentos?copy=src-1&items=item-a,item-special'])

    await screen.findAllByText('PAI-E1')
    expect(localStorage.getItem(cartStorageKey(user.id, 'EU'))).toBe(draft)

    const confirm = await screen.findByRole('button', { name: 'Confirmar Orçamento' })
    await waitFor(() => expect(confirm).toBeEnabled())
    fireEvent.click(confirm)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(posts).toHaveLength(1))

    // Sai do modo cópia: mensagem de sucesso e o rascunho continua intacto.
    // A tela espera 3 s fixos ao criar; por isso o tempo maior neste passo.
    expect(await screen.findByText(/Orçamento confirmado com sucesso/, {}, { timeout: 8000 })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/Novo orçamento copiado de/)).toBeNull())
    // O rascunho volta para a tela e continua o mesmo (o conteúdo; a tela só o regrava).
    const kept = JSON.parse(localStorage.getItem(cartStorageKey(user.id, 'EU')) ?? '[]') as Array<{ line_id: string; qty: number }>
    expect(kept).toHaveLength(1)
    expect(kept[0]).toMatchObject({ line_id: 'draft-1', qty: 9 })
  }, 20000)

  it('Cancelar cópia volta ao orçamento em branco sem criar nada', async () => {
    const posts = installHandlers()
    renderCopy()
    await screen.findAllByText('PAI-E1')

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar cópia' }))

    await waitFor(() => expect(screen.queryByText(/Novo orçamento copiado de/)).toBeNull())
    expect(posts).toHaveLength(0)
  })
})
