import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { http, HttpResponse } from 'msw'
import { vi } from 'vitest'
import { type AuthUser, type UserRole } from '../contexts/AuthContext'
import { AuthContext } from '../hooks/useAuth'
import { LocaleProvider } from '../contexts/LocaleContext'
import { server } from './setup'

export function productTestUser(role: UserRole = 'admin', market: 'BR' | 'EU' = 'BR'): AuthUser {
  return {
    id: `p05-${role}-${market}`, email: `${role}@example.test`, username: role,
    full_name: `Pessoa ${role}`, role, rep_id: null, order_rep_id: null, linked_id: null,
    is_active: true, must_change_password: false, max_discount: 10,
    can_view_dashboard: false, home_market: market, active_market: market,
    allowed_markets: [market],
  }
}

export function renderProductPage(node: ReactNode, user: AuthUser, initialEntries: string[] = ['/']) {
  localStorage.removeItem('cadastros_ui_state')
  if (user.active_market === 'EU' && localStorage.getItem(`ilya-locale:${user.id}:EU`) == null) {
    localStorage.setItem(`ilya-locale:${user.id}:EU`, 'pt-PT')
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
  const auth = {
    user, accessToken: 'p05-test-token', isLoading: false,
    login: vi.fn(), logout: vi.fn(), refreshSession: vi.fn(), refreshMe: vi.fn(), switchMarket: vi.fn(),
  }
  return render(
    <AuthContext.Provider value={auth}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <LocaleProvider>{node}</LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
}

export interface ProductFixture {
  id: string
  product_code: string
  description: string
  ean: string | null
  summary: string | null
  article_category_path: string | null
  description_pt_pt: string | null
  description_en: string | null
  type: string
  catalog_id: string | null
  catalog: { id: string; name: string } | null
  area_limit_enabled: boolean
  max_area_m2: number | string | null
  is_circular: boolean
  is_set: boolean
  altura: number
  largura: number
  profundidade: number
  price: number
  price_lojista: number
  price_corporativo: number
  market_code: 'BR' | 'EU'
  currency: 'BRL' | 'EUR'
  market_prices: Record<string, number>
  observacao: string | null
  all_optionals_categories: string | null
  optionals: never[]
  optional_applications: never[]
  set_items: never[]
  components: never[]
  photo_url: string | null
  thumbnail_url: string | null
  created_at: string
  updated_at: string
}

export function productFixture(
  market: 'BR' | 'EU',
  overrides: Partial<ProductFixture> = {},
): ProductFixture {
  const now = '2026-10-19T12:00:00Z'
  return {
    id: `p05-${market.toLowerCase()}-product`, product_code: `P05-${market}-SKU`,
    description: market === 'EU' ? 'Mesa PT' : 'Mesa BR', ean: null, summary: null,
    article_category_path: null,
    description_pt_pt: market === 'EU' ? 'Mesa PT' : null,
    description_en: market === 'EU' ? 'Table EN' : null,
    type: 'Outro', catalog_id: null, catalog: null,
    area_limit_enabled: false, max_area_m2: null,
    is_circular: false, is_set: false, altura: 0, largura: 1, profundidade: 1,
    price: 100, price_lojista: 100, price_corporativo: 90,
    market_code: market, currency: market === 'EU' ? 'EUR' : 'BRL',
    market_prices: market === 'EU'
      ? { lojista: 100, corporativo: 90, pvp: 120, arquiteto: 80 }
      : { lojista: 100, corporativo: 90 },
    observacao: null, all_optionals_categories: null, optionals: [],
    optional_applications: [], set_items: [], components: [],
    photo_url: null, thumbnail_url: null, created_at: now, updated_at: now,
    ...overrides,
  }
}

export function installProductHandlers(options: {
  products?: ProductFixture[]
  catalogs?: Array<{ id: string; name: string }>
  onCreate?: (payload: Record<string, unknown>) => Response | Promise<Response>
  onPatch?: (id: string, payload: Record<string, unknown>) => Response | Promise<Response>
} = {}) {
  const products = options.products ?? []
  server.use(
    http.get('*/products', () => HttpResponse.json(products, {
      headers: { 'X-Total-Count': String(products.length), 'X-Has-More': 'false', 'X-Page-Size': String(products.length) },
    })),
    http.get('*/products/article-categories', () => HttpResponse.json([])),
    http.get('*/catalogs', () => HttpResponse.json(options.catalogs ?? [])),
    http.get('*/product-types', () => HttpResponse.json([])),
    http.get('*/product-groups', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/clients', () => HttpResponse.json([])),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.post('*/products', async ({ request }) => {
      const payload = await request.json() as Record<string, unknown>
      return options.onCreate
        ? options.onCreate(payload)
        : HttpResponse.json({ ...productFixture('EU'), ...payload }, { status: 201 })
    }),
    http.patch('*/products/:id', async ({ params, request }) => {
      const payload = await request.json() as Record<string, unknown>
      return options.onPatch
        ? options.onPatch(String(params.id), payload)
        : HttpResponse.json({ ...productFixture('EU'), ...payload })
    }),
  )
}
