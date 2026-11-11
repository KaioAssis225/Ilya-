import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { vi, describe, expect, it } from 'vitest'
import { PlatformAuthContext, type PlatformAuthValue } from '../contexts/platformAuth'
import type { UserMarketAccess, UserRead } from '../hooks/useUsers'
import { server } from '../test/setup'
import PlatformPage from './PlatformPage'

// Os painéis abaixo têm as próprias chamadas; não fazem parte do que se testa aqui.
vi.mock('../components/RetentionGovernancePanel', () => ({ default: () => null }))
vi.mock('../components/IncidentRegistryPanel', () => ({ default: () => null }))
vi.mock('../components/MoloniIntegrationPanel', () => ({ default: () => null }))

function access(patch: Partial<UserMarketAccess> = {}): UserMarketAccess {
  return {
    market_code: 'BR', role: 'vendedor', status: 'active', linked_client_id: null,
    rep_id: null, order_rep_id: null, can_view_dashboard: false, can_approve_tax: false, ...patch,
  }
}

function identity(id: string, name: string, accesses: UserMarketAccess[], hasStock = false): UserRead {
  return {
    id, email: `${id}@example.test`, username: id, full_name: name, role: accesses[0]?.role ?? 'vendedor',
    rep_id: null, order_rep_id: null, is_active: true, can_view_dashboard: false,
    has_stock_access: hasStock, home_market: accesses[0]?.market_code ?? 'BR',
    allowed_markets: accesses.map(item => item.market_code), market_accesses: accesses,
  }
}

const ROWS: UserRead[] = [
  identity('u-br', 'Bia Brasil', [access()], true),
  identity('u-eu', 'Eva Europa', [access({ market_code: 'EU' })]),
  identity('u-pend', 'Paulo Pendente', [access({ status: 'pending' })]),
  identity('u-cli', 'Clara Cliente', [access({ role: 'cliente' })]),
]

const platformAuth: PlatformAuthValue = {
  user: { id: 'plat-1', email: 'adm@example.test', full_name: 'Admin Plataforma', scope: 'platform', capabilities: ['platform_admin'] },
  accessToken: 't', isLoading: false,
  login: vi.fn(), logout: vi.fn(), refreshSession: vi.fn(),
}

function install(patches: Array<Record<string, unknown>> = []) {
  server.use(
    http.get('*/markets', () => HttpResponse.json([{ code: 'BR', name: 'Brasil', currency: 'BRL', is_enabled: true }])),
    http.get('*/users', () => HttpResponse.json(ROWS)),
    http.get('*/integrations/outbox/status', () => HttpResponse.json({ total: 0, counts: {} })),
    http.get('*/users/:id/platform-permissions', () => HttpResponse.json({ capabilities: [] })),
    http.patch('*/users/:id', async ({ request, params }) => {
      patches.push(await request.json() as Record<string, unknown>)
      return HttpResponse.json(ROWS.find(row => row.id === params.id))
    }),
  )
}

function renderPlatform() {
  return render(
    <PlatformAuthContext.Provider value={platformAuth}><PlatformPage /></PlatformAuthContext.Provider>,
  )
}

async function openEditor(name: string) {
  const row = (await screen.findByText(name)).closest('tr') as HTMLElement
  await userEvent.click(within(row).getByTitle('Editar'))
  return screen.findByRole('heading', { name: 'Editar identidade' })
}

describe('PlatformPage — Acesso ao Estoque', () => {
  it('mostra o selo Estoque só para quem tem o acesso', async () => {
    install()
    renderPlatform()
    const withAccess = (await screen.findByText('Bia Brasil')).closest('tr') as HTMLElement
    expect(within(withAccess).getByText('Estoque')).toBeInTheDocument()
    const without = screen.getByText('Eva Europa').closest('tr') as HTMLElement
    expect(within(without).queryByText('Estoque')).not.toBeInTheDocument()
  })

  it('conta BR ativa mostra o checkbox e o PATCH leva o valor marcado', async () => {
    const patches: Array<Record<string, unknown>> = []
    install(patches)
    renderPlatform()
    await openEditor('Bia Brasil')
    const checkbox = screen.getByLabelText('Acesso ao Estoque')
    expect(checkbox).toBeChecked()
    await userEvent.click(checkbox)
    await userEvent.click(screen.getByRole('button', { name: 'Salvar identidade e mercados' }))
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].has_stock_access).toBe(false)
  })

  it('o admin concede o acesso a quem ainda não tem', async () => {
    const patches: Array<Record<string, unknown>> = []
    install(patches)
    server.use(http.get('*/users', () => HttpResponse.json([identity('u-br', 'Bia Brasil', [access()], false)])))
    renderPlatform()
    await openEditor('Bia Brasil')
    const checkbox = screen.getByLabelText('Acesso ao Estoque')
    expect(checkbox).not.toBeChecked()
    await userEvent.click(checkbox)
    await userEvent.click(screen.getByRole('button', { name: 'Salvar identidade e mercados' }))
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].has_stock_access).toBe(true)
  })

  it('sem BR ativo ou com papel cliente não há checkbox', async () => {
    install()
    renderPlatform()
    for (const name of ['Eva Europa', 'Paulo Pendente', 'Clara Cliente']) {
      await openEditor(name)
      expect(screen.queryByLabelText('Acesso ao Estoque')).not.toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    }
  })

  it('ao tirar o BR da conta, a tela envia false mesmo com o acesso antes marcado', async () => {
    const patches: Array<Record<string, unknown>> = []
    install(patches)
    renderPlatform()
    await openEditor('Bia Brasil')
    await userEvent.click(screen.getByRole('button', { name: 'Remover vínculo BR' }))
    await userEvent.click(screen.getByRole('button', { name: 'Salvar identidade e mercados' }))
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].has_stock_access).toBe(false)
  })
})
