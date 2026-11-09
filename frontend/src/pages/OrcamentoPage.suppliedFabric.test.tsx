import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey } from '../lib/cart'
import type { Client, OptionalApplication, OptionalColor, Product } from '../types'
import { productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

// TECIDO FORNECIDO (Portugal): opção na aplicação de tecidos IBTW de produtos
// importados. Ao escolher, aparece o campo de metragem (só leitura) e o preço da
// linha passa para o da planilha; trocar de opção volta ao normal.

const client: Client = {
  id: 'client-eu-fabric', name: 'Cliente Portugal', phone: '+351 912 345 678', email: null,
  cpf_cnpj: null, cep: '1000-001', numero: null, address: 'Rua de Teste', city: 'Lisboa',
  state: 'Lisboa', country: 'PT', region: null, tax_id: 'PT123456789', market_code: 'EU',
  price_profile: 'lojista', max_discount: 0, rep_id: null, created_at: '2026-11-09T12:00:00Z',
  updated_at: '2026-11-09T12:00:00Z', last_activity_at: '2026-11-09T12:00:00Z',
}

const LINEN: OptionalColor = { id: 'opt-linho', category: 'TECIDOS_IBTW', color_name: 'Linho', photo_url: null } as OptionalColor

function fabricApplication(id: string, name: string, order: number): OptionalApplication {
  return {
    id, category_id: 'cat-tecidos', category_code: 'TECIDOS_IBTW', category_name: 'Tecidos IBTW',
    name, name_en: null, required: false, display_order: order, allow_all: false, allow_repeat: true,
    allowed_optionals: [LINEN],
  }
}

function sofa(withFabricData: boolean): Product {
  return {
    ...productFixture('EU'),
    product_code: 'SF0343',
    description: 'Sofá Portugal',
    description_pt_pt: 'Sofá Portugal',
    market_prices: { lojista: 1000, corporativo: 900, arquiteto: 800, pvp: 1200 },
    catalog: { id: 'catalog-ibtw', name: 'IBTW' },
    optional_applications: [fabricApplication('app-tecido', 'Tecido', 0), fabricApplication('app-almofadas', 'Almofadas', 1)],
    supplied_fabric: withFabricData
      ? { linear_meters: '13.20', prices: { lojista: '700.10', corporativo: '650', arquiteto: '600', pvp: '800' } }
      : null,
  } as Product
}

function install(product: Product) {
  server.use(
    http.get('*/products', () => HttpResponse.json([product], {
      headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
    })),
    http.post('*/products/batch', async ({ request }) => {
      const body = await request.json() as { product_codes?: string[] }
      return HttpResponse.json((body.product_codes ?? []).map(code => code === product.product_code ? product : null).filter(Boolean))
    }),
    http.get('*/clients', () => HttpResponse.json([])),
    http.get(`*/clients/${client.id}`, () => HttpResponse.json(client)),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([{ id: 'cat-tecidos', code: 'TECIDOS_IBTW', name: 'Tecidos IBTW' }])),
    http.get('*/product-types', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([LINEN])),
  )
}

function renderQuote() {
  const user = productTestUser('admin', 'EU')
  localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([{
    line_id: 'line-1', product_code: 'SF0343', qty: 1, discount: 0, opt_categories: {}, optional_choices: [],
  }]))
  sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, client.id)
  renderProductPage(<OrcamentoPage />, user)
  return user
}

const storedChoices = (userId: string) =>
  (JSON.parse(localStorage.getItem(cartStorageKey(userId, 'EU')) ?? '[]') as Array<{ optional_choices: unknown[] }>)[0]?.optional_choices ?? []

async function openFirstFabric() {
  const [combobox] = await screen.findAllByRole('combobox', { name: 'Tecidos IBTW: Tecido' })
  fireEvent.click(combobox)
  return combobox
}

describe('OrcamentoPage — TECIDO FORNECIDO (EU)', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('oferece a opção, mostra a metragem e troca o preço pelo da planilha; trocar de opção volta ao normal', async () => {
    install(sofa(true))
    const user = renderQuote()
    const [line] = await screen.findAllByRole('listitem', { name: /SF0343/ })

    // Estado inicial: preço normal, sem campo de metragem.
    expect(line.textContent).toMatch(/1000,00/)
    expect(screen.queryByLabelText('Tecido necessário (metros lineares)')).toBeNull()

    await openFirstFabric()
    fireEvent.click(screen.getByRole('option', { name: 'TECIDO FORNECIDO' }))

    // Campo só leitura com a coluna "MTS TECIDO" e preço da planilha (lojista).
    const field = (await screen.findAllByLabelText('Tecido necessário (metros lineares)'))[0] as HTMLInputElement
    expect(field.readOnly).toBe(true)
    expect(field.value).toBe('13,2 m')
    await waitFor(() => expect(line.textContent).toMatch(/700,10/))
    expect(line.textContent).not.toMatch(/1000,00/)
    // Vale para todos os tecidos IBTW do produto: a 2ª aplicação foi marcada junto.
    expect(storedChoices(user.id)).toEqual(expect.arrayContaining([
      { application_id: 'app-tecido', supplied_fabric: true },
      { application_id: 'app-almofadas', supplied_fabric: true },
    ]))

    // Volta a uma opção do cadastro: campo some, preço normal, irmãs desmarcadas.
    const [combobox] = await screen.findAllByRole('combobox', { name: 'Tecidos IBTW: Tecido' })
    fireEvent.click(combobox)
    fireEvent.click(screen.getByRole('option', { name: 'Linho' }))
    await waitFor(() => expect(screen.queryByLabelText('Tecido necessário (metros lineares)')).toBeNull())
    await waitFor(() => expect(line.textContent).toMatch(/1000,00/))
    expect(storedChoices(user.id)).toEqual([{ application_id: 'app-tecido', optional_id: 'opt-linho' }])
  })

  it('não oferece a opção em produto sem dado importado', async () => {
    install(sofa(false))
    renderQuote()
    await openFirstFabric()
    expect(screen.getByRole('option', { name: 'Linho' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: 'TECIDO FORNECIDO' })).toBeNull()
  })

  it('mostra o rótulo em inglês no orçamento em en-GB', async () => {
    install(sofa(true))
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(`ilya-locale:${user.id}:EU`, 'en-GB')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([{
      line_id: 'line-1', product_code: 'SF0343', qty: 1, discount: 0, opt_categories: {},
      optional_choices: [{ application_id: 'app-tecido', supplied_fabric: true }, { application_id: 'app-almofadas', supplied_fabric: true }],
    }]))
    sessionStorage.setItem(`orcamento_client_id:${user.id}:EU`, client.id)
    renderProductPage(<OrcamentoPage />, user)
    const field = (await screen.findAllByLabelText('Fabric required (linear metres)'))[0] as HTMLInputElement
    expect(field.value).toBe('13.2 m')
    const [line] = await screen.findAllByRole('listitem', { name: /SF0343/ })
    expect(within(line).getAllByText(/SUPPLIED FABRIC/).length).toBeGreaterThan(0)
  })
})
