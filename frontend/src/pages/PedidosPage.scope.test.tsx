import { beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
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

// Simula o filtro de servidor: a lista devolvida depende do parâmetro `status`.
function installOrdersBackend(initial: OrderSummary[]) {
  const orders = [...initial]
  const statusRequests: Array<string | null> = []
  server.use(
    http.get('*/orders', ({ request }) => {
      const status = new URL(request.url).searchParams.get('status')
      statusRequests.push(status)
      const rows = orders.filter((order) => {
        if (status === 'finalized') return order.is_finalized
        if (status === 'not_finalized') return !order.is_finalized
        if (status === 'in_progress') return !order.is_finalized && !order.is_cancelled
        if (status === 'cancelled') return order.is_cancelled
        return true
      })
      return HttpResponse.json(rows, { headers: { 'X-Has-More': 'false' } })
    }),
    http.post('*/orders/:id/finalize', ({ params }) => {
      const order = orders.find((candidate) => candidate.id === params.id)
      if (order) order.is_finalized = true
      return HttpResponse.json(order)
    }),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/orders/history', () => HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })),
  )
  return { statusRequests }
}

function Tabs() {
  return (
    <Routes>
      <Route path="/pedidos" element={<PedidosPage key="quotes" scope="quotes" />} />
      <Route path="/pedidos-finalizados" element={<PedidosPage key="orders" scope="orders" />} />
    </Routes>
  )
}

describe('PedidosPage por aba (Orçamento x Pedido)', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('Orçamento pede não finalizados ao servidor e Pedido pede só finalizados', async () => {
    const quote = makeSummary({ id: 'q1', code: 'PED-0001' })
    const cancelled = makeSummary({ id: 'q2', code: 'PED-0002', is_cancelled: true })
    const placed = makeSummary({ id: 'p1', code: 'PED-0003', is_finalized: true })
    const { statusRequests } = installOrdersBackend([quote, cancelled, placed])

    const { unmount } = renderProductPage(<PedidosPage scope="quotes" />, productTestUser('admin', 'BR'))
    expect(await screen.findByRole('heading', { name: /Orçamentos/ })).toBeInTheDocument()
    await screen.findAllByText('PED-0001')
    // O cancelado nunca foi finalizado: continua visível em Orçamento, com status.
    expect(screen.getAllByText('PED-0002').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Cancelado').length).toBeGreaterThan(0)
    expect(screen.queryAllByText('PED-0003')).toHaveLength(0)
    expect(statusRequests).toContain('not_finalized')
    unmount()

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    expect(await screen.findByRole('heading', { name: /Pedidos/ })).toBeInTheDocument()
    await screen.findAllByText('PED-0003')
    expect(screen.queryAllByText('PED-0001')).toHaveLength(0)
    expect(screen.queryAllByText('PED-0002')).toHaveLength(0)
    expect(statusRequests).toContain('finalized')
  })

  it('o filtro de status de Orçamento não oferece Finalizados e Pedido não mostra o filtro', async () => {
    const user = userEvent.setup()
    installOrdersBackend([makeSummary()])

    const { unmount } = renderProductPage(<PedidosPage scope="quotes" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')
    await user.click(screen.getByRole('button', { name: /Filtros/ }))
    const select = screen.getByLabelText('Status')
    expect(Array.from((select as HTMLSelectElement).options).map((option) => option.text)).toEqual([
      'Todos', 'Em andamento', 'Cancelados',
    ])
    unmount()

    renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
    await screen.findByRole('heading', { name: /Pedidos/ })
    await user.click(screen.getByRole('button', { name: /Filtros/ }))
    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument()
  })

  it('ao finalizar, o orçamento sai de Orçamento, o aviso leva à aba Pedido e ele aparece lá', async () => {
    const user = userEvent.setup()
    installOrdersBackend([makeSummary()])

    renderProductPage(<Tabs />, productTestUser('admin', 'BR'), ['/pedidos'])
    await screen.findAllByText('PED-0001')

    await user.click(screen.getAllByLabelText('Finalizar orçamento PED-0001')[0])
    await user.click(screen.getByRole('button', { name: 'Finalizar Orçamento' }))

    expect(await screen.findByText('Orçamento PED-0001 finalizado e movido para a aba Pedido.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryAllByText('PED-0001')).toHaveLength(0))

    await user.click(screen.getByRole('button', { name: 'Ver em Pedido' }))
    expect(await screen.findByRole('heading', { name: /Pedidos/ })).toBeInTheDocument()
    expect((await screen.findAllByText('PED-0001')).length).toBeGreaterThan(0)
  })

  it('traduz títulos e aviso para en-GB no mercado EU', async () => {
    const user = userEvent.setup()
    const euUser = productTestUser('admin', 'EU')
    localStorage.setItem(`ilya-locale:${euUser.id}:EU`, 'en-GB')
    installOrdersBackend([makeSummary({ market_code: 'EU', currency: 'EUR' })])

    renderProductPage(<Tabs />, euUser, ['/pedidos-finalizados'])
    expect(await screen.findByRole('heading', { name: /Orders/ })).toBeInTheDocument()
    // O estado vazio existe nos dois layouts (cartões mobile e tabela).
    expect((await screen.findAllByText('No finalized orders yet.')).length).toBeGreaterThan(0)
    await user.click(screen.getAllByRole('button', { name: 'View quotes' })[0])
    expect(await screen.findByRole('heading', { name: /Quotes/ })).toBeInTheDocument()
    await screen.findAllByText('PED-0001')

    await user.click(screen.getAllByLabelText('Finalizar orçamento PED-0001')[0])
    await user.click(screen.getByRole('button', { name: 'Finalizar Orçamento' }))
    expect(await screen.findByText('Quote PED-0001 finalised and moved to the Order tab.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View in Orders' })).toBeInTheDocument()
  })

  it('mantém modal aberto e mostra erro da API ao finalizar', async () => {
    const user = userEvent.setup()
    installOrdersBackend([makeSummary()])
    server.use(
      http.post('*/orders/:id/finalize', () => HttpResponse.json({
        detail: 'Selecione todos os opcionais antes de finalizar. Pendências: MESA-1: Base',
      }, { status: 422 })),
    )

    renderProductPage(<PedidosPage scope="quotes" />, productTestUser('admin', 'BR'))
    await screen.findAllByText('PED-0001')

    await user.click(screen.getAllByLabelText('Finalizar orçamento PED-0001')[0])
    await user.click(screen.getByRole('button', { name: 'Finalizar Orçamento' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Selecione todos os opcionais antes de finalizar. Pendências: MESA-1: Base',
    )
    expect(screen.getByRole('button', { name: 'Finalizar Orçamento' })).toBeInTheDocument()
  })
})
