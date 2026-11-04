import { beforeEach, describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import PedidosPage from './PedidosPage'
import type { Order, OrderSummary } from '../types'

// Datas ao meio-dia UTC: o dia exibido não muda com o fuso do navegador.
const CREATED = '2024-01-01T12:00:00.000Z'
const FINALIZED = '2024-03-15T12:00:00.000Z'
// Diferente de propósito: prova que a tela lê production_started_at, não finalized_at.
const STARTED = '2024-03-16T12:00:00.000Z'
const DELIVERED = '2024-04-20T12:00:00.000Z'

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
  is_finalized: true,
  is_cancelled: false,
  finalized_at: FINALIZED,
  production_started_at: STARTED,
  cancelled_at: null,
  order_stage: 'production',
  delivered_at: null,
  items: [],
  created_at: CREATED,
  ...overrides,
})

function installBackend(rows: OrderSummary[]) {
  const requests: Array<Record<string, string>> = []
  server.use(
    http.get('*/orders', ({ request }) => {
      requests.push(Object.fromEntries(new URL(request.url).searchParams))
      return HttpResponse.json(rows, { headers: { 'X-Has-More': 'false' } })
    }),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/orders/history', () => HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })),
    http.post('*/products/batch', () => HttpResponse.json([])),
    http.get('*/orders/:id/emails', () => HttpResponse.json({ detail: 'sem e-mails' }, { status: 404 })),
  )
  for (const row of rows) {
    const detail: Order = {
      ...row,
      price_list_code: 'lojista',
      locale: row.market_code === 'EU' ? 'pt-PT' : 'pt-BR',
      total_ipi: 0,
      external_code: null,
      notes: null,
      items: [],
      history: [],
      updated_at: row.created_at,
    }
    server.use(http.get(`*/orders/${row.id}`, () => HttpResponse.json(detail)))
  }
  return requests
}

describe('PedidosPage: datas de finalização e entrega', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('aba Pedido ordena e filtra pela finalização (servidor) e mostra o início de produção, não a data de criação', async () => {
    const requests = installBackend([makeSummary()])

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')

    expect(requests.some((query) => query.date_basis === 'finalized_at')).toBe(true)
    expect(screen.getByRole('columnheader', { name: 'Início de produção' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Data' })).not.toBeInTheDocument()
    expect(screen.getAllByText('16/03/2024').length).toBeGreaterThan(0)
    expect(screen.queryByText('01/01/2024')).not.toBeInTheDocument()
    expect(screen.getByText('Início de produção 16/03/2024')).toBeInTheDocument()
  })

  it('coluna "Entregue em" mostra a data só quando a etapa é Entregue', async () => {
    installBackend([
      makeSummary({ id: 'a', code: 'PED-0001', order_stage: 'production', delivered_at: null }),
      makeSummary({ id: 'b', code: 'PED-0002', order_stage: 'delivered', delivered_at: DELIVERED }),
    ])

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0002')

    expect(screen.getByRole('columnheader', { name: 'Entregue em' })).toBeInTheDocument()
    const rows = screen.getAllByRole('row')
    const production = rows.find((row) => within(row).queryByText('PED-0001'))!
    const delivered = rows.find((row) => within(row).queryByText('PED-0002'))!
    expect(within(production).queryByText('20/04/2024')).not.toBeInTheDocument()
    expect(within(production).getByText('—', { selector: 'span' })).toBeInTheDocument()
    expect(within(delivered).getByText('20/04/2024')).toBeInTheDocument()
    // No cartão mobile a data de entrega só aparece no pedido entregue.
    expect(screen.getAllByText('Entregue em 20/04/2024')).toHaveLength(1)
  })

  it('aba Orçamento continua com a data de criação e sem "Entregue em"', async () => {
    const requests = installBackend([
      makeSummary({ is_finalized: false, finalized_at: null, order_stage: null }),
    ])

    renderProductPage(<PedidosPage scope="quotes" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')

    expect(requests.some((query) => query.date_basis === 'created_at')).toBe(true)
    expect(screen.getByRole('columnheader', { name: 'Data' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Entregue em' })).not.toBeInTheDocument()
    expect(screen.getAllByText('01/01/2024').length).toBeGreaterThan(0)
  })

  it('sem production_started_at, cai para a data de finalização', async () => {
    installBackend([makeSummary({ production_started_at: null })])

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')

    expect(screen.getByText('Início de produção 15/03/2024')).toBeInTheDocument()
    expect(screen.queryByText('16/03/2024')).not.toBeInTheDocument()
  })

  it('rotula os filtros de data como início de produção na aba Pedido', async () => {
    const user = userEvent.setup()
    installBackend([makeSummary()])

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')
    await user.click(screen.getByRole('button', { name: /Filtros/ }))

    expect(screen.getByLabelText('Início de produção de')).toBeInTheDocument()
    expect(screen.getByLabelText('Início de produção até')).toBeInTheDocument()
  })

  it('detalhe mostra "Início de produção" e, entregue, "Entregue em"; em Produção não mostra a entrega', async () => {
    const user = userEvent.setup()
    installBackend([
      makeSummary({ id: 'a', code: 'PED-0001', order_stage: 'production', delivered_at: null }),
      makeSummary({ id: 'b', code: 'PED-0002', order_stage: 'delivered', delivered_at: DELIVERED }),
    ])

    const { unmount } = renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')
    await user.click(screen.getAllByLabelText('Visualizar pedido PED-0001')[0])
    expect(await screen.findByText('Início de produção', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText('16/03/2024', { selector: 'p' })).toBeInTheDocument()
    expect(screen.queryByText('Entregue em', { selector: 'p' })).not.toBeInTheDocument()
    unmount()

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0002')
    await user.click(screen.getAllByLabelText('Visualizar pedido PED-0002')[0])
    expect(await screen.findByText('Entregue em', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText('20/04/2024', { selector: 'p' })).toBeInTheDocument()
  })

  it('traduz rótulos para en-GB no mercado EU', async () => {
    const euUser = productTestUser('admin', 'EU')
    localStorage.setItem(`ilya-locale:${euUser.id}:EU`, 'en-GB')
    installBackend([
      makeSummary({ market_code: 'EU', currency: 'EUR', order_stage: 'delivered', delivered_at: DELIVERED }),
    ])

    renderProductPage(<PedidosPage scope="orders" />, euUser)
    await screen.findAllByText('PED-0001')

    expect(screen.getByRole('columnheader', { name: 'Production started' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Delivered on' })).toBeInTheDocument()
    expect(screen.getByText('Production started 16/03/2024')).toBeInTheDocument()
    expect(screen.getByText('Delivered on 20/04/2024')).toBeInTheDocument()
  })
})
