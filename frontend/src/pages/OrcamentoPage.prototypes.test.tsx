import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey } from '../lib/cart'
import { installProductHandlers, productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

const PROTOTYPE = {
  ...productFixture('EU', {
    id: 'proto-1', product_code: 'PROT-0001', description: 'Poltrona protótipo',
    market_prices: { lojista: 1000, corporativo: 900, pvp: 1500, arquiteto: 1100 },
  }),
  is_prototype: true, vat_rate: '23.00',
}
const NORMAL = productFixture('EU', { id: 'eu-1', product_code: 'EU-001', description: 'Mesa comum' })

/** Imita o servidor: o protótipo só vem com include_prototypes=true E texto em q. */
function installSearch(seen: URLSearchParams[]) {
  installProductHandlers()
  server.use(
    http.get('*/products', ({ request }) => {
      const params = new URL(request.url).searchParams
      seen.push(params)
      const q = (params.get('q') ?? '').toLowerCase()
      const withPrototypes = params.get('include_prototypes') === 'true' && q !== ''
      const rows = [NORMAL, ...(withPrototypes ? [PROTOTYPE] : [])].filter(
        row => !q || `${row.product_code} ${row.description}`.toLowerCase().includes(q),
      )
      return HttpResponse.json(rows, {
        headers: { 'X-Total-Count': String(rows.length), 'X-Has-More': 'false', 'X-Page-Size': String(rows.length) },
      })
    }),
    http.post('*/products/batch', async ({ request }) => {
      const body = await request.json() as { product_codes: string[] }
      return HttpResponse.json([PROTOTYPE, NORMAL].filter(row => body.product_codes.includes(row.product_code)))
    }),
  )
}

async function typeInSearch(text: string) {
  const [input] = await screen.findAllByLabelText(/Buscar produto para adicionar ao orçamento/i)
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: text } })
}

describe('OrcamentoPage — busca de protótipo pelo código', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('com a permissão, digitar PROT-00 (qualquer caixa) mostra o protótipo e o adiciona como produto normal', async () => {
    const seen: URLSearchParams[] = []
    installSearch(seen)
    const user = { ...productTestUser('vendedor', 'EU'), can_manage_prototypes: true }
    renderProductPage(<OrcamentoPage />, user)

    await typeInSearch('prot-00')
    const item = (await screen.findAllByText('PROT-0001'))[0].closest('li') as HTMLElement
    expect(item).toHaveTextContent('Poltrona protótipo')
    expect(item).toHaveTextContent('Protótipo')
    expect(seen.some(params => params.get('include_prototypes') === 'true' && params.get('q') === 'prot-00')).toBe(true)

    fireEvent.mouseDown(item)
    fireEvent.click(screen.getAllByRole('button', { name: /ADICIONAR AO ORÇAMENTO/i })[0])
    await waitFor(() => {
      const cart = JSON.parse(localStorage.getItem(cartStorageKey(user.id, 'EU')) ?? '[]') as Array<{ product_code: string; qty: number }>
      expect(cart).toHaveLength(1)
      expect(cart[0]).toMatchObject({ product_code: 'PROT-0001', qty: 1 })
    })
  })

  it('o nome do protótipo também encontra', async () => {
    installSearch([])
    renderProductPage(<OrcamentoPage />, { ...productTestUser('vendedor', 'EU'), can_manage_prototypes: true })
    await typeInSearch('poltrona')
    expect((await screen.findAllByText('PROT-0001')).length).toBeGreaterThan(0)
  })

  it('sem a permissão o front nem pede protótipo e o código exato não acha nada', async () => {
    const seen: URLSearchParams[] = []
    installSearch(seen)
    renderProductPage(<OrcamentoPage />, { ...productTestUser('vendedor', 'EU'), can_manage_prototypes: false })
    await typeInSearch('PROT-0001')
    await waitFor(() => expect(seen.some(params => params.get('q') === 'PROT-0001')).toBe(true))
    await screen.findAllByText('Nenhum produto encontrado.')
    expect(screen.queryByText('PROT-0001')).not.toBeInTheDocument()
    expect(seen.every(params => params.get('include_prototypes') === null)).toBe(true)
  })

  it('no mercado BR o pedido de protótipo nem sai, mesmo com a permissão no usuário', async () => {
    const seen: URLSearchParams[] = []
    installSearch(seen)
    renderProductPage(<OrcamentoPage />, { ...productTestUser('vendedor', 'BR'), can_manage_prototypes: true })
    await typeInSearch('PROT-0001')
    await waitFor(() => expect(seen.some(params => params.get('q') === 'PROT-0001')).toBe(true))
    expect(seen.every(params => params.get('include_prototypes') === null)).toBe(true)
    expect(screen.queryByText('PROT-0001')).not.toBeInTheDocument()
  })
})
