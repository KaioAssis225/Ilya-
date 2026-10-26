import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import CadastroPage from './CadastroPage'
import type { Client } from '../types'
import {
  installProductHandlers,
  productTestUser,
  renderProductPage,
} from '../test/productTestUtils'
import { server } from '../test/setup'

const clients: Client[] = [
  {
    id: 'client-layout-1',
    name: 'Casa Castro Interiores e Arquitetura Comercial Ltda.',
    phone: '(41) 93222-8899',
    email: 'contato.projetos.arquitetura@casacastrointeriores.com.br',
    cpf_cnpj: '12.345.678/0001-90',
    cep: '12240-000',
    numero: '120',
    address: 'Avenida Cassiano Ricardo',
    city: 'São José dos Campos',
    state: 'SP',
    country: 'BR',
    region: null,
    tax_id: null,
    market_code: 'BR',
    price_profile: 'lojista',
    max_discount: 8,
    rep_id: null,
    created_at: '2026-10-23T12:00:00Z',
    updated_at: '2026-10-23T12:00:00Z',
    last_activity_at: '2026-10-23T12:00:00Z',
    created_by_name: 'Marina — Demonstração',
  },
  {
    id: 'client-layout-2',
    name: 'Studio Lumina',
    phone: '+351 912 345 678',
    email: 'studio.lumina@example.test',
    cpf_cnpj: '98.765.432/0001-10',
    cep: '01414-001',
    numero: '450',
    address: 'Rua Haddock Lobo',
    city: 'São Paulo',
    state: 'SP',
    country: 'BR',
    region: null,
    tax_id: null,
    market_code: 'BR',
    price_profile: 'corporativo',
    all_price_lists: false,
    price_list_codes: [],
    max_discount: 10,
    rep_id: null,
    created_at: '2026-10-23T12:00:00Z',
    updated_at: '2026-10-23T12:00:00Z',
    last_activity_at: '2026-10-23T12:00:00Z',
    created_by_name: 'Marina — Demonstração',
  },
]

async function renderClientsPage(requestUrls: URL[] = []) {
  const user = userEvent.setup()
  installProductHandlers()
  server.use(
    http.get('*/clients', ({ request }) => {
      requestUrls.push(new URL(request.url))
      return HttpResponse.json(clients, {
        headers: { 'X-Total-Count': String(clients.length) },
      })
    }),
  )
  renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))
  await user.click(screen.getAllByRole('button', { name: /Clientes/ })[0])
  const table = await screen.findByRole('table')
  return { table, user }
}

describe('CadastroPage — tabela de clientes', () => {
  it('agrupa telefone íntegro e e-mail na mesma célula de contato', async () => {
    const { table } = await renderClientsPage()

    const phone = within(table).getByText('(41) 93222-8899')
    const contactCell = phone.closest('td')

    expect(contactCell).not.toBeNull()
    expect(within(contactCell!).getByText('contato.projetos.arquitetura@casacastrointeriores.com.br')).toBeVisible()
  })

  it('mantém visualizar, editar e excluir alcançáveis em cada linha desktop', async () => {
    const { table } = await renderClientsPage()

    expect(within(table).getAllByRole('button', { name: 'Visualizar' })).toHaveLength(2)
    expect(within(table).getAllByRole('button', { name: 'Editar' })).toHaveLength(2)
    expect(within(table).getAllByRole('button', { name: 'Excluir' })).toHaveLength(2)
  })

  it('ordena por nome pelo teclado e reflete a direção no cabeçalho', async () => {
    const requestUrls: URL[] = []
    const { table, user } = await renderClientsPage(requestUrls)
    const sortButton = within(table).getByRole('button', { name: 'Nome' })
    const nameHeader = sortButton.closest('th')

    expect(nameHeader).toHaveAttribute('aria-sort', 'ascending')
    sortButton.focus()
    await user.keyboard('{Enter}')

    await waitFor(() => {
      // A troca de ordenação refaz a consulta e pode remontar a tabela: consultar o DOM vivo.
      const currentNameHeader = within(screen.getByRole('table')).getByRole('button', { name: 'Nome' }).closest('th')
      expect(currentNameHeader).toHaveAttribute('aria-sort', 'descending')
      expect(requestUrls.some((url) => (
        url.searchParams.get('sort_by') === 'name'
        && url.searchParams.get('sort_dir') === 'desc'
      ))).toBe(true)
    })
  })
})

describe('CadastroPage — tabelas de preço visíveis', () => {
  it('admin cria representante com a lista Lojista após sair de Todas', async () => {
    const user = userEvent.setup()
    let createPayload: Record<string, unknown> | null = null
    installProductHandlers()
    server.use(
      http.get('*/representatives', () => HttpResponse.json([], {
        headers: { 'X-Total-Count': '0' },
      })),
      http.post('*/representatives', async ({ request }) => {
        createPayload = await request.json() as Record<string, unknown>
        return HttpResponse.json({ id: 'rep-price-list-new' }, { status: 201 })
      }),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))
    await user.click(screen.getAllByRole('button', { name: /Representantes/ })[0])
    const newRepresentativeButton = await waitFor(() => {
      const button = Array.from(document.querySelectorAll<HTMLButtonElement>('button'))
        .find((candidate) => candidate.textContent?.includes('Novo Representante'))
      if (!button) throw new Error('Botão Novo Representante não encontrado')
      return button
    })
    await user.click(newRepresentativeButton)

    expect(screen.getByRole('button', { name: 'Todas' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: 'Lojista' }))
    expect(screen.getByRole('button', { name: 'Todas' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Lojista' })).toHaveAttribute('aria-pressed', 'true')

    await user.type(screen.getByLabelText('Nome *'), 'Representante Teste')
    await user.type(screen.getByLabelText('Telefone *'), '11999999999')
    await user.type(screen.getByLabelText('CEP *'), '01001000')
    await user.type(screen.getByLabelText('Endereço *'), 'Rua Teste')
    await user.type(screen.getByLabelText('Cidade *'), 'São Paulo')
    await user.selectOptions(screen.getByLabelText('Estado *'), 'SP')
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    await waitFor(() => {
      expect(createPayload).toMatchObject({
        all_price_lists: false,
        price_list_codes: ['lojista'],
      })
    })
  })

  it('mantém o perfil de faturamento corporativo pressionado e bloqueado na edição', async () => {
    const { table, user } = await renderClientsPage()
    const row = within(table).getByText('Studio Lumina').closest('tr')
    if (!row) throw new Error('Linha do cliente não encontrada')

    await user.click(within(row).getByRole('button', { name: 'Editar' }))

    const billingProfile = screen.getByTitle('O perfil de faturamento fica sempre visível.')
    expect(billingProfile).toHaveAttribute('aria-pressed', 'true')
    expect(billingProfile).toBeDisabled()
  })
})
