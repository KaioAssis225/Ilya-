import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
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
    catalog: { id: 'catalog-ibtw', name: 'IBTW' },
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

function seedCart(userId: string, market: 'EU' | 'BR' = 'EU', lines = 1) {
  localStorage.setItem(cartStorageKey(userId, market), JSON.stringify(Array.from({ length: lines }, (_, index) => ({
    line_id: `parent-line-${index + 1}`, product_code: 'PAI', qty: index + 1, discount: 0,
    opt_categories: {}, optional_choices: [],
  }))))
}

function renderQuote(role: Parameters<typeof productTestUser>[0] = 'admin', market: 'EU' | 'BR' = 'EU', lines = 1) {
  const user = productTestUser(role, market)
  seedCart(user.id, market, lines)
  if (market === 'EU') sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, client.id)
  renderProductPage(<OrcamentoPage />, user)
  return user
}

async function addSpecial() {
  const [button] = await screen.findAllByRole('button', { name: /^Tornar especial/ })
  fireEvent.click(button)
  await screen.findAllByText('PAI-E1')
}

describe('OrcamentoPage — especiais EU', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('transforma a própria linha em PAI-E1 (sem linha nova) e o segundo clique desfaz', async () => {
    installHandlers()
    const user = renderQuote()
    const storedLines = () => JSON.parse(localStorage.getItem(cartStorageKey(user.id, 'EU')) ?? '[]') as Array<{ line_id: string; qty: number }>

    const [toggle] = await screen.findAllByRole('button', { name: /^Tornar especial/ })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(toggle).toHaveAttribute('title', 'Tornar especial')
    expect(screen.getAllByText('Desconto (%)').length).toBeGreaterThan(0)
    fireEvent.click(toggle)

    await screen.findAllByText('PAI-E1')
    expect(screen.queryAllByText('PAI')).toHaveLength(0)
    expect(screen.getAllByText(/ESPECIAL - Mesa Portugal/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Especial (%)').length).toBeGreaterThan(0)
    expect(screen.queryByText('Desconto (%)')).toBeNull()
    const pressed = screen.getAllByRole('button', { name: /^Remover especial/ })[0]
    expect(pressed).toHaveAttribute('aria-pressed', 'true')
    expect(pressed).toHaveAttribute('title', 'Remover especial')
    // Mesma linha: nada novo no carrinho, quantidade mantida.
    await waitFor(() => expect(storedLines()).toHaveLength(1))
    expect(storedLines()[0].line_id).toBe('parent-line-1')

    fireEvent.click(pressed)
    await waitFor(() => expect(screen.queryAllByText('PAI-E1')).toHaveLength(0))
    expect(screen.getAllByText('PAI').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Desconto (%)').length).toBeGreaterThan(0)
    expect(screen.queryAllByText(/ESPECIAL/)).toHaveLength(0)
    expect(screen.getAllByRole('button', { name: /^Tornar especial/ })[0]).toHaveAttribute('aria-pressed', 'false')
    expect(storedLines()).toHaveLength(1)
  })

  it('numera E1, E2… por pai dentro do orçamento e reaproveita o número livre', async () => {
    installHandlers()
    renderQuote('admin', 'EU', 2)
    const clickToggle = async (index: number) => {
      const buttons = await screen.findAllByRole('button', { name: /^(Tornar|Remover) especial/ })
      // Ordem no DOM: cartões mobile (linha 1, 2) e depois a tabela (linha 1, 2).
      fireEvent.click(buttons[index])
    }

    await clickToggle(0)
    await screen.findAllByText('PAI-E1')
    await clickToggle(1)
    await screen.findAllByText('PAI-E2')

    // Desfaz a primeira: E1 volta a ficar livre e é a próxima a ser usada.
    await clickToggle(0)
    await waitFor(() => expect(screen.queryAllByText('PAI-E1')).toHaveLength(0))
    await clickToggle(0)
    await screen.findAllByText('PAI-E1')
    expect(screen.getAllByText('PAI-E2').length).toBeGreaterThan(0)
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

  async function submitButton(name: 'Finalizar Orçamento' | 'Salvar Alterações' = 'Finalizar Orçamento') {
    const button = await screen.findByRole('button', { name })
    await waitFor(() => expect(button).toBeEnabled())
    return button
  }

  function trackPosts() {
    const calls = { post: 0, put: 0 }
    server.use(
      http.post('*/orders', async () => { calls.post += 1; return HttpResponse.json({}, { status: 201 }) }),
      http.put('*/orders/edit-special', async () => { calls.put += 1; return HttpResponse.json({}) }),
    )
    return calls
  }

  it('bloqueia a finalização com especial sem comentário: avisa, realça o ícone e não chama a API', async () => {
    installHandlers()
    renderQuote()
    await addSpecial()
    const calls = trackPosts()

    fireEvent.click(await submitButton())

    expect(await screen.findByRole('alert')).toHaveTextContent('Adicione um comentário aos itens especiais: PAI-E1')
    expect(screen.queryByRole('dialog')).toBeNull()
    const boxes = await screen.findAllByPlaceholderText('Escreva um comentário sobre este item')
    expect(boxes[0]).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getAllByRole('button', { name: /^Comentário de ESPECIAL - Mesa Portugal/ })[0]).toHaveAttribute('data-invalid', 'true')
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(calls.post).toBe(0)

    // Comentário só com espaços continua recusado; com texto, o realce some.
    fireEvent.change(boxes[0], { target: { value: '   ' } })
    fireEvent.click(await submitButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('PAI-E1')
    expect(calls.post).toBe(0)
    fireEvent.change(screen.getAllByPlaceholderText('Escreva um comentário sobre este item')[0], { target: { value: 'Tampo sob medida' } })
    await waitFor(() => expect(screen.getAllByPlaceholderText('Escreva um comentário sobre este item')[0]).not.toHaveAttribute('aria-invalid'))
  })

  it('com especial comentado, confirma o catálogo antes de enviar; Voltar não envia', async () => {
    installHandlers()
    renderQuote()
    await addSpecial()
    fireEvent.click(screen.getAllByRole('button', { name: /^Comentário de ESPECIAL - Mesa Portugal/ })[0])
    fireEvent.change(screen.getAllByPlaceholderText('Escreva um comentário sobre este item')[0], { target: { value: 'Nota' } })
    const calls = trackPosts()

    fireEvent.click(await submitButton())
    const dialog = await screen.findByRole('dialog', { name: 'Confirmar o catálogo' })
    expect(dialog).toHaveTextContent('Este orçamento será feito no catálogo IBTW, tabela Lojista. Está correto?')
    expect(calls.post).toBe(0)

    fireEvent.click(screen.getByRole('button', { name: 'Voltar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(calls.post).toBe(0)

    fireEvent.click(await submitButton())
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(calls.post).toBe(1))
  })

  it('sem item especial não pede confirmação e envia direto', async () => {
    installHandlers()
    renderQuote()
    const calls = trackPosts()
    await screen.findAllByText('PAI')

    fireEvent.click(await submitButton())
    await waitFor(() => expect(calls.post).toBe(1))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('edição: especial sem comentário também é bloqueado; com comentário salva sem diálogo', async () => {
    installHandlers()
    const editUser = productTestUser('admin', 'EU')
    sessionStorage.setItem(`orcamento_client_id:${editUser.id}:EU`, client.id)
    server.use(http.get('*/orders/edit-special', () => HttpResponse.json({
      id: 'edit-special', code: 'ORC-1', orc_id: 'ORC-1', client_id: client.id, rep_id: null,
      market_code: 'EU', price_list_code: 'lojista', currency: 'EUR', locale: 'pt-PT',
      total_value: 100, total_ipi: 0, total_with_ipi: 100, is_finalized: false,
      is_cancelled: false, finalized_at: null, cancelled_at: null, external_code: null,
      notes: null, history: [], created_at: '2026-01-01', updated_at: '2026-01-01',
      items: [{ id: 'special-item', order_id: 'edit-special', product_code: 'PAI',
        description: 'ESPECIAL - Mesa Portugal', is_special: true, special_code: 'PAI-E1',
        special_percent: 0, qty: 1, unit_price: 100, discount: 0, is_circular: false,
        altura: 0, largura: 1, profundidade: 1, opt_categories: {}, optional_choices: [],
        ipi_rate: 0, ipi_value: 0, tax_label: 'IVA', currency: 'EUR', observacao: null,
        comment: null, created_at: '2026-01-01', updated_at: '2026-01-01' }],
    } as Order)))
    const calls = trackPosts()
    renderProductPage(<OrcamentoPage />, editUser, ['/orcamentos?edit=edit-special'])

    fireEvent.click(await submitButton('Salvar Alterações'))
    expect(await screen.findByRole('alert')).toHaveTextContent('PAI-E1')
    expect(calls.put).toBe(0)

    const boxes = await screen.findAllByPlaceholderText('Escreva um comentário sobre este item')
    fireEvent.change(boxes[0], { target: { value: 'Nota' } })
    fireEvent.click(await submitButton('Salvar Alterações'))
    await waitFor(() => expect(calls.put).toBe(1))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('envia o pai como product_code e os campos especiais no payload', async () => {
    installHandlers()
    renderQuote()
    await addSpecial()
    const specialField = screen.getAllByRole('spinbutton', { name: 'Especial em Mesa Portugal' })[0]
    fireEvent.change(specialField, { target: { value: '15' } })
    fireEvent.click(screen.getAllByRole('button', { name: /Comentário de ESPECIAL - Mesa Portugal/ })[0])
    fireEvent.change(screen.getAllByPlaceholderText('Escreva um comentário sobre este item')[0], { target: { value: 'Nota' } })

    let body: { items: Array<Record<string, unknown>> } | null = null
    server.use(http.post('*/orders', async ({ request }) => {
      body = await request.json() as { items: Array<Record<string, unknown>> }
      return HttpResponse.json({}, { status: 201 })
    }))
    const finalize = await screen.findByRole('button', { name: 'Finalizar Orçamento' })
    await waitFor(() => expect(finalize).toBeEnabled())
    fireEvent.click(finalize)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
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
    expect(screen.queryByRole('button', { name: /especial/i })).toBeNull()
  })
})
