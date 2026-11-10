import { beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import DashboardPage from './DashboardPage'

const baseMetrics = {
  revenue_total: 0, revenue_finalized: 0, revenue_open: 0, revenue_cancelled: 0,
  orders_total: 0, orders_finalized: 0, orders_open: 0, orders_cancelled: 0,
  revenue_production: 0, revenue_delivered: 0, orders_production: 0, orders_delivered: 0,
}

function installOverview() {
  const kinds: Array<string | null> = []
  server.use(
    http.get('*/dashboard/overview', ({ request }) => {
      const kind = new URL(request.url).searchParams.get('kind')
      kinds.push(kind)
      const metrics = kind === 'orders'
        ? { ...baseMetrics, orders_total: 7, orders_production: 5, orders_delivered: 2 }
        : { ...baseMetrics, orders_total: 3, orders_open: 2, orders_cancelled: 1 }
      return HttpResponse.json({
        kind, start_date: '2026-01-01', end_date: '2026-01-31', granularity: 'day',
        metrics, chart: [], representatives: [], products: [],
      })
    }),
    http.get('*/representatives', () => HttpResponse.json([])),
  )
  return kinds
}

const tab = (name: string) => screen.findByRole('tab', { name, hidden: true })

describe('Dashboard: abas Orçamentos e Pedidos', () => {
  beforeEach(() => localStorage.clear())

  it('abre em Orçamentos e mostra só os indicadores de orçamento', async () => {
    const kinds = installOverview()
    renderProductPage(<DashboardPage />, productTestUser('admin'), ['/dashboard'])

    expect(await tab('Orçamentos')).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('Orçamentos em aberto', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.queryByText('Pedidos em produção')).not.toBeInTheDocument()
    expect(screen.queryByText('Orçamentos finalizados')).not.toBeInTheDocument()
    expect(kinds.every(kind => kind === 'quotes')).toBe(true)
  })

  it('o botão Pedidos troca os indicadores e consulta o servidor com kind=orders', async () => {
    const kinds = installOverview()
    const user = userEvent.setup()
    renderProductPage(<DashboardPage />, productTestUser('admin'), ['/dashboard'])

    await user.click(await tab('Pedidos'))

    expect(await screen.findByText('Pedidos em produção')).toBeInTheDocument()
    expect(screen.getByText('Pedidos entregues')).toBeInTheDocument()
    expect(screen.queryByText('Orçamentos em aberto')).not.toBeInTheDocument()
    expect(screen.queryByText('Orçamentos cancelados')).not.toBeInTheDocument()
    await waitFor(() => expect(kinds).toContain('orders'))
    const panel = screen.getByRole('tabpanel', { name: 'Pedidos', hidden: true })
    await waitFor(() => expect(within(panel).getByText('7')).toBeInTheDocument())
    expect(await tab('Pedidos')).toHaveAttribute('aria-selected', 'true')
  })

  it('a aba na URL (?aba=pedidos) abre direto em Pedidos', async () => {
    const kinds = installOverview()
    renderProductPage(<DashboardPage />, productTestUser('admin'), ['/dashboard?aba=pedidos'])

    expect(await tab('Pedidos')).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('Pedidos total')).toBeInTheDocument()
    expect(kinds.every(kind => kind === 'orders')).toBe(true)
  })

  it('lembra a última aba escolhida na próxima visita', async () => {
    installOverview()
    const user = userEvent.setup()
    const first = renderProductPage(<DashboardPage />, productTestUser('admin'), ['/dashboard'])
    await user.click(await tab('Pedidos'))
    await screen.findByText('Pedidos em produção')
    first.unmount()

    renderProductPage(<DashboardPage />, productTestUser('admin'), ['/dashboard'])

    expect(await tab('Pedidos')).toHaveAttribute('aria-selected', 'true')
  })
})

function installClients() {
  const requests: URLSearchParams[] = []
  server.use(
    http.get('*/dashboard/clients', ({ request }) => {
      requests.push(new URL(request.url).searchParams)
      return HttpResponse.json({
        total: 2, contacted: 1, not_contacted: 1, contacted_pct: 50, filtered_total: 2,
        items: [
          { id: 'c1', name: 'Alfa Pendente', contact_name: 'Ana', phone: '+351 911', email: null, city: 'Lisboa', country: 'Portugal', rep_id: null, rep_name: 'Rep Alfa', contacted: false },
          { id: 'c2', name: 'Beta Contactado', contact_name: null, phone: '+351 922', email: null, city: 'Porto', country: 'Portugal', rep_id: null, rep_name: null, contacted: true },
        ],
      })
    }),
  )
  return requests
}

describe('Dashboard: aba Clientes dentro do BI (Portugal)', () => {
  beforeEach(() => localStorage.clear())

  it('Portugal tem o botão Clientes, que mostra contactados e não contactados no BI', async () => {
    installOverview()
    const requests = installClients()
    const user = userEvent.setup()
    renderProductPage(<DashboardPage />, productTestUser('admin', 'EU'), ['/dashboard'])

    await user.click(await tab('Clientes'))

    expect((await screen.findAllByText('Alfa Pendente')).length).toBeGreaterThan(0)
    expect(screen.getByTestId('kpi-contacted')).toHaveTextContent('1')
    expect(screen.getByTestId('kpi-pct')).toHaveTextContent('50%')
    expect(requests.length).toBeGreaterThan(0)
    // Sem indicadores de orçamento/pedido nem filtros de período nesta aba.
    expect(screen.queryByText('Orçamentos em aberto')).not.toBeInTheDocument()
    expect(screen.queryByText('Data inicial')).not.toBeInTheDocument()
    expect(await tab('Clientes')).toHaveAttribute('aria-selected', 'true')
  })

  it('a aba na URL (?aba=clientes) abre direto em Clientes e não pede o overview', async () => {
    const kinds = installOverview()
    installClients()
    renderProductPage(<DashboardPage />, productTestUser('admin', 'EU'), ['/dashboard?aba=clientes'])

    expect(await tab('Clientes')).toHaveAttribute('aria-selected', 'true')
    expect((await screen.findAllByText('Beta Contactado')).length).toBeGreaterThan(0)
    expect(kinds).toHaveLength(0)
  })

  it('lembra a aba Clientes na próxima visita', async () => {
    installOverview()
    installClients()
    const user = userEvent.setup()
    const first = renderProductPage(<DashboardPage />, productTestUser('admin', 'EU'), ['/dashboard'])
    await user.click(await tab('Clientes'))
    await screen.findAllByText('Alfa Pendente')
    first.unmount()

    renderProductPage(<DashboardPage />, productTestUser('admin', 'EU'), ['/dashboard'])

    expect(await tab('Clientes')).toHaveAttribute('aria-selected', 'true')
  })

  it('Brasil não tem o botão Clientes, nem pela URL', async () => {
    const kinds = installOverview()
    renderProductPage(<DashboardPage />, productTestUser('admin', 'BR'), ['/dashboard?aba=clientes'])

    expect(await tab('Orçamentos')).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('tab', { name: 'Clientes', hidden: true })).not.toBeInTheDocument()
    await waitFor(() => expect(kinds).toContain('quotes'))
  })

  it('executivo em Portugal não vê o botão Clientes', async () => {
    installOverview()
    renderProductPage(<DashboardPage />, productTestUser('executivo', 'EU'), ['/dashboard'])

    expect(await tab('Orçamentos')).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Clientes', hidden: true })).not.toBeInTheDocument()
  })
})
