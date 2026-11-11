import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AuthUser } from '../contexts/AuthContext'
import { AuthContext } from '../hooks/useAuth'
import { server } from '../test/setup'
import { StockLink } from './StockLink'

const ORIGIN = 'https://ilya-estoque.vercel.app'

function userWith(patch: Partial<AuthUser>): AuthUser {
  return {
    id: 'user-1', email: 'u@example.test', username: 'u', full_name: 'Pessoa', role: 'vendedor',
    rep_id: null, order_rep_id: null, linked_id: null, is_active: true, must_change_password: false,
    max_discount: 0, can_view_dashboard: false, home_market: 'BR', active_market: 'BR',
    allowed_markets: ['BR'], can_access_stock: true, ...patch,
  }
}

function renderLink(user: AuthUser, variant: 'desktop' | 'mobile' = 'desktop') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const value = {
    user, accessToken: 't', isLoading: false,
    login: vi.fn(), logout: vi.fn(), refreshSession: vi.fn(), refreshMe: vi.fn(), switchMarket: vi.fn(),
  }
  return render(
    <AuthContext.Provider value={value}>
      <QueryClientProvider client={client}><StockLink variant={variant} /></QueryClientProvider>
    </AuthContext.Provider>,
  )
}

describe('StockLink', () => {
  afterEach(() => vi.restoreAllMocks())

  it('aparece na sessão BR com acesso e a origem vinda do servidor', async () => {
    server.use(http.get('*/stock/link', () => HttpResponse.json({ origin: ORIGIN })))
    renderLink(userWith({}))
    expect(await screen.findByRole('button', { name: 'Estoque' })).toBeVisible()
  })

  it('some sem can_access_stock, sem sequer consultar o servidor', async () => {
    let called = false
    server.use(http.get('*/stock/link', () => { called = true; return HttpResponse.json({ origin: ORIGIN }) }))
    renderLink(userWith({ can_access_stock: false }))
    await new Promise(resolve => setTimeout(resolve, 30))
    expect(screen.queryByRole('button', { name: 'Estoque' })).not.toBeInTheDocument()
    expect(called).toBe(false)
  })

  it('some na sessão do mercado EU, mesmo com a flag', async () => {
    server.use(http.get('*/stock/link', () => HttpResponse.json({ origin: ORIGIN })))
    renderLink(userWith({ active_market: 'EU', allowed_markets: ['BR', 'EU'] }))
    await new Promise(resolve => setTimeout(resolve, 30))
    expect(screen.queryByRole('button', { name: 'Estoque' })).not.toBeInTheDocument()
  })

  it('some quando o servidor responde 503 (sem chave) ou 403', async () => {
    for (const status of [503, 403]) {
      server.use(http.get('*/stock/link', () => HttpResponse.json({ detail: 'x' }, { status })))
      const { unmount } = renderLink(userWith({ id: `user-${status}` }))
      await new Promise(resolve => setTimeout(resolve, 60))
      expect(screen.queryByRole('button', { name: 'Estoque' })).not.toBeInTheDocument()
      unmount()
    }
  })

  it('o clique abre o Estoque mantendo o opener', async () => {
    server.use(http.get('*/stock/link', () => HttpResponse.json({ origin: ORIGIN })))
    const popup = { closed: false, postMessage: vi.fn() } as unknown as Window
    const open = vi.spyOn(window, 'open').mockReturnValue(popup)
    renderLink(userWith({}), 'mobile')
    await userEvent.click(await screen.findByRole('button', { name: 'Estoque' }))
    await waitFor(() => expect(open).toHaveBeenCalledWith(`${ORIGIN}/entrar-ilya`, '_blank'))
  })

  it('avisa quando o pop-up é bloqueado', async () => {
    server.use(http.get('*/stock/link', () => HttpResponse.json({ origin: ORIGIN })))
    vi.spyOn(window, 'open').mockReturnValue(null)
    renderLink(userWith({}))
    await userEvent.click(await screen.findByRole('button', { name: 'Estoque' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/bloqueou/i)
  })
})
