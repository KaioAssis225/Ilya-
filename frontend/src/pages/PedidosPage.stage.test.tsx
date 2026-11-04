import { beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import PedidosPage from './PedidosPage'
import type { OrderStage, OrderSummary } from '../types'

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
  finalized_at: '2024-01-02T00:00:00.000Z',
  cancelled_at: null,
  order_stage: 'production',
  items: [],
  created_at: '2024-01-01T00:00:00.000Z',
  ...overrides,
})

// Simula o servidor: filtro `stage` na listagem e POST /orders/:id/stage.
function installOrdersBackend(initial: OrderSummary[]) {
  const orders = [...initial]
  const stageRequests: Array<string | null> = []
  const stagePosts: Array<{ id: string; stage: OrderStage }> = []
  server.use(
    http.get('*/orders', ({ request }) => {
      const params = new URL(request.url).searchParams
      const stage = params.get('stage')
      stageRequests.push(stage)
      const rows = orders.filter((order) => order.is_finalized && (!stage || order.order_stage === stage))
      return HttpResponse.json(rows, { headers: { 'X-Has-More': 'false' } })
    }),
    http.post('*/orders/:id/stage', async ({ params, request }) => {
      const body = (await request.json()) as { stage: OrderStage }
      stagePosts.push({ id: String(params.id), stage: body.stage })
      const order = orders.find((candidate) => candidate.id === params.id)
      if (order) order.order_stage = body.stage
      return HttpResponse.json(order)
    }),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/orders/history', () => HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })),
  )
  return { stageRequests, stagePosts }
}

describe('PedidosPage: etapa do pedido (Produção x Entregue)', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('mostra a etapa no lugar de "Finalizado"; pedido sem etapa conta como Produção', async () => {
    installOrdersBackend([
      makeSummary({ id: 'a', code: 'PED-0001', order_stage: 'production' }),
      makeSummary({ id: 'b', code: 'PED-0002', order_stage: 'delivered' }),
      makeSummary({ id: 'c', code: 'PED-0003', order_stage: null }),
    ])

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')

    expect(screen.queryByText('Finalizado')).not.toBeInTheDocument()
    expect(screen.getAllByText('Produção').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Entregue').length).toBeGreaterThan(0)
  })

  it('marca como entregue pela lista, avisa e permite desfazer', async () => {
    const user = userEvent.setup()
    const { stagePosts } = installOrdersBackend([makeSummary()])

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')

    await user.click(screen.getAllByLabelText('Mais ações do pedido PED-0001')[0])
    await user.click(screen.getByLabelText('Marcar como entregue PED-0001'))

    expect(await screen.findByText('Pedido PED-0001 marcado como entregue.')).toBeInTheDocument()
    expect(stagePosts).toEqual([{ id: 'order-1', stage: 'delivered' }])
    await waitFor(() => expect(screen.getAllByText('Entregue').length).toBeGreaterThan(0))
    expect(screen.queryByRole('button', { name: 'Marcar como entregue PED-0001' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Desfazer' }))
    expect(await screen.findByText('Pedido PED-0001 voltou para Produção.')).toBeInTheDocument()
    expect(stagePosts).toEqual([
      { id: 'order-1', stage: 'delivered' },
      { id: 'order-1', stage: 'production' },
    ])
  })

  it('falha ao mudar a etapa mostra o alerta e não anuncia sucesso', async () => {
    const user = userEvent.setup()
    installOrdersBackend([makeSummary()])
    server.use(http.post('*/orders/:id/stage', () => HttpResponse.json({ detail: 'erro' }, { status: 500 })))

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')
    await user.click(screen.getAllByLabelText('Mais ações do pedido PED-0001')[0])
    await user.click(screen.getByLabelText('Marcar como entregue PED-0001'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível alterar a etapa do pedido. Tente novamente.')
    expect(screen.queryByText('Pedido PED-0001 marcado como entregue.')).not.toBeInTheDocument()
  })

  it('filtra por etapa no servidor e troca o filtro de status pelo de etapa', async () => {
    const user = userEvent.setup()
    const { stageRequests } = installOrdersBackend([
      makeSummary({ id: 'a', code: 'PED-0001', order_stage: 'production' }),
      makeSummary({ id: 'b', code: 'PED-0002', order_stage: 'delivered' }),
    ])

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')
    await user.click(screen.getByRole('button', { name: /Filtros/ }))

    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument()
    const select = screen.getByLabelText('Etapa') as HTMLSelectElement
    expect(Array.from(select.options).map((option) => option.text)).toEqual(['Todas', 'Produção', 'Entregue'])

    await user.selectOptions(select, 'delivered')
    await waitFor(() => expect(stageRequests).toContain('delivered'))
    await waitFor(() => expect(screen.queryAllByText('PED-0001')).toHaveLength(0))
    expect(screen.getAllByText('PED-0002').length).toBeGreaterThan(0)
  })

  it('cliente final vê a etapa, mas não tem ação para mudá-la', async () => {
    installOrdersBackend([makeSummary()])
    const client = { ...productTestUser('cliente', 'BR'), linked_id: 'client-1' }

    renderProductPage(<PedidosPage scope="orders" />, client)
    await screen.findAllByText('PED-0001')

    expect(screen.getAllByText('Produção').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /Marcar como entregue/ })).not.toBeInTheDocument()
  })
})
