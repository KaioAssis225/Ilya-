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
import { cartStorageKey } from '../lib/cart'
import type { OptionalApplication, OptionalColor, Product } from '../types'
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

function detailProduct(overrides: Partial<Product>): Product {
  return { ...productFixture('BR'), description: 'Produto com acabamentos', ...overrides } as Product
}

function optional(id: string, category: string, color_name: string): OptionalColor {
  return {
    id,
    category,
    color_name,
    photo_url: `/optionals/${id}.jpg`,
    thumbnail_url: `/optionals/${id}-thumb.jpg`,
  }
}

function installDetailProduct(product: Product, availableOptionals: OptionalColor[] = []) {
  installProductHandlers({ products: [product as unknown as ReturnType<typeof productFixture>] })
  server.use(http.get('*/optionals', () => HttpResponse.json(availableOptionals)))
}

function readCart(user: AuthUser) {
  const raw = localStorage.getItem(cartStorageKey(user.id, user.active_market))
  return raw ? JSON.parse(raw) as Array<{
    line_id: string
    product_code: string
    qty: number
    discount: number
    opt_categories: Record<string, string>
    optional_choices: Array<{ application_id: string; optional_id: string }>
  }> : []
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

  it('seleciona acabamento fixo com foto e só mescla linhas com escolhas iguais', async () => {
    const user = userEvent.setup()
    const authUser = productTestUser('admin', 'BR')
    const carvalho = optional('wood-oak', 'MADEIRA', 'Carvalho')
    const nogueira = optional('wood-walnut', 'MADEIRA', 'Nogueira')
    const product = detailProduct({ optionals: [carvalho, nogueira] })
    installDetailProduct(product)
    renderProductPage(<ProdutosPage />, authUser)

    await user.click(await screen.findByText(product.description))
    const oakButton = screen.getByRole('button', { name: 'MADEIRA: Carvalho' })
    const walnutButton = screen.getByRole('button', { name: 'MADEIRA: Nogueira' })
    expect(oakButton.querySelector('img')).toHaveAttribute('src', carvalho.thumbnail_url)
    expect(walnutButton.querySelector('img')).toHaveAttribute('src', nogueira.thumbnail_url)
    expect(oakButton).toHaveAttribute('aria-pressed', 'true')

    await user.click(walnutButton)
    const addButton = screen.getByRole('button', { name: 'Adicionar ao orçamento' })
    await user.click(addButton)
    await user.click(addButton)

    let cart = readCart(authUser)
    expect(cart).toHaveLength(1)
    expect(cart[0]).toMatchObject({ qty: 2, discount: 0, opt_categories: { MADEIRA: 'Nogueira' } })
    expect(cart[0].line_id).toEqual(expect.any(String))

    await user.click(oakButton)
    await user.click(addButton)
    cart = readCart(authUser)
    expect(cart).toHaveLength(2)
    expect(cart.map(line => line.opt_categories.MADEIRA)).toEqual(['Nogueira', 'Carvalho'])
  })

  it('lista a categoria livre e omite ou grava a seleção de TECIDO', async () => {
    const user = userEvent.setup()
    const authUser = productTestUser('admin', 'BR')
    const fabrics = [
      optional('fabric-sand', 'TECIDO', 'Areia'),
      optional('fabric-blue', 'TECIDO', 'Azul'),
      optional('fabric-green', 'TECIDO', 'Verde'),
    ]
    const product = detailProduct({ all_optionals_categories: 'TECIDO', optionals: [] })
    installDetailProduct(product, fabrics)
    renderProductPage(<ProdutosPage />, authUser)

    await user.click(await screen.findByText(product.description))
    for (const fabric of fabrics) {
      expect(await screen.findByRole('button', { name: `TECIDO: ${fabric.color_name}` })).toBeVisible()
    }

    const addButton = screen.getByRole('button', { name: 'Adicionar ao orçamento' })
    await user.click(addButton)
    expect(readCart(authUser)[0].opt_categories).not.toHaveProperty('TECIDO')

    await user.click(screen.getByRole('button', { name: 'TECIDO: Azul' }))
    await user.click(addButton)
    const cart = readCart(authUser)
    expect(cart).toHaveLength(2)
    expect(cart[1].opt_categories).toMatchObject({ TECIDO: 'Azul' })
  })

  it('bloqueia aplicação obrigatória pendente e grava a escolha sem navegar', async () => {
    const user = userEvent.setup()
    const authUser = productTestUser('admin', 'BR')
    const fabric = optional('fabric-required', 'TECIDO', 'Linho Natural')
    const application: OptionalApplication = {
      id: 'seat-fabric',
      category_id: 'fabric-category',
      category_code: 'TECIDO',
      category_name: 'Tecido',
      name: 'Assento',
      name_en: 'Seat',
      required: true,
      display_order: 0,
      allow_all: false,
      allow_repeat: false,
      allowed_optionals: [fabric],
    }
    const product = detailProduct({ optional_applications: [application] })
    installDetailProduct(product)
    renderProductPage(<ProdutosPage />, authUser)

    await user.click(await screen.findByText(product.description))
    expect(await screen.findByText('1 de 1 acabamento obrigatório ainda precisa de escolha.')).toBeVisible()
    const addButton = screen.getByRole('button', { name: 'Adicionar ao orçamento' })
    await user.click(addButton)
    expect(readCart(authUser)).toEqual([])
    expect(screen.getByRole('alert')).toHaveTextContent('Escolha todos os acabamentos obrigatórios')

    await user.click(screen.getByRole('button', { name: 'Assento *: Linho Natural' }))
    await user.click(addButton)
    expect(readCart(authUser)).toHaveLength(1)
    expect(readCart(authUser)[0].optional_choices).toEqual([
      { application_id: application.id, optional_id: fabric.id },
    ])
    expect(screen.getByRole('dialog', { name: product.description })).toBeVisible()
  })

  it('abre a foto pela lupa e Escape fecha somente o zoom', async () => {
    const user = userEvent.setup()
    const authUser = productTestUser('admin', 'BR')
    const wood = optional('wood-zoom', 'MADEIRA', 'Nogueira')
    const product = detailProduct({ optionals: [wood] })
    installDetailProduct(product)
    renderProductPage(<ProdutosPage />, authUser)

    await user.click(await screen.findByText(product.description))
    await user.click(screen.getByRole('button', { name: 'Ampliar MADEIRA: Nogueira' }))
    expect(screen.getByRole('dialog', { name: 'MADEIRA: Nogueira' })).toBeVisible()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'MADEIRA: Nogueira' })).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: product.description })).toBeVisible()
  })
})
