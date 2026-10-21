import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { renderProductPage, productTestUser } from '../test/productTestUtils'
import { server } from '../test/setup'
import PedidosPage from './PedidosPage'
import type { OrderSummary } from '../types'

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

  it('admin with open order sees Editar, Finalizar, Cancelar, Excluir actions', async () => {
    const summary = makeSummary()
    setupHandlers(summary)

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))

    await screen.findAllByText(summary.code)

    expect(screen.getAllByLabelText(`Editar pedido ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Finalizar pedido ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Cancelar pedido ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Excluir pedido ${summary.code}`).length).toBeGreaterThan(0)
  })

  it('admin with finalized order hides Editar/Finalizar/Cancelar but keeps Excluir', async () => {
    const summary = makeSummary({
      is_finalized: true,
      finalized_at: '2024-01-02T00:00:00.000Z',
    })
    setupHandlers(summary)

    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))

    await screen.findAllByText(summary.code)

    expect(screen.queryAllByLabelText(`Editar pedido ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Finalizar pedido ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Cancelar pedido ${summary.code}`)).toHaveLength(0)
    expect(screen.getAllByLabelText(`Excluir pedido ${summary.code}`).length).toBeGreaterThan(0)
  })

  it('produtos role sees Editar/Finalizar/Cancelar but not Excluir; cliente linked does not see mutation actions', async () => {
    const summary = makeSummary()
    setupHandlers(summary)

    const { unmount } = renderProductPage(<PedidosPage />, productTestUser('produtos', 'BR'))

    await screen.findAllByText(summary.code)

    expect(screen.getAllByLabelText(`Editar pedido ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Finalizar pedido ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`Cancelar pedido ${summary.code}`).length).toBeGreaterThan(0)
    expect(screen.queryAllByLabelText(`Excluir pedido ${summary.code}`)).toHaveLength(0)

    unmount()

    renderProductPage(<PedidosPage />, {
      ...productTestUser('cliente', 'BR'),
      linked_id: 'client-1',
    })

    await screen.findAllByText(summary.code)

    expect(screen.queryAllByLabelText(`Editar pedido ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Finalizar pedido ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Cancelar pedido ${summary.code}`)).toHaveLength(0)
    expect(screen.queryAllByLabelText(`Excluir pedido ${summary.code}`)).toHaveLength(0)
  })
})
