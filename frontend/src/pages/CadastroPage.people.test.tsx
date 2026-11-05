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

  it('não mostra tabelas de preço visíveis na edição do cliente', async () => {
    const { table, user } = await renderClientsPage()
    const row = within(table).getByText('Studio Lumina').closest('tr')
    if (!row) throw new Error('Linha do cliente não encontrada')

    await user.click(within(row).getByRole('button', { name: 'Editar' }))

    expect(screen.queryByText('Tabelas de preço visíveis')).toBeNull()
    expect(screen.getByText('Perfil de faturamento *')).toBeVisible()
  })

  it('Portugal oculta o perfil de faturamento do cliente', async () => {
    const user = userEvent.setup()
    const euClient = { ...clients[0], id: 'client-eu', market_code: 'EU' as const, country: 'PT', state: '--' }
    installProductHandlers()
    server.use(
      http.get('*/clients', () => HttpResponse.json([euClient], {
        headers: { 'X-Total-Count': '1' },
      })),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await user.click(screen.getAllByRole('button', { name: /Clientes/ })[0])
    const table = await screen.findByRole('table')
    const row = within(table).getByText(euClient.name).closest('tr')
    if (!row) throw new Error('Linha do cliente EU não encontrada')

    await user.click(within(row).getByRole('button', { name: 'Editar' }))

    expect(screen.queryByText('Perfil de faturamento *')).toBeNull()
  })

  it('Portugal cadastra os dados informativos sem preencher o país automaticamente', async () => {
    const user = userEvent.setup()
    let createPayload: Record<string, unknown> | null = null
    installProductHandlers()
    server.use(
      http.get('*/clients', () => HttpResponse.json([], {
        headers: { 'X-Total-Count': '0' },
      })),
      http.post('*/clients', async ({ request }) => {
        createPayload = await request.json() as Record<string, unknown>
        return HttpResponse.json({ id: 'client-eu-new' }, { status: 201 })
      }),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await user.click(screen.getAllByRole('button', { name: /Clientes/ })[0])
    const newClientButton = await waitFor(() => {
      const button = Array.from(document.querySelectorAll<HTMLButtonElement>('button'))
        .find((candidate) => candidate.textContent?.includes('Novo Cliente'))
      if (!button) throw new Error('Botão Novo Cliente não encontrado')
      return button
    })
    await user.click(newClientButton)

    expect(screen.getByLabelText('País')).toHaveValue('')
    expect(screen.queryByText('Desconto Máximo (%)')).toBeNull()
    await user.type(screen.getByLabelText('Cliente *'), 'Casa Atlântico')
    await user.type(screen.getByLabelText('Contato'), 'Maria Silva')
    const clientType = screen.getByLabelText('Tipo de cliente *')
    expect(within(clientType).getByRole('option', { name: 'LOJISTA/DIST/FFE' })).toHaveValue('lojista')
    expect(within(clientType).getByRole('option', { name: 'ARQUITETO/INTERIOR DESIGN' })).toHaveValue('arquiteto')
    await user.selectOptions(clientType, 'arquiteto')
    await user.type(screen.getByLabelText('Telefone *'), '+351 912 345 678')
    await user.type(screen.getByLabelText('Código postal *'), '1000-001')
    await user.type(screen.getByLabelText('Endereço *'), 'Rua Teste')
    await user.type(screen.getByLabelText('Localidade *'), 'Lisboa')
    await user.type(screen.getByLabelText('País'), 'Portugal')
    await user.type(screen.getByLabelText('Observação'), 'Contato após as 14h.')
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    await waitFor(() => {
      expect(createPayload).toMatchObject({
        name: 'Casa Atlântico',
        contact_name: 'Maria Silva',
        client_type: 'arquiteto',
        country: 'Portugal',
        observation: 'Contato após as 14h.',
        price_profile: 'lojista',
      })
    })
  })

  it('Portugal oculta tabelas visíveis e força acesso a todas ao salvar representante', async () => {
    const user = userEvent.setup()
    let createPayload: Record<string, unknown> | null = null
    installProductHandlers()
    server.use(
      http.get('*/representatives', () => HttpResponse.json([], {
        headers: { 'X-Total-Count': '0' },
      })),
      http.post('*/representatives', async ({ request }) => {
        createPayload = await request.json() as Record<string, unknown>
        return HttpResponse.json({ id: 'rep-eu-new' }, { status: 201 })
      }),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await user.click(screen.getAllByRole('button', { name: /Representantes/ })[0])
    const newRepresentativeButton = await waitFor(() => {
      const button = Array.from(document.querySelectorAll<HTMLButtonElement>('button'))
        .find((candidate) => candidate.textContent?.includes('Novo Representante'))
      if (!button) throw new Error('Botão Novo Representante não encontrado')
      return button
    })
    await user.click(newRepresentativeButton)

    expect(screen.queryByText('Tabelas de preço visíveis')).toBeNull()
    expect(screen.queryByText('Desconto Máximo (%)')).toBeNull()
    await user.type(screen.getByLabelText('Nome *'), 'Representante Portugal')
    await user.type(screen.getByLabelText('Telefone *'), '+351 912 345 678')
    await user.type(screen.getByLabelText('Código postal *'), '1000-001')
    await user.type(screen.getByLabelText('Endereço *'), 'Rua Teste')
    await user.type(screen.getByLabelText('Localidade *'), 'Lisboa')
    await user.type(screen.getByLabelText('País'), 'Portugal')
    await user.click(screen.getByRole('button', { name: 'Criar' }))

    await waitFor(() => {
      expect(createPayload).toMatchObject({
        all_price_lists: true,
        price_list_codes: [],
      })
      expect(createPayload).not.toHaveProperty('max_discount')
    })
  })
})

describe('Ficha de cliente de Portugal', () => {
  const euClient: Client = {
    ...clients[0],
    id: 'client-eu-ficha',
    name: 'Casa Atlântico',
    market_code: 'EU',
    country: 'Portugal',
    state: '--',
    numero: '12',
    tax_id: 'PT501964843',
    contact_name: 'Maria',
    client_type: 'lojista',
    observation: 'Ligar à tarde.',
    contacted: false,
  }

  async function openEuEdit(patch?: (payload: Record<string, unknown>) => Response | undefined) {
    const user = userEvent.setup()
    installProductHandlers()
    const payloads: Record<string, unknown>[] = []
    server.use(
      http.get('*/clients', () => HttpResponse.json([euClient], { headers: { 'X-Total-Count': '1' } })),
      http.patch(`*/clients/${euClient.id}`, async ({ request }) => {
        const payload = await request.json() as Record<string, unknown>
        payloads.push(payload)
        return patch?.(payload) ?? HttpResponse.json({ ...euClient, ...payload })
      }),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await user.click(screen.getAllByRole('button', { name: /Clientes/ })[0])
    const table = await screen.findByRole('table')
    const row = within(table).getByText(euClient.name).closest('tr')
    if (!row) throw new Error('Linha do cliente EU não encontrada')
    await user.click(within(row).getByRole('button', { name: 'Editar' }))
    return { user, payloads }
  }

  it('não mostra o número da morada e põe "Cliente contactado" logo abaixo da observação', async () => {
    await openEuEdit()

    expect(screen.queryByLabelText('Número')).toBeNull()
    const observation = screen.getByLabelText('Observação')
    const contacted = screen.getByLabelText('Cliente contactado')
    expect(contacted).not.toBeChecked()
    expect(observation.compareDocumentPosition(contacted) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('editar grava VAT, contactado e demais campos no PATCH (sem número)', async () => {
    const { user, payloads } = await openEuEdit()

    const vat = screen.getByLabelText('VAT / Tax ID')
    await user.clear(vat)
    await user.type(vat, 'PT999888777')
    await user.clear(screen.getByLabelText('Telefone *'))
    await user.type(screen.getByLabelText('Telefone *'), '+351 933 000 111')
    await user.click(screen.getByLabelText('Cliente contactado'))
    await user.click(screen.getByRole('button', { name: 'Salvar' }))

    await waitFor(() => expect(payloads).toHaveLength(1))
    expect(payloads[0]).toMatchObject({
      tax_id: 'PT999888777',
      phone: '+351 933 000 111',
      contacted: true,
      observation: 'Ligar à tarde.',
      country: 'Portugal',
    })
    expect(payloads[0]).not.toHaveProperty('numero')
  })

  it('mostra o motivo quando o servidor recusa a edição (VAT repetido)', async () => {
    const { user } = await openEuEdit(() =>
      HttpResponse.json({ detail: 'Já existe um cliente com este VAT / Tax ID.' }, { status: 409 }),
    )

    await user.click(screen.getByRole('button', { name: 'Salvar' }))

    expect(await screen.findByText('Já existe um cliente com este VAT / Tax ID.')).toBeVisible()
  })

  it('a navegação do Cadastro chama-se Fichas em Portugal e Cadastros no Brasil', async () => {
    installProductHandlers()
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    expect((await screen.findAllByText('Fichas')).length).toBeGreaterThan(0)
    expect(screen.queryByText('Cadastros')).toBeNull()
  })
})
