import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import AdminPage from './AdminPage'

// Os painéis de privacidade têm as próprias chamadas; não fazem parte deste teste.
vi.mock('../components/RetentionGovernancePanel', () => ({ default: () => null }))
vi.mock('../components/IncidentRegistryPanel', () => ({ default: () => null }))

describe('AdminPage na sessão de mercado', () => {
  it.each([401, 403])('com %i na lista de contas avisa onde administrar, com link para /platform', async (status) => {
    server.use(http.get('*/users', () => HttpResponse.json({ detail: 'x' }, { status })))
    renderProductPage(<AdminPage />, productTestUser('admin', 'BR'), ['/admin'])

    expect(await screen.findByRole('alert')).toHaveTextContent('A administração de contas fica na Plataforma')
    expect(screen.getByRole('link', { name: 'Ir para a Plataforma' })).toHaveAttribute('href', '/platform')
    expect(screen.queryByRole('button', { name: /Novo Usuário/ })).not.toBeInTheDocument()
  })

  it('outros erros (500) não mostram o aviso da Plataforma', async () => {
    server.use(http.get('*/users', () => HttpResponse.json({ detail: 'x' }, { status: 500 })))
    renderProductPage(<AdminPage />, productTestUser('admin', 'BR'), ['/admin'])

    expect(await screen.findByRole('button', { name: /Novo Usuário/ })).toBeInTheDocument()
    expect(screen.queryByText('A administração de contas fica na Plataforma')).not.toBeInTheDocument()
  })
})
