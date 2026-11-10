import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router'
import { AuthContext } from '../hooks/useAuth'
import type { AuthUser, UserRole } from '../contexts/AuthContext'
import PrivateApp from '../PrivateApp'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import ClientesDashboardContent from '../components/ClientesDashboardContent'

const ROWS = [
  { id: 'c1', name: 'Alfa Pendente', contact_name: 'Ana', phone: '+351 911', email: 'ana@alfa.pt', city: 'Lisboa', country: 'Portugal', rep_id: 'r1', rep_name: 'Rep Alfa', contacted: false },
  { id: 'c2', name: 'Beta Contactado', contact_name: null, phone: '+351 922', email: null, city: 'Porto', country: 'Portugal', rep_id: null, rep_name: null, contacted: true },
]

function installClients() {
  const requests: URLSearchParams[] = []
  server.use(
    http.get('*/dashboard/clients', ({ request }) => {
      const params = new URL(request.url).searchParams
      requests.push(params)
      const filter = params.get('contacted')
      const q = (params.get('q') ?? '').toLowerCase()
      const items = ROWS.filter(row => (
        (filter !== 'yes' || row.contacted) && (filter !== 'no' || !row.contacted)
        && (!q || row.name.toLowerCase().includes(q))
      ))
      return HttpResponse.json({ total: 2, contacted: 1, not_contacted: 1, contacted_pct: 50, filtered_total: items.length, items })
    }),
  )
  return requests
}

describe('Dashboard de Clientes', () => {
  beforeEach(() => localStorage.clear())

  it('mostra indicadores do servidor e a lista com o estado de contacto', async () => {
    installClients()
    renderProductPage(<ClientesDashboardContent />, productTestUser('admin', 'EU'), ['/clientes'])

    expect((await screen.findAllByText('Alfa Pendente')).length).toBeGreaterThan(0)
    expect(screen.getByTestId('kpi-total')).toHaveTextContent('2')
    expect(screen.getByTestId('kpi-contacted')).toHaveTextContent('1')
    expect(screen.getByTestId('kpi-pending')).toHaveTextContent('1')
    expect(screen.getByTestId('kpi-pct')).toHaveTextContent('50%')
    const rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('Não contactado')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Contactado')).toBeInTheDocument()
    expect(within(rows[1]).getByText(/Ana · \+351 911 · ana@alfa\.pt/)).toBeInTheDocument()
    expect(within(rows[2]).getByText('Sem representante')).toBeInTheDocument()
  })

  it('o filtro Não contactados e a busca são enviados ao servidor', async () => {
    const requests = installClients()
    const user = userEvent.setup()
    renderProductPage(<ClientesDashboardContent />, productTestUser('admin', 'EU'), ['/clientes'])
    await screen.findAllByText('Alfa Pendente')

    await user.click(screen.getByRole('button', { name: 'Não contactados' }))
    await waitFor(() => expect(screen.queryAllByText('Beta Contactado')).toHaveLength(0))
    expect(requests.some(p => p.get('contacted') === 'no')).toBe(true)

    await user.click(screen.getByRole('button', { name: 'Todos' }))
    await user.type(screen.getByRole('searchbox'), 'beta')
    await waitFor(() => expect(requests.some(p => p.get('q') === 'beta')).toBe(true))
    expect((await screen.findAllByText('Beta Contactado')).length).toBeGreaterThan(0)
    expect(screen.queryAllByText('Alfa Pendente')).toHaveLength(0)
  })

  it('mostra erro quando o servidor nega ou falha', async () => {
    server.use(http.get('*/dashboard/clients', () => new HttpResponse(null, { status: 500 })))
    renderProductPage(<ClientesDashboardContent />, productTestUser('representante', 'EU'), ['/clientes'])

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível carregar os clientes.')
  })
})

describe('Dashboard de Clientes: só dentro do BI', () => {
  beforeEach(() => localStorage.clear())

  function userFor(role: UserRole, market: 'BR' | 'EU', canViewDashboard = false): AuthUser {
    return {
      ...productTestUser(role, market),
      linked_id: role === 'cliente' ? 'client-1' : null,
      can_view_dashboard: canViewDashboard,
    }
  }

  function renderApp(user: AuthUser, path: string) {
    server.use(
      http.get('*/notifications', () => HttpResponse.json([])),
      http.get('*/products', () => HttpResponse.json([])),
      http.get('*/products/article-categories', () => HttpResponse.json([])),
      http.get('*/products/filter-options', () => HttpResponse.json({})),
      http.get('*/product-types', () => HttpResponse.json([])),
      http.get('*/product-groups', () => HttpResponse.json([])),
      http.get('*/catalogs', () => HttpResponse.json([])),
      http.get('*/optionals', () => HttpResponse.json([])),
      http.get('*/optional-categories', () => HttpResponse.json([])),
      http.get('*/clients', () => HttpResponse.json([])),
      http.get('*/clients/:id', () => HttpResponse.json([])),
      http.get('*/representatives', () => HttpResponse.json([])),
      http.post('*/products/batch', () => HttpResponse.json([])),
      http.get('*/dashboard/overview', () => HttpResponse.json({
        kind: 'quotes', start_date: '2026-01-01', end_date: '2026-01-31', granularity: 'month',
        metrics: {}, chart: [], representatives: [], products: [],
      })),
    )
    // Por último: o glob '*/clients' acima também casaria com /dashboard/clients.
    installClients()
    const auth = {
      user, accessToken: 't', isLoading: false,
      login: vi.fn(), logout: vi.fn(), refreshSession: vi.fn(), refreshMe: vi.fn(), switchMarket: vi.fn(),
    }
    return render(
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[path]}><PrivateApp /></MemoryRouter>
      </AuthContext.Provider>,
    )
  }

  it.each(['admin', 'vendedor', 'representante', 'cadastros', 'produtos'] as UserRole[])(
    'Portugal: %s não tem "Clientes" no menu normal', async role => {
      renderApp(userFor(role, 'EU'), '/produtos')

      await screen.findByRole('heading', { name: 'Catálogo de produtos', level: 1 })
      expect(screen.queryByRole('link', { name: 'Clientes' })).not.toBeInTheDocument()
    },
  )

  it('/clientes (link salvo) leva ao botão Clientes dentro do BI', async () => {
    renderApp(userFor('admin', 'EU'), '/clientes')

    expect(await screen.findByRole('tab', { name: 'Clientes', hidden: true })).toHaveAttribute('aria-selected', 'true')
    expect((await screen.findAllByText('Alfa Pendente')).length).toBeGreaterThan(0)
  })

  it('/clientes sem acesso ao BI cai na tela inicial do usuário', async () => {
    renderApp(userFor('representante', 'EU'), '/clientes')

    expect(await screen.findByRole('heading', { name: 'Novo Orçamento', hidden: true, level: 1 })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Clientes', hidden: true })).not.toBeInTheDocument()
  })

  it('/clientes no Brasil abre o BI em Orçamentos, sem aba Clientes', async () => {
    renderApp(userFor('admin', 'BR'), '/clientes')

    expect(await screen.findByRole('tab', { name: 'Orçamentos', hidden: true })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('tab', { name: 'Clientes', hidden: true })).not.toBeInTheDocument()
  })
})
