import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type AuthUser, type UserRole } from './contexts/AuthContext'
import { AuthContext } from './hooks/useAuth'
import PrivateApp from './PrivateApp'
import { server } from './test/setup'
import { cartStorageKey } from './lib/cart'

const roles: UserRole[] = ['admin', 'vendedor', 'representante', 'cadastros', 'produtos', 'cliente', 'executivo']
const markets = ['BR', 'EU'] as const

function userFor(role: UserRole, market: 'BR' | 'EU' = 'BR'): AuthUser {
  return {
    id: `user-${role}`, email: `${role}@example.test`, username: role,
    full_name: `Pessoa ${role}`, role, rep_id: null, order_rep_id: null, linked_id: role === 'cliente' ? 'client-1' : null,
    is_active: true, must_change_password: false, max_discount: 10,
    can_view_dashboard: false, home_market: market, active_market: market, allowed_markets: [market],
  }
}

function authValue(user: AuthUser) {
  return {
    user, accessToken: 'test-token', isLoading: false,
    login: vi.fn(), logout: vi.fn(), refreshSession: vi.fn(), refreshMe: vi.fn(), switchMarket: vi.fn(),
  }
}

function renderPrivate(user: AuthUser, path: string) {
  return render(
      <AuthContext.Provider value={authValue(user)}>
        <MemoryRouter initialEntries={[path]}><PrivateApp /></MemoryRouter>
      </AuthContext.Provider>,
    )
}

const empty = () => HttpResponse.json([])
const dashboard = () => HttpResponse.json({
  start_date: '2026-01-01', end_date: '2026-01-31', granularity: 'month',
  metrics: { revenue_total: 0, revenue_finalized: 0, revenue_open: 0, revenue_cancelled: 0, orders_total: 0, orders_finalized: 0, orders_open: 0, orders_cancelled: 0 },
  chart: [], representatives: [], products: [],
})
function mapRequests() {
  server.use(
    http.get('*/notifications', empty),
    http.get('*/products', empty),
    http.get('*/products/article-categories', empty),
    http.get('*/product-types', empty),
    http.get('*/product-groups', empty),
    http.get('*/catalogs', empty),
    http.get('*/optionals', empty),
    http.get('*/optional-categories', empty),
    http.get('*/clients', empty),
    http.get('*/clients/:id', empty),
    http.get('*/representatives', empty),
    http.get('*/dashboard/overview', dashboard),
    http.post('*/products/batch', empty),
  )
}

describe('PrivateApp em DOM', () => {
  afterEach(() => vi.restoreAllMocks())

  it.each(roles.flatMap(role => markets.map(market => [role, market] as const)))(
    'abre a rota direta /produtos para %s no mercado %s', async (role, market) => {
      mapRequests()
      renderPrivate(userFor(role, market), '/produtos')
      expect(await screen.findByRole('heading', { name: 'Catálogo de produtos', level: 1 })).toBeVisible()
      expect(document.querySelector('[data-market]')).toHaveAttribute('data-market', market)
    },
  )

  it('o IVA não está no menu de cima e o antigo /iva abre a aba IVA de Cadastros (admin EU)', async () => {
    mapRequests()
    server.use(http.get('*/markets/EU/vat-rate', () => HttpResponse.json({
      market: 'EU', vat_rate: '23.00', can_edit: true, history: [],
    })))
    renderPrivate(userFor('admin', 'EU'), '/iva')

    const current = await screen.findByTestId('eu-vat-current')
    await waitFor(() => expect(current).toHaveTextContent('23%'))
    expect(screen.queryByRole('link', { name: 'IVA' })).not.toBeInTheDocument()
  })

  it.each(roles)("mostra a aba Opcionais apenas para o papel autorizado: %s", async role => {
    mapRequests()
    renderPrivate(userFor(role), '/produtos')
    await screen.findByRole('heading', { name: 'Catálogo de produtos', level: 1 })
    const links = screen.queryAllByRole('link', { name: 'Opcional' })
    const allowed = ['admin', 'vendedor', 'representante', 'cliente', 'produtos'].includes(role)
    expect(links).toHaveLength(allowed ? 2 : 0)
  })

  it.each(roles.flatMap(role => markets.map(market => [role, market] as const)))(
    'aplica o guard de /cadastros para %s em %s', async (role, market) => {
      mapRequests()
      const redirect = role === 'cliente' ? '/orcamentos' : role === 'executivo' ? '/dashboard' : null
      renderPrivate(userFor(role, market), '/cadastros')
      if (redirect === null) {
        const navigation = screen.getAllByRole('navigation', { name: 'Navegação principal' })[0]
        expect(await within(navigation).findByRole('link', { name: market === 'EU' ? 'Ficha' : 'Cadastro' })).toHaveAttribute('aria-current', 'page')
      } else {
        const expectedHeading = redirect === '/dashboard' ? 'Dashboard BI Comercial' : 'Novo Orçamento'
        expect(await screen.findByRole('heading', { name: expectedHeading, hidden: true, level: 1 })).toBeInTheDocument()
      }
    },
  )

  it('remove cache privado e carrinho BR real ao trocar para EU', async () => {
    mapRequests()
    const userBR = userFor('admin', 'BR')
    let notificationRequests = 0
    server.use(http.get('*/notifications', () => {
      notificationRequests += 1
      return HttpResponse.json([])
    }))
    localStorage.setItem(cartStorageKey(userBR.id, 'BR'), JSON.stringify([{ product_code: 'BR-SKU', qty: 3 }]))
    const { rerender } = renderPrivate(userBR, '/produtos')
    await screen.findByRole('heading', { name: 'Catálogo de produtos' })
    await waitFor(() => expect(notificationRequests).toBeGreaterThan(0))
    const requestsBeforeSwitch = notificationRequests
    expect(await screen.findAllByRole('link', { name: /3 itens/ })).toHaveLength(2)
    const nextUser = userFor('admin', 'EU')
    rerender(
      <AuthContext.Provider value={authValue(nextUser)}>
        <MemoryRouter initialEntries={['/produtos']}><PrivateApp /></MemoryRouter>
      </AuthContext.Provider>,
    )
    await waitFor(() => expect(document.querySelector('[data-market]')).toHaveAttribute('data-market', 'EU'))
    await waitFor(() => expect(notificationRequests).toBeGreaterThan(requestsBeforeSwitch))
    expect(screen.getAllByRole('link', { name: 'Novo Orçamento' })).toHaveLength(2)
    expect(JSON.parse(localStorage.getItem(cartStorageKey(userBR.id, 'BR')) ?? '[]')).toEqual([{ product_code: 'BR-SKU', qty: 3 }])
    expect(localStorage.getItem(cartStorageKey(userBR.id, 'EU'))).toBeNull()
  })

  it('isola o cache privado entre montagens com QueryClient independentes', async () => {
    mapRequests()
    const productsByCall: string[][] = []
    server.use(http.get('*/products', ({ request }) => {
      productsByCall.push([new URL(request.url).searchParams.get('q') ?? 'none'])
      return HttpResponse.json([])
    }))
    const first = renderPrivate(userFor('admin', 'BR'), '/produtos')
    expect(await screen.findByRole('heading', { name: 'Catálogo de produtos' })).toBeVisible()
    first.unmount()
    renderPrivate(userFor('admin', 'BR'), '/produtos')
    expect(await screen.findByRole('heading', { name: 'Catálogo de produtos' })).toBeVisible()
    await waitFor(() => expect(productsByCall).toHaveLength(2))
  })

  it.each(roles)('mostra a aba Pedido ao lado de Orçamento só para quem vê orçamentos: %s', async role => {
    mapRequests()
    renderPrivate(userFor(role), '/produtos')
    await screen.findByRole('heading', { name: 'Catálogo de produtos', level: 1 })
    const allowed = !['cadastros', 'executivo'].includes(role)
    expect(screen.queryAllByRole('link', { name: 'Pedido' })).toHaveLength(allowed ? 2 : 0)
    expect(screen.queryAllByRole('link', { name: 'Orçamento' })).toHaveLength(allowed ? 2 : 0)
  })

  it('rotula a aba Pedido como Order em en-GB (Portugal)', async () => {
    mapRequests()
    const user = { ...userFor('admin', 'EU'), can_manage_showrooms: true }
    localStorage.setItem(`ilya-locale:${user.id}:EU`, 'en-GB')
    renderPrivate(user, '/produtos')
    await screen.findByRole('heading', { name: 'Product catalogue', level: 1 })
    expect(screen.getAllByRole('link', { name: 'Order' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: 'Quote' })).toHaveLength(2)
    // Estoque do showroom não tem mais aba: só o botão redondo.
    expect(screen.queryAllByRole('link', { name: 'Stock' })).toHaveLength(0)
  })

  it('/pedidos-finalizados abre a lista de pedidos e marca só a aba Pedido como ativa', async () => {
    mapRequests()
    const statuses: Array<string | null> = []
    server.use(http.get('*/orders', ({ request }) => {
      statuses.push(new URL(request.url).searchParams.get('status'))
      return HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })
    }))
    renderPrivate(userFor('admin'), '/pedidos-finalizados')
    expect(await screen.findByRole('heading', { name: /Pedidos/, level: 1 })).toBeInTheDocument()
    await waitFor(() => expect(statuses).toContain('finalized'))
    const navigation = screen.getAllByRole('navigation', { name: 'Navegação principal' })[0]
    expect(within(navigation).getByRole('link', { name: 'Pedido' })).toHaveAttribute('aria-current', 'page')
    expect(within(navigation).getByRole('link', { name: 'Orçamento' })).not.toHaveAttribute('aria-current')
  })

  it('/pedidos continua abrindo a lista de orçamentos (não finalizados)', async () => {
    mapRequests()
    const statuses: Array<string | null> = []
    server.use(http.get('*/orders', ({ request }) => {
      statuses.push(new URL(request.url).searchParams.get('status'))
      return HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })
    }))
    renderPrivate(userFor('admin'), '/pedidos')
    expect(await screen.findByRole('heading', { name: /Orçamentos/, level: 1 })).toBeInTheDocument()
    await waitFor(() => expect(statuses).toContain('not_finalized'))
  })

  describe('botão flutuante de atalhos', () => {
    async function openCatalog(user: AuthUser) {
      mapRequests()
      renderPrivate(user, '/produtos')
      await screen.findByRole('heading', { name: /Cat[aá]logo|catalogue/i, level: 1 })
    }

    it('admin de Portugal com armazém e protótipos abre o menu com os 3 atalhos', async () => {
      await openCatalog({ ...userFor('admin', 'EU'), can_manage_showrooms: true, can_manage_prototypes: true })
      const button = screen.getByRole('button', { name: 'Atalhos rápidos' })
      expect(button).toHaveAttribute('aria-expanded', 'false')
      await userEvent.click(button)
      expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Dashboard', 'Armazém', 'Protótipo'])
    })

    it('só mostra Armazém e Protótipo a quem tem essas permissões em Portugal', async () => {
      await openCatalog({ ...userFor('admin', 'EU'), can_manage_prototypes: true })
      await userEvent.click(screen.getByRole('button', { name: 'Atalhos rápidos' }))
      expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Dashboard', 'Protótipo'])
    })

    it('no Brasil o botão continua indo direto ao Dashboard, sem menu', async () => {
      await openCatalog({ ...userFor('admin', 'BR'), can_manage_showrooms: true, can_manage_prototypes: true })
      expect(screen.getByRole('button', { name: 'Abrir Dashboard BI' })).not.toHaveAttribute('aria-expanded')
      expect(screen.queryByRole('button', { name: 'Atalhos rápidos' })).not.toBeInTheDocument()
    })

    it('quem só tem armazém (sem Dashboard) vê o botão levando direto ao Armazém', async () => {
      await openCatalog({ ...userFor('vendedor', 'EU'), can_manage_showrooms: true })
      expect(screen.getByRole('button', { name: 'Abrir Armazém' })).toBeInTheDocument()
    })

    it('Protótipos e Estoque não aparecem mais no menu de cima nem no de baixo (só no botão redondo)', async () => {
      await openCatalog({ ...userFor('admin', 'EU'), can_manage_showrooms: true, can_manage_prototypes: true })
      expect(screen.queryAllByRole('link', { name: 'Protótipos' })).toHaveLength(0)
      expect(screen.queryAllByRole('link', { name: 'Estoque' })).toHaveLength(0)
      await userEvent.click(screen.getByRole('button', { name: 'Atalhos rápidos' }))
      expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Dashboard', 'Armazém', 'Protótipo'])
    })

    it('as rotas continuam abrindo pela URL para quem tem permissão', async () => {
      mapRequests()
      server.use(http.get('*/showrooms*', empty), http.get('*/prototypes*', empty))
      renderPrivate({ ...userFor('vendedor', 'EU'), can_manage_prototypes: true }, '/prototipos')
      expect(await screen.findByRole('button', { name: 'Abrir Protótipos' })).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'Protótipos' })).not.toBeInTheDocument()
    })

    it('em Novo Orçamento o botão aparece para quem tem Armazém/Protótipo (único acesso) e não para quem só tem Dashboard', async () => {
      mapRequests()
      const first = renderPrivate({ ...userFor('vendedor', 'EU'), can_manage_showrooms: true }, '/orcamentos')
      expect(await screen.findByRole('button', { name: 'Abrir Armazém' })).toBeInTheDocument()
      first.unmount()
      renderPrivate({ ...userFor('admin', 'BR') }, '/orcamentos')
      await screen.findByRole('heading', { name: /Novo Orçamento/, level: 1 })
      expect(screen.queryByRole('button', { name: /Abrir Dashboard BI|Atalhos rápidos/ })).not.toBeInTheDocument()
    })

    it('sem Dashboard, armazém nem protótipos não há botão flutuante', async () => {
      await openCatalog(userFor('vendedor', 'EU'))
      expect(screen.queryByRole('button', { name: /Atalhos|Abrir (Dashboard|Armazém|Protótipos)/ })).not.toBeInTheDocument()
    })
  })

  it('rejeita request sem handler MSW usando URL absoluta', async () => {
    await expect(fetch('http://localhost/api/v1/unmapped-test')).rejects.toThrow()
  })
})
