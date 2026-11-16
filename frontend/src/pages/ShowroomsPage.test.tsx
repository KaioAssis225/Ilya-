import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import ShowroomsPage from './ShowroomsPage'
import { productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

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
})
