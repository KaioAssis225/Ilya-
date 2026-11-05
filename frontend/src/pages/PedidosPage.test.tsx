import { describe, it, expect, beforeEach } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { renderProductPage, productTestUser } from '../test/productTestUtils'
import { server } from '../test/setup'
import PedidosPage from './PedidosPage'
import type { Order, OrderSummary } from '../types'

const makeSummary = (overrides: Partial<OrderSummary> = {}): OrderSummary => ({
  id: 'order-1',
  code: 'PED-0001',
  orc_id: 'ORC-0001',
  market_code: 'BR',
  currency: 'BRL',
  client_id: 'client-1',
  client_name: 'Cliente Teste',
  rep_id: 'rep-1',
  rep_name: 'Representante Teste',
  total_value: 100,
  total_with_ipi: 100,
  is_finalized: false,
  is_cancelled: false,
  finalized_at: null,
  cancelled_at: null,
  items: [],
  created_at: '2024-01-01T00:00:00.000Z',
  ...overrides,
})

const setupHandlers = (summary: OrderSummary) => {
  server.use(
    http.get('*/orders', () => {
      return HttpResponse.json([summary], {
        headers: { 'X-Has-More': 'false' },
      })
    }),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/orders/history', () => {
      return HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })
    }),
  )
}

describe('PedidosPage', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('mostra os anexos privados junto ao comentário do item', async () => {
    const user = userEvent.setup()
    const summary = makeSummary({ items: [{ product_code: 'POL-001', qty: 1 }] })
    const detail: Order = {
      ...summary,
      price_list_code: 'lojista',
      locale: 'pt-BR',
      total_ipi: 0,
      external_code: null,
      notes: null,
      updated_at: summary.created_at,
      history: [],
      items: [{
        id: 'item-1', order_id: summary.id, product_code: 'POL-001', description: 'Poltrona teste',
        is_circular: false, altura: 0.8, largura: 0.7, profundidade: 0.75,
        opt_categories: {}, optional_choices: [], qty: 1, unit_price: 100, discount: 0,
        ipi_rate: 0, ipi_value: 0, tax_label: 'IPI', currency: 'BRL', observacao: null,
        comment: 'Conferir acabamento',
        attachments: [{
          id: 'attachment-1', order_item_id: 'item-1', original_filename: 'referencia.pdf',
          content_type: 'application/pdf', size_bytes: 2048, created_at: summary.created_at,
        }],
        created_at: summary.created_at, updated_at: summary.created_at,
      }],
    }
    setupHandlers(summary)
    server.use(
      http.get('*/orders/order-1', () => HttpResponse.json(detail)),
      http.post('*/products/batch', () => HttpResponse.json([])),
      http.get('*/optionals', () => HttpResponse.json([])),
    )

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    await screen.findAllByText(summary.orc_id)
    await user.click(screen.getAllByLabelText(`Visualizar orçamento ${summary.code}`)[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Conferir acabamento')).toBeVisible()
    expect(within(dialog).getByRole('button', { name: 'referencia.pdf' })).toBeVisible()
  })

  it('admin with open order sees Editar, Finalizar, Cancelar, Excluir actions', async () => {
    const user = userEvent.setup()
    const summary = makeSummary()
    setupHandlers(summary)

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))

    await screen.findAllByText(summary.orc_id)

    expect(screen.getByRole('heading', { name: /Orçamentos/ })).toBeInTheDocument()
    expect(screen.getAllByLabelText(`Visualizar orçamento ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.queryAllByLabelText(`Copiar orçamento ${summary.code}`)).toHaveLength(0)
    await user.click(screen.getAllByLabelText(`Mais ações do orçamento ${summary.code}`)[0])
    expect(screen.getByLabelText(`Copiar orçamento ${summary.code}`)).toBeVisible()
    expect(screen.getAllByLabelText(`Editar orçamento ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Confirmar orçamento ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Cancelar orçamento ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Excluir orçamento ${summary.code}`).length).toBeGreaterThan(0)
  })

  it('keeps view visible and groups copy and the other actions in the ellipsis menu', async () => {
    const user = userEvent.setup()
    const summary = makeSummary({ items: [{ product_code: 'POL-001', qty: 1 }] })
    const detail: Order = {
      ...summary,
      price_list_code: 'lojista',
      locale: 'pt-BR',
      total_ipi: 0,
      external_code: null,
      notes: null,
      updated_at: summary.created_at,
      history: [],
      items: [{
        id: 'item-1', order_id: summary.id, product_code: 'POL-001', description: 'Poltrona teste',
        is_circular: false, altura: 0.8, largura: 0.7, profundidade: 0.75,
        opt_categories: {}, optional_choices: [], qty: 1, unit_price: 100, discount: 0,
        ipi_rate: 0, ipi_value: 0, tax_label: 'IPI', currency: 'BRL', observacao: null,
        created_at: summary.created_at, updated_at: summary.created_at,
      }],
    }
    setupHandlers(summary)
    server.use(
      http.get('*/orders/order-1', () => HttpResponse.json(detail)),
      http.post('*/products/batch', () => HttpResponse.json([])),
      http.get('*/optionals', () => HttpResponse.json([])),
    )

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    await screen.findAllByText(summary.orc_id)
    await user.click(screen.getAllByLabelText(`Mais ações do orçamento ${summary.code}`)[0])
    await user.click(screen.getByLabelText(`Copiar orçamento ${summary.code}`))
    const copyDialog = await screen.findByRole('dialog', { name: 'Copiar orçamento' })
    expect(within(copyDialog).getByRole('button', { name: 'Continuar' })).toBeVisible()
    await user.click(within(copyDialog).getByRole('button', { name: 'Fechar' }))

    await user.click(screen.getAllByLabelText(`Visualizar orçamento ${summary.code}`)[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: 'Copiar orçamento' })).toBeVisible()
    expect(within(dialog).queryByRole('menu')).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Mais ações' }))
    const menu = within(dialog).getByRole('menu', { name: 'Ações do orçamento' })
    expect(within(menu).getByRole('menuitem', { name: 'Confirmar orçamento' })).toBeVisible()
    expect(within(menu).getByRole('menuitem', { name: 'Editar orçamento' })).toBeVisible()
    expect(within(menu).getByRole('menuitem', { name: 'Cancelar orçamento' })).toBeVisible()

    await user.keyboard('{Escape}')
    expect(within(dialog).queryByRole('menu')).not.toBeInTheDocument()
    expect(dialog).toBeVisible()
  })

  it('admin with finalized order hides Editar/Finalizar/Cancelar but keeps Excluir', async () => {
    const user = userEvent.setup()
    const summary = makeSummary({
      is_finalized: true,
      finalized_at: '2024-01-02T00:00:00.000Z',
    })
    setupHandlers(summary)

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))

    await screen.findAllByText(summary.orc_id)

    expect(screen.getAllByLabelText(`Visualizar pedido ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.queryAllByLabelText(`Copiar pedido ${summary.code}`)).toHaveLength(0)
    await user.click(screen.getAllByLabelText(`Mais ações do pedido ${summary.code}`)[0])
    expect(screen.getByLabelText(`Copiar pedido ${summary.code}`)).toBeVisible()
    expect(screen.queryAllByLabelText(`Editar orçamento ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Confirmar orçamento ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Cancelar orçamento ${summary.code}`)).toHaveLength(0)
    expect(screen.getAllByLabelText(`Excluir pedido ${summary.code}`).length).toBeGreaterThan(0)
  })

  it('produtos role sees Editar/Finalizar/Cancelar but not Excluir; cliente linked does not see mutation actions', async () => {
    const user = userEvent.setup()
    const summary = makeSummary()
    setupHandlers(summary)

    const { unmount } = renderProductPage(<PedidosPage />, productTestUser('produtos', 'BR'))

    await screen.findAllByText(summary.orc_id)

    expect(screen.queryAllByLabelText(`Copiar orçamento ${summary.code}`)).toHaveLength(0)
    await user.click(screen.getAllByLabelText(`Mais ações do orçamento ${summary.code}`)[0])
    expect(screen.getAllByLabelText(`Editar orçamento ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Confirmar orçamento ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Cancelar orçamento ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.queryAllByLabelText(`Excluir orçamento ${summary.code}`)).toHaveLength(0)

    unmount()

    renderProductPage(<PedidosPage />, {
      ...productTestUser('cliente', 'BR'),
      linked_id: 'client-1',
    })

    await screen.findAllByText(summary.orc_id)

    await user.click(screen.getAllByLabelText(`Mais ações do orçamento ${summary.code}`)[0])
    expect(screen.queryAllByLabelText(`Editar orçamento ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Confirmar orçamento ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Cancelar orçamento ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Excluir orçamento ${summary.code}`)).toHaveLength(0)
  })

  it('keeps item options collapsed with photo thumbnails and supports item and global expansion', async () => {
    const user = userEvent.setup()
    const summary = makeSummary({ items: [
      { product_code: 'POL-001', qty: 1 },
      { product_code: 'BAN-001', qty: 1 },
    ] })
    const choicePhoto = 'https://example.test/boucle-platina-thumb.jpg'
    const detail: Order = {
      ...summary,
      price_list_code: 'lojista',
      locale: 'pt-BR',
      total_ipi: 0,
      external_code: null,
      notes: null,
      updated_at: summary.created_at,
      history: [],
      items: [
        {
          id: 'item-1',
          order_id: summary.id,
          product_code: 'POL-001',
          description: 'Poltrona teste',
          is_circular: false,
          altura: 0.8,
          largura: 0.7,
          profundidade: 0.75,
          opt_categories: {
            madeira: 'Iroko Taupe Óleo',
            couro_soleta: 'Branco Fosco',
          },
          optional_choices: [{
            id: 'choice-1',
            application_id: 'application-1',
            optional_id: 'optional-boucle',
            application_name: 'Encosto externo',
            application_name_en: 'External backrest',
            category_code: 'tecido',
            category_name: 'Tecido',
            optional_name: 'Bouclé Platina',
            component_name: null,
            display_order: 0,
          }],
          qty: 1,
          unit_price: 100,
          discount: 0,
          ipi_rate: 0,
          ipi_value: 0,
          tax_label: 'IPI',
          currency: 'BRL',
          observacao: null,
          created_at: summary.created_at,
          updated_at: summary.created_at,
        },
        {
          id: 'item-2',
          order_id: summary.id,
          product_code: 'BAN-001',
          description: 'Banco teste',
          is_circular: false,
          altura: 0.45,
          largura: 0.5,
          profundidade: 0.5,
          opt_categories: { metal: 'Latão' },
          optional_choices: [],
          qty: 1,
          unit_price: 100,
          discount: 0,
          ipi_rate: 0,
          ipi_value: 0,
          tax_label: 'IPI',
          currency: 'BRL',
          observacao: null,
          created_at: summary.created_at,
          updated_at: summary.created_at,
        },
      ],
    }
    setupHandlers(summary)
    server.use(
      http.get('*/orders/order-1', () => HttpResponse.json(detail)),
      http.post('*/products/batch', () => HttpResponse.json([])),
      http.get('*/optional-categories', () => HttpResponse.json([
        { id: 'category-1', code: 'madeira', name: 'Madeira' },
        { id: 'category-2', code: 'couro_soleta', name: 'Couro Soleta' },
        { id: 'category-3', code: 'tecido', name: 'Tecido' },
        { id: 'category-4', code: 'metal', name: 'Metal' },
      ])),
      http.get('*/optionals', ({ request }) => {
        const categories = new URL(request.url).searchParams.get('categories')?.split(',') ?? []
        return HttpResponse.json([
          ...(categories.includes('madeira') ? [{ id: 'optional-madeira', category: 'madeira', color_name: 'Iroko Taupe Óleo', photo_url: 'https://example.test/iroko.jpg' }] : []),
          ...(categories.includes('couro_soleta') ? [{ id: 'optional-couro', category: 'couro_soleta', color_name: 'Branco Fosco', photo_url: 'https://example.test/couro.jpg' }] : []),
          ...(categories.includes('tecido') ? [{ id: 'optional-boucle', category: 'tecido', color_name: 'Bouclé Platina', photo_url: 'https://example.test/boucle.jpg', thumbnail_url: choicePhoto }] : []),
          ...(categories.includes('metal') ? [{ id: 'optional-metal', category: 'metal', color_name: 'Latão', photo_url: 'https://example.test/latao.jpg' }] : []),
        ])
      }),
    )

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    await screen.findAllByText(summary.orc_id)
    await user.click(screen.getAllByLabelText(`Visualizar orçamento ${summary.code}`)[0])

    const itemToggle = await screen.findByRole('button', { name: '3 opcionais' })
    const labels = [
      'Madeira — Iroko Taupe Óleo',
      'Couro Soleta — Branco Fosco',
      'Encosto externo: Bouclé Platina',
    ]
    expect(itemToggle).toHaveAttribute('aria-expanded', 'false')
    labels.forEach((label) => {
      expect(screen.queryByText(label)).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    })
    expect(within(screen.getByRole('button', { name: labels[2] })).getByRole('img')).toHaveAttribute('src', choicePhoto)

    await user.click(itemToggle)
    expect(itemToggle).toHaveAttribute('aria-expanded', 'true')
    labels.forEach((label) => expect(screen.getByText(label)).toBeVisible())

    await user.click(itemToggle)
    expect(itemToggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Metal — Latão')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mostrar todos os opcionais' }))
    expect(itemToggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: '1 opcional' })).toHaveAttribute('aria-expanded', 'true')
    labels.forEach((label) => expect(screen.getByText(label)).toBeVisible())
    expect(screen.getByText('Metal — Latão')).toBeVisible()
  })

  it('shows area quantity and hides dimensions using the saved order snapshot', async () => {
    const user = userEvent.setup()
    const summary = makeSummary({ items: [{ product_code: 'TAP-001', qty: 4.5 }] })
    const detail: Order = {
      ...summary,
      price_list_code: 'lojista',
      locale: 'pt-BR',
      total_ipi: 0,
      external_code: null,
      notes: null,
      updated_at: summary.created_at,
      history: [],
      items: [{
        id: 'area-item', order_id: summary.id, product_code: 'TAP-001', description: 'Tapete Amazonas',
        sold_by_area: true, is_circular: false, altura: 9, largura: 9, profundidade: 9,
        opt_categories: {}, optional_choices: [], qty: 4.5, unit_price: 100, discount: 0,
        ipi_rate: 0, ipi_value: 0, tax_label: 'IPI', currency: 'BRL', observacao: null,
        created_at: summary.created_at, updated_at: summary.created_at,
      }],
    }
    setupHandlers(summary)
    server.use(
      http.get('*/orders/order-1', () => HttpResponse.json(detail)),
      http.post('*/products/batch', () => HttpResponse.json([])),
      http.get('*/optionals', () => HttpResponse.json([])),
    )

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    expect((await screen.findAllByText('TAP-001(4,5 m²)')).length).toBeGreaterThan(0)
    await user.click(screen.getAllByLabelText(`Visualizar orçamento ${summary.code}`)[0])

    const code = await screen.findByText('TAP-001')
    const row = code.closest('tr')!
    const cells = within(row).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('—')
    expect(cells[4]).toHaveTextContent('4,5 m²')
  })
})
