import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../hooks/useAuth'
import type { AuthContextValue, AuthUser } from '../contexts/AuthContext'
import { LocaleProvider } from '../contexts/LocaleContext'
import { useLocale } from '../hooks/useLocale'
import { server } from '../test/setup'
import OpcionaisPage from './OpcionaisPage'

const user: AuthUser = {
  id: 'user-1', email: 'user@example.test', username: 'user', full_name: 'Pessoa Teste',
  role: 'representante', rep_id: 'rep-1', linked_id: null, is_active: true,
  must_change_password: false, max_discount: 10, can_view_dashboard: false,
  home_market: 'BR', active_market: 'BR', allowed_markets: ['BR'],
}

const auth: AuthContextValue = {
  user,
  accessToken: 'token',
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
  refreshMe: vi.fn(),
  switchMarket: vi.fn(),
}

function LanguageControls() {
  const { setLocale } = useLocale()
  return <><button onClick={() => setLocale('pt-PT')}>PT</button><button onClick={() => setLocale('en-GB')}>EN</button></>
}

function renderPage(activeUser: AuthUser = user) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <AuthContext.Provider value={{ ...auth, user: activeUser }}>
      <LocaleProvider>
        <LanguageControls />
        <QueryClientProvider client={client}>
          <OpcionaisPage />
        </QueryClientProvider>
      </LocaleProvider>
    </AuthContext.Provider>,
  )
}

describe('OpcionaisPage', () => {
  it('traduz nomes, categorias, busca, bancada e zoom no EN e volta aos originais no PT', async () => {
    const original = { id: 'opt-branco', category: 'MADEIRA', color_name: 'Branco', photo_url: '/branco.jpg' }
    server.use(
      http.get('*/optional-categories', () => HttpResponse.json([
        { id: 'cat-madeira', code: 'MADEIRA', name: 'Madeira', display_order: 1 },
      ])),
      http.get('*/optionals', () => HttpResponse.json([original])),
    )
    localStorage.removeItem(`ilya-locale:${user.id}:EU`)
    renderPage({ ...user, active_market: 'EU', allowed_markets: ['EU'] })
    expect(await screen.findByRole('heading', { name: 'Branco', level: 3 })).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'EN' }))
    expect(screen.getByRole('heading', { name: 'Wood', level: 2 })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'White', level: 3 })).toBeVisible()
    const search = screen.getByRole('searchbox', { name: 'Search finishes by name' })
    await userEvent.type(search, 'white')
    expect(screen.getByRole('heading', { name: 'White', level: 3 })).toBeVisible()
    await userEvent.clear(search)
    await userEvent.type(search, 'branco')
    expect(screen.getByRole('heading', { name: 'White', level: 3 })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Place side by side' }))
    expect(screen.getByRole('button', { name: 'Remove White' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Enlarge White' }))
    expect(screen.getByRole('dialog', { name: 'Wood: White' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    await userEvent.click(screen.getByRole('button', { name: 'PT' }))
    expect(screen.getByRole('heading', { name: 'Madeira', level: 2 })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Branco', level: 3 })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Remover Branco' })).toBeVisible()
    expect(original.color_name).toBe('Branco')
  })

  it('ordena categorias do cadastro, busca sem acento e mostra o estado sem foto', async () => {
    server.use(
      http.get('*/optional-categories', () => HttpResponse.json([
        { id: 'cat-madeira', code: 'madeira', name: 'Madeira', display_order: 2 },
        { id: 'cat-aluminio', code: 'aluminio', name: 'Alumínio', display_order: 1 },
        { id: 'cat-vazio', code: 'vazio', name: 'Categoria vazia', display_order: 3 },
      ])),
      http.get('*/optionals', () => HttpResponse.json([
        {
          id: 'opt-agata', category: 'aluminio', color_name: 'Ágata', photo_url: '/agata.jpg', thumbnail_url: '/agata-thumb.jpg',
          photo_variants: null,
        },
        {
          id: 'opt-neve', category: 'madeira', color_name: 'Neve', photo_url: null, thumbnail_url: null,
          photo_variants: null,
        },
        {
          id: 'opt-orphan', category: 'legado', color_name: 'Legado', photo_url: '/legado.jpg', thumbnail_url: null,
          photo_variants: null,
        },
      ])),
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Opcionais', level: 1 })).toBeVisible()
    expect((await screen.findAllByRole('heading', { level: 2 })).map(heading => heading.textContent)).toEqual([
      'Alumínio', 'Madeira', 'Categoria vazia', 'Outros',
    ])
    expect(screen.getByText('Nenhum opcional nesta categoria.')).toBeVisible()
    expect(screen.getByRole('img', { name: 'Imagem em atualização: Neve' })).toBeVisible()
    expect(screen.getAllByRole('button', { name: 'Colocar lado a lado' }).some(button => button.hasAttribute('disabled'))).toBe(true)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar opcionais por nome' }), 'agata')
    expect(screen.getByText('Ágata')).toBeVisible()
    expect(screen.queryByText('Neve')).not.toBeInTheDocument()
  })
})
