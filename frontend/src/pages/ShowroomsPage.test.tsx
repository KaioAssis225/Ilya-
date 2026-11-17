import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ShowroomsPage from './ShowroomsPage'
import { productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import { showroomChoicesToCart } from '../lib/showroomCart'

const now = '2026-11-16T12:00:00Z'

function showroomUser(permitted = true) {
  return {
    ...productTestUser('vendedor', 'EU'),
    can_manage_showrooms: permitted,
  }
}

function boxFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: 'box-1', name: 'Estoque Portugal', market_code: 'EU',
    price_list_code: 'lojista', currency: 'EUR',
    items: [{
      item_id: 'item-1', id: 'product-1', product_code: 'ICD0106',
      description: 'ALBA - CADEIRA', thumbnail_url: null,
      unit_price: '89.42', quantity: 2, line_total: '178.84',
      optional_choices: [],
    }],
    item_count: 1, total_quantity: 2, total_value: '178.84',
    created_at: now, updated_at: now,
    ...overrides,
  }
}

describe('ShowroomsPage', () => {
  beforeEach(() => {
    // O histórico de transferências carrega junto com qualquer box aberta.
    server.use(http.get('*/showroom-boxes/:boxId/transfers', () => HttpResponse.json([])))
  })

  it('não renderiza a área para usuário sem a capacidade', () => {
    server.use(http.get('*/showroom-boxes', () => HttpResponse.json([])))
    renderProductPage(<ShowroomsPage />, showroomUser(false), ['/showrooms'])
    expect(screen.queryByText('Estoque')).not.toBeInTheDocument()
  })

  it('exibe quantidade, tabela e valores vivos da box', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([boxFixture()])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([])),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])

    await user.click(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' }))
    expect(await screen.findByRole('heading', { name: 'Estoque Portugal' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Todas as boxes' })).toBeInTheDocument()
    expect(screen.getByText('Lojista')).toBeInTheDocument()
    expect(screen.getByText('89,42 €')).toBeInTheDocument()
    expect(screen.getAllByText('178,84 €').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByLabelText('Quantidade de ICD0106')[0]).toHaveValue(2)
  })

  it('cria outra box com a tabela selecionada', async () => {
    const user = userEvent.setup()
    const requests: Array<Record<string, unknown>> = []
    const boxes = [boxFixture()]
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json(boxes)),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([])),
      http.post('*/showroom-boxes', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        requests.push(body)
        boxes.push(boxFixture({
          id: 'box-2', ...body, items: [], item_count: 0,
          total_quantity: 0, total_value: '0.00',
        }))
        return HttpResponse.json(boxes[1], { status: 201 })
      }),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])
    await screen.findByRole('button', { name: 'Abrir Estoque Portugal' })

    await user.click(screen.getByRole('button', { name: 'Local Estoque' }))
    await user.type(screen.getByLabelText('Nome da box'), 'Feira Porto')
    await user.selectOptions(screen.getByLabelText('Tabela de preço'), 'arquiteto')
    await user.click(screen.getByRole('button', { name: 'Salvar box' }))

    await waitFor(() => expect(requests).toEqual([{
      name: 'Feira Porto', price_list_code: 'arquiteto',
    }]))
    expect(await screen.findByText('Feira Porto')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir Feira Porto' })).toBeInTheDocument()
    expect(screen.getByText('Arquiteto')).toBeInTheDocument()
  })

  it('adiciona, altera quantidade e remove um produto', async () => {
    const user = userEvent.setup()
    let current = boxFixture({ items: [], item_count: 0, total_quantity: 0, total_value: '0.00' })
    const added = vi.fn()
    const patched = vi.fn()
    const removed = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([current])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([{
        id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA',
        thumbnail_url: null, unit_price: '89.42',
      }])),
      http.post('*/products/batch', () => HttpResponse.json([
        productFixture('EU', {
          id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA',
        }),
      ])),
      http.post('*/showroom-boxes/:boxId/items', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        added()
        expect(body).toMatchObject({
          product_id: 'product-1', quantity: 1, optional_choices: [],
        })
        current = boxFixture()
        return HttpResponse.json(current)
      }),
      http.patch('*/showroom-boxes/:boxId/items/:itemId', async ({ request }) => {
        const body = await request.json() as { quantity: number }
        patched(body)
        current = boxFixture({
          items: [{ ...boxFixture().items[0], quantity: body.quantity, line_total: '268.26' }],
          total_quantity: body.quantity, total_value: '268.26',
        })
        return HttpResponse.json(current)
      }),
      http.delete('*/showroom-boxes/:boxId/items/:itemId', () => {
        removed()
        current = boxFixture({ items: [], item_count: 0, total_quantity: 0, total_value: '0.00' })
        return HttpResponse.json(current)
      }),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])

    await user.click(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' }))
    await user.type(screen.getByLabelText('Buscar produtos'), 'ICD0106')
    await user.click(await screen.findByRole('button', { name: 'Configurar ICD0106' }))
    await user.click(await screen.findByRole('button', { name: 'Adicionar ao estoque' }))
    await waitFor(() => expect(added).toHaveBeenCalledOnce())
    const quantity = (await screen.findAllByLabelText('Quantidade de ICD0106'))[0]
    await user.clear(quantity)
    await user.type(quantity, '3')
    await user.tab()
    await waitFor(() => expect(patched).toHaveBeenCalledWith({ quantity: 3 }))

    await user.click(screen.getAllByRole('button', { name: 'Remover ICD0106' })[0])
    await waitFor(() => expect(removed).toHaveBeenCalledOnce())
    expect(await screen.findByText('Esta box ainda está vazia')).toBeInTheDocument()
  })

  it('mantém o foco somente na box aberta e permite voltar à visão geral', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([
        boxFixture(),
        boxFixture({ id: 'box-2', name: 'Feira Porto' }),
      ])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([])),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])

    expect(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir Feira Porto' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Abrir Estoque Portugal' }))

    expect(await screen.findByRole('heading', { name: 'Estoque Portugal' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir Feira Porto' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Todas as boxes' }))

    expect(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir Feira Porto' })).toBeInTheDocument()
  })

  it('apresenta a visão geral e o detalhe da box em inglês', async () => {
    const user = userEvent.setup()
    const authUser = showroomUser()
    localStorage.setItem(`ilya-locale:${authUser.id}:EU`, 'en-GB')
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([boxFixture()])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([])),
    )
    renderProductPage(<ShowroomsPage />, authUser, ['/showrooms'])

    await user.click(await screen.findByRole('button', { name: 'Open Estoque Portugal' }))

    expect(await screen.findByRole('heading', { name: 'Estoque Portugal' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All boxes' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit location' })).toBeInTheDocument()
    expect(screen.getByText('Products in this box')).toBeInTheDocument()
    expect(screen.getByLabelText('Search products')).toBeInTheDocument()
  })

  it('envia opcionais e mantém combinações visíveis como configurações separadas', async () => {
    const user = userEvent.setup()
    const requests: Array<Record<string, unknown>> = []
    let current = boxFixture({ items: [], item_count: 0, total_quantity: 0, total_value: '0.00' })
    const option = {
      id: 'optional-taupe', category: 'PINTURA', color_name: 'TAUPE', brand: 'IBTW' as const,
      photo_url: null, thumbnail_url: '/media/taupe.webp',
    }
    const application = {
      id: 'application-legs', category_id: 'category-paint', category_code: 'PINTURA',
      category_name: 'Pintura', name: 'Pés', name_en: 'Legs', required: true,
      display_order: 0, allow_all: false, allow_repeat: true, allowed_optionals: [option],
    }
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([current])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([{
        id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA',
        thumbnail_url: null, unit_price: '89.42',
      }])),
      http.post('*/products/batch', () => HttpResponse.json([
        productFixture('EU', {
          id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA',
          optional_applications: [application],
        }),
      ])),
      http.post('*/showroom-boxes/:boxId/items', async ({ request }) => {
        requests.push(await request.json() as Record<string, unknown>)
        current = boxFixture({
          items: [{
            ...boxFixture().items[0],
            optional_choices: [{
              application_id: application.id, application_name: 'Pés', application_name_en: 'Legs',
              category_code: 'PINTURA', category_name: 'Pintura', optional_id: option.id,
              optional_name: 'TAUPE', component_name: null, thumbnail_url: option.thumbnail_url,
            }],
          }],
        })
        return HttpResponse.json(current)
      }),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])

    await user.click(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' }))
    await user.type(screen.getByLabelText('Buscar produtos'), 'ICD0106')
    await user.click(await screen.findByRole('button', { name: 'Configurar ICD0106' }))
    await user.click(await screen.findByRole('button', { name: 'TAUPE' }))
    await user.click(screen.getByRole('button', { name: 'Adicionar ao estoque' }))

    await waitFor(() => expect(requests).toEqual([{
      product_id: 'product-1', quantity: 1,
      optional_choices: [{ application_id: 'application-legs', optional_id: 'optional-taupe' }],
    }]))
    expect((await screen.findAllByText('Pés')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('TAUPE').length).toBeGreaterThan(0)
  })

  it('salva com opcional obrigatório pendente e com Customizado', async () => {
    const user = userEvent.setup()
    const requests: Array<Record<string, unknown>> = []
    const application = (id: string, name: string, brand: 'IBTW' | 'ILYA') => ({
      id, category_id: 'category-paint', category_code: 'PINTURA',
      category_name: 'Pintura', name, name_en: name, required: true,
      display_order: 0, allow_all: false, allow_repeat: true,
      allowed_optionals: [{
        id: `optional-${id}`, category: 'PINTURA', color_name: `COR ${name}`, brand,
        photo_url: null, thumbnail_url: null,
      }],
    })
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([boxFixture({ items: [], item_count: 0 })])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([{
        id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA',
        thumbnail_url: null, unit_price: '89.42',
      }])),
      http.post('*/products/batch', () => HttpResponse.json([
        productFixture('EU', {
          id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA',
          optional_applications: [application('legs', 'Pés', 'IBTW'), application('top', 'Tampo', 'ILYA')],
        }),
      ])),
      http.post('*/showroom-boxes/:boxId/items', async ({ request }) => {
        requests.push(await request.json() as Record<string, unknown>)
        return HttpResponse.json(boxFixture())
      }),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])

    await user.click(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' }))
    await user.type(screen.getByLabelText('Buscar produtos'), 'ICD0106')
    await user.click(await screen.findByRole('button', { name: 'Configurar ICD0106' }))
    // Acabamento ILYA não oferece Customizado; o IBTW oferece.
    expect(await screen.findAllByRole('button', { name: 'Customizado' })).toHaveLength(1)
    expect(screen.getByText(/2 opcional\(is\) obrigatório\(s\) sem escolha/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Customizado' }))
    await user.click(screen.getByRole('button', { name: 'Adicionar ao estoque' }))

    await waitFor(() => expect(requests).toEqual([{
      product_id: 'product-1', quantity: 1,
      optional_choices: [{ application_id: 'legs', custom: true }],
    }]))
  })

  it('mostra o erro do servidor ao lado do botão ao falhar ao salvar o item', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([boxFixture({ items: [], item_count: 0 })])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([{
        id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA',
        thumbnail_url: null, unit_price: '89.42',
      }])),
      http.post('*/products/batch', () => HttpResponse.json([
        productFixture('EU', { id: 'product-1', product_code: 'ICD0106', description: 'ALBA - CADEIRA' }),
      ])),
      http.post('*/showroom-boxes/:boxId/items', () => HttpResponse.json(
        { detail: 'Opção não autorizada em “Pés”.' }, { status: 422 },
      )),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])

    await user.click(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' }))
    await user.type(screen.getByLabelText('Buscar produtos'), 'ICD0106')
    await user.click(await screen.findByRole('button', { name: 'Configurar ICD0106' }))
    await user.click(await screen.findByRole('button', { name: 'Adicionar ao estoque' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Opção não autorizada em “Pés”.')
  })

  it('avisa quando a alteração de quantidade é recusada pelo servidor', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/showroom-boxes', () => HttpResponse.json([boxFixture()])),
      http.get('*/showroom-boxes/products', () => HttpResponse.json([])),
      http.patch('*/showroom-boxes/:boxId/items/:itemId', () => HttpResponse.json(
        { detail: 'Sem permissão nesta box.' }, { status: 403 },
      )),
    )
    renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])

    await user.click(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' }))
    const quantity = (await screen.findAllByLabelText('Quantidade de ICD0106'))[0]
    await user.clear(quantity)
    await user.type(quantity, '5')
    await user.tab()

    expect(await screen.findByRole('alert')).toHaveTextContent('Sem permissão nesta box.')
  })

  describe('transferência', () => {
    const transferRecord = {
      id: 'transfer-1', created_at: now, created_by_name: 'Maria', source_box_id: 'box-1',
      source_box_name: 'Estoque Portugal', destination_type: 'box', destination_box_id: 'box-2',
      destination_box_name: 'Feira Porto', destination_order_id: null, destination_order_code: null,
      product_code: 'ICD0106', quantity: 1, optional_choices: [],
    }

    async function openTransfer(user: ReturnType<typeof userEvent.setup>) {
      await user.click(await screen.findByRole('button', { name: 'Abrir Estoque Portugal' }))
      await user.click(await screen.findByRole('button', { name: 'Transferência' }))
      return screen.findByRole('dialog', { name: 'Transferir peças' })
    }

    function baseHandlers() {
      return [
        http.get('*/showroom-boxes', () => HttpResponse.json([
          boxFixture(),
          boxFixture({ id: 'box-2', name: 'Feira Porto', items: [], item_count: 0, total_quantity: 0, total_value: '0.00' }),
        ])),
        http.get('*/showroom-boxes/products', () => HttpResponse.json([])),
        http.get('*/showroom-boxes/:boxId/transfers', () => HttpResponse.json([transferRecord])),
        http.get('*/clients', () => HttpResponse.json([{ id: 'client-7', name: 'Cliente Sete' }])),
      ]
    }

    it('transfere para outra box e não deixa passar do saldo', async () => {
      const user = userEvent.setup()
      const requests: Array<Record<string, unknown>> = []
      server.use(
        ...baseHandlers(),
        http.post('*/showroom-boxes/:boxId/transfers', async ({ request }) => {
          requests.push(await request.json() as Record<string, unknown>)
          return HttpResponse.json({ transfer: { ...transferRecord, quantity: 2 }, box: boxFixture() }, { status: 201 })
        }),
      )
      renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])
      const dialog = await openTransfer(user)

      expect(within(dialog).getByText('Máximo: 2 (saldo do armazém)')).toBeInTheDocument()
      const quantity = within(dialog).getByLabelText('Quantidade a transferir')
      await user.clear(quantity)
      await user.type(quantity, '3')
      await user.selectOptions(within(dialog).getByLabelText('Armazém de destino'), 'box-2')
      expect(within(dialog).getByRole('button', { name: 'Transferir' })).toBeDisabled()

      await user.clear(quantity)
      await user.type(quantity, '2')
      await user.click(within(dialog).getByRole('button', { name: 'Transferir' }))

      await waitFor(() => expect(requests).toEqual([{
        item_id: 'item-1', quantity: 2, destination: { type: 'box', box_id: 'box-2' },
      }]))
      expect(await screen.findByRole('status')).toHaveTextContent('2 x ICD0106 transferido(s) para Feira Porto.')
      expect(screen.getByText('Transferências recentes')).toBeInTheDocument()
    })

    it('não oferece orçamento existente: só outra box e Novo orçamento', async () => {
      const user = userEvent.setup()
      const orderRequests: string[] = []
      server.use(
        ...baseHandlers(),
        http.get('*/orders', ({ request }) => { orderRequests.push(request.url); return HttpResponse.json([]) }),
      )
      renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])
      const dialog = await openTransfer(user)

      expect(within(dialog).getByRole('button', { name: 'Outro armazém' })).toBeInTheDocument()
      expect(within(dialog).getByRole('button', { name: 'Novo orçamento' })).toBeInTheDocument()
      expect(within(dialog).queryByRole('button', { name: /Orçamento existente/ })).not.toBeInTheDocument()
      expect(within(dialog).queryByLabelText('Orçamento em aberto')).not.toBeInTheDocument()
      expect(orderRequests).toEqual([])
    })

    it('Novo orçamento leva a peça para a aba sem criar orçamento nem tirar do estoque', async () => {
      const user = userEvent.setup()
      const authUser = showroomUser()
      const posts: string[] = []
      server.use(
        ...baseHandlers(),
        http.post('*/showroom-boxes/:boxId/transfers', () => { posts.push('transfer'); return HttpResponse.json({}, { status: 201 }) }),
        http.post('*/orders', () => { posts.push('order'); return HttpResponse.json({}, { status: 201 }) }),
      )
      renderProductPage(<ShowroomsPage />, authUser, ['/showrooms'])
      const dialog = await openTransfer(user)

      await user.click(within(dialog).getByRole('button', { name: 'Novo orçamento' }))
      expect(within(dialog).getByText(/O saldo só baixa do estoque quando você salvar/)).toBeInTheDocument()
      const quantity = within(dialog).getByLabelText('Quantidade a transferir')
      await user.clear(quantity)
      await user.type(quantity, '2')
      await user.click(within(dialog).getByRole('button', { name: 'Levar para Novo orçamento' }))

      const stored = JSON.parse(localStorage.getItem(`carrinho_orcamento:${authUser.id}:EU`) ?? '[]')
      expect(stored).toHaveLength(1)
      expect(stored[0]).toMatchObject({
        product_code: 'ICD0106', qty: 2, discount: 0,
        showroom_source_item_id: 'item-1', showroom_box_name: 'Estoque Portugal',
      })
      expect(posts).toEqual([])
    })

    it('converte os opcionais do estoque (aplicação, Customizado e categoria) para o carrinho', () => {
      expect(showroomChoicesToCart([
        { application_id: 'app-1', category_code: 'PINTURA', optional_id: 'opt-1', optional_name: 'TAUPE' },
        { application_id: 'app-2', category_code: 'PINTURA', optional_id: null, optional_name: 'Customizado', custom: true },
        { application_id: null, category_code: 'TECIDO', optional_id: 'opt-3', optional_name: 'LINHO' },
      ])).toEqual({
        optional_choices: [
          { application_id: 'app-1', optional_id: 'opt-1' },
          { application_id: 'app-2', custom_text: '' },
        ],
        opt_categories: { TECIDO: 'LINHO' },
      })
    })

    it('mostra o motivo quando o servidor recusa a transferência', async () => {
      const user = userEvent.setup()
      server.use(
        ...baseHandlers(),
        http.post('*/showroom-boxes/:boxId/transfers', () => HttpResponse.json(
          { detail: 'Quantidade maior que o saldo do armazém: há 1 peça(s).' }, { status: 422 },
        )),
      )
      renderProductPage(<ShowroomsPage />, showroomUser(), ['/showrooms'])
      const dialog = await openTransfer(user)

      await user.selectOptions(within(dialog).getByLabelText('Armazém de destino'), 'box-2')
      await user.click(within(dialog).getByRole('button', { name: 'Transferir' }))

      expect(await within(dialog).findByRole('alert')).toHaveTextContent('Quantidade maior que o saldo do armazém: há 1 peça(s).')
    })
  })
})
