import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { AuthProvider, type AuthUser } from '../contexts/AuthContext'
import { AuthContext } from '../hooks/useAuth'
import PrivateApp from '../PrivateApp'
import ProdutosPage from './ProdutosPage'
import { server } from '../test/setup'
import {
  installProductHandlers,
  productFixture,
  productTestUser,
  renderProductPage,
} from '../test/productTestUtils'

function renderPrivate(user: AuthUser) {
  const auth = {
    user, accessToken: 'p05-test-token', isLoading: false,
    login: vi.fn(), logout: vi.fn(), refreshSession: vi.fn(), refreshMe: vi.fn(), switchMarket: vi.fn(),
  }
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={['/produtos']}><PrivateApp /></MemoryRouter>
    </AuthContext.Provider>,
  )
}

const empty = () => HttpResponse.json([])
function privateAppHandlers(products: (requestCount: number) => ReturnType<typeof productFixture>[]) {
  let requestCount = 0
  installProductHandlers()
  server.use(
    http.get('*/products', () => {
      const current = requestCount++
      const items = products(current)
      return HttpResponse.json(items, {
        headers: {
          'X-Total-Count': String(items.length),
          'X-Has-More': 'false',
          'X-Page-Size': String(items.length),
        },
      })
    }),
    http.get('*/notifications', empty),
    http.post('*/products/batch', empty),
  )
  return () => requestCount
}

describe('ProdutosPage de catálogo em DOM', () => {
  it('REG-CAT-01: mercado BR mostra apenas produtos BR fornecidos pelo MSW', async () => {
    privateAppHandlers(() => [productFixture('BR')])
    renderPrivate(productTestUser('admin', 'BR'))

    expect(await screen.findByText('P05-BR-SKU')).toBeVisible()
    expect(screen.queryByText('P05-EU-SKU')).not.toBeInTheDocument()
  })

  it('REG-CAT-01: troca BR→EU pela sessão real atualiza token, mercado e catálogo', async () => {
    const user = userEvent.setup()
    const users = {
      BR: { ...productTestUser('admin', 'BR'), allowed_markets: ['BR', 'EU'] as Array<'BR' | 'EU'> },
      EU: { ...productTestUser('admin', 'EU'), allowed_markets: ['BR', 'EU'] as Array<'BR' | 'EU'> },
    }
    const productRequests: Array<{ token: string | null; market: 'BR' | 'EU' }> = []
    server.use(
      http.post('*/auth/refresh', () => HttpResponse.json({ access_token: 'p05-br-token' })),
      http.get('*/auth/me', ({ request }) => {
        const token = request.headers.get('authorization')
        if (token === 'Bearer p05-br-token') return HttpResponse.json(users.BR)
        if (token === 'Bearer p05-eu-token') return HttpResponse.json(users.EU)
        return HttpResponse.json({ detail: 'Token inesperado' }, { status: 401 })
      }),
      http.post('*/auth/switch-market', async ({ request }) => {
        const body = await request.json() as { market: string }
        if (request.headers.get('authorization') !== 'Bearer p05-br-token' || body.market !== 'EU') {
          return HttpResponse.json({ detail: 'Troca inesperada' }, { status: 403 })
        }
        return HttpResponse.json({ access_token: 'p05-eu-token' })
      }),
      http.get('*/products', ({ request }) => {
        const token = request.headers.get('authorization')
        const market = token === 'Bearer p05-br-token' ? 'BR' : 'EU'
        productRequests.push({ token, market })
        const product = productFixture(market)
        return HttpResponse.json([product], {
          headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
        })
      }),
      http.get('*/notifications', empty),
      http.get('*/product-types', empty),
      http.get('*/product-groups', empty),
      http.get('*/catalogs', empty),
      http.get('*/optionals', empty),
      http.get('*/optional-categories', empty),
    )

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/produtos']}><PrivateApp /></MemoryRouter>
      </AuthProvider>,
    )
    expect(await screen.findByText('P05-BR-SKU')).toBeVisible()
    await waitFor(() => expect(productRequests).toContainEqual({ token: 'Bearer p05-br-token', market: 'BR' }))

    await user.click(screen.getByRole('button', { name: 'Ambiente Brasil. Trocar ambiente' }))
    await user.click(screen.getByRole('menuitemradio', { name: /Portugal/ }))

    expect(await screen.findByText('P05-EU-SKU')).toBeVisible()
    expect(screen.queryByText('P05-BR-SKU')).not.toBeInTheDocument()
    expect(document.querySelector('[data-market]')).toHaveAttribute('data-market', 'EU')
    await waitFor(() => expect(productRequests).toContainEqual({ token: 'Bearer p05-eu-token', market: 'EU' }))
  })

  it('REG-PROD-02: catálogo EU apresenta o preço Arquiteto selecionado', async () => {
    const user = userEvent.setup()
    installProductHandlers({ products: [productFixture('EU')] })
    renderProductPage(<ProdutosPage />, productTestUser('admin', 'EU'))

    const architect = await screen.findByRole('button', { name: 'Arquiteto' })
    await user.click(architect)
    expect(architect).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByText(/80,00/)).toBeVisible()
  })

  it('REG-CAT-01: “Todos os Catálogos” remove o filtro e renderiza mercados distintos', async () => {
    const user = userEvent.setup()
    const firstCatalog = { id: 'p05-catalog-1', name: 'Catálogo Primeiro' }
    const secondCatalog = { id: 'p05-catalog-2', name: 'Catálogo Segundo' }
    const first = productFixture('EU', {
      id: 'p05-first-catalog-product', product_code: 'P05-FILTER-ONE',
      catalog_id: firstCatalog.id, catalog: firstCatalog,
    })
    const second = productFixture('EU', {
      id: 'p05-second-catalog-product', product_code: 'P05-FILTER-TWO',
      catalog_id: secondCatalog.id, catalog: secondCatalog,
    })
    const requests: Array<{ catalogId: string | null; query: string | null }> = []
    installProductHandlers({ products: [first, second], catalogs: [firstCatalog, secondCatalog] })
    server.use(http.get('*/products', ({ request }) => {
      const params = new URL(request.url).searchParams
      const catalogId = params.get('catalog_id')
      requests.push({ catalogId, query: params.get('q') })
      const items = catalogId === firstCatalog.id ? [first]
        : catalogId === secondCatalog.id ? [second]
          : [first, second]
      return HttpResponse.json(items, {
        headers: { 'X-Total-Count': String(items.length), 'X-Has-More': 'false', 'X-Page-Size': String(items.length) },
      })
    }))
    renderProductPage(<ProdutosPage />, productTestUser('admin', 'EU'))

    await screen.findByRole('option', { name: firstCatalog.name })
    const catalogFilter = screen.getAllByRole('combobox')[0]
    await user.selectOptions(catalogFilter, firstCatalog.id)
    expect(await screen.findByText('P05-FILTER-ONE')).toBeVisible()
    expect(screen.queryByText('P05-FILTER-TWO')).not.toBeInTheDocument()
    await waitFor(() => expect(requests).toContainEqual({ catalogId: firstCatalog.id, query: null }))

    await user.selectOptions(catalogFilter, '')
    await user.type(screen.getByRole('textbox', { name: 'Pesquisar produtos' }), 'P05-FILTER')
    expect(await screen.findByText('P05-FILTER-ONE')).toBeVisible()
    expect(await screen.findByText('P05-FILTER-TWO')).toBeVisible()
    await waitFor(() => expect(requests).toContainEqual({ catalogId: null, query: 'P05-FILTER' }))
  })

  it('REG-PROD-02: locale en-GB solicita e mostra o nome inglês do produto', async () => {
    const product = productFixture('EU', { description: 'English table', description_en: 'English table' })
    const requests: string[] = []
    installProductHandlers({ products: [product] })
    server.use(http.get('*/products', ({ request }) => {
      requests.push(new URL(request.url).searchParams.get('language') ?? '')
      return HttpResponse.json([product], {
        headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
      })
    }))
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(`ilya-locale:${user.id}:EU`, 'en-GB')
    renderProductPage(<ProdutosPage />, user)

    expect(await screen.findByRole('heading', { name: 'Product catalogue' })).toBeVisible()
    expect(await screen.findByText('English table')).toBeVisible()
    await waitFor(() => expect(requests).toContain('en-GB'))
  })
})