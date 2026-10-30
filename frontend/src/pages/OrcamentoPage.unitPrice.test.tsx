import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import OrcamentoPage from './OrcamentoPage'
import { cartStorageKey, writeCartPriceList } from '../lib/cart'
import type { Product } from '../types'
import { renderProductPage, productFixture, productTestUser } from '../test/productTestUtils'
import { server } from '../test/setup'

// Coluna "Valor unitário com desconto": preço-base − desconto unitário. O
// subtotal continua sendo o oficial do servidor (linha arredondada uma vez).

const eur = (value: number) => new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(value)
const brl = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value)

function buildProduct(market: 'BR' | 'EU', overrides: Partial<Product> = {}): Product {
  return {
    ...productFixture(market),
    product_code: market === 'BR' ? 'SKU-BR' : 'SKU-EU',
    optional_applications: [],
    ...overrides,
  } as Product
}

function eurProduct(overrides: Partial<Product> = {}): Product {
  return buildProduct('EU', {
    market_prices: { lojista: 1731.18, corporativo: 1731.18, pvp: 1731.18, arquiteto: 1731.18 },
    price: 1731.18,
    price_lojista: 1731.18,
    ...overrides,
  })
}

function installHandlers(products: Product[], productTypes: unknown[] = []) {
  server.use(
    http.get('*/products', () => HttpResponse.json(products, {
      headers: { 'X-Total-Count': String(products.length), 'X-Has-More': 'false', 'X-Page-Size': String(products.length) },
    })),
    http.post('*/products/batch', async ({ request }) => {
      const codes = ((await request.json()) as { product_codes?: string[] }).product_codes ?? []
      return HttpResponse.json(products.filter((p) => codes.includes(p.product_code)))
    }),
    http.get('*/clients', () => HttpResponse.json([])),
    http.get('*/representatives', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/product-types', () => HttpResponse.json(productTypes)),
    http.get('*/optionals', () => HttpResponse.json([])),
  )
}

function cartLine(overrides: Record<string, unknown>) {
  return {
    line_id: 'line-1', product_code: 'SKU-EU', qty: 1, discount: 0,
    opt_categories: {}, optional_choices: [], ...overrides,
  }
}

/** Texto do valor que acompanha o rótulo da coluna dentro da linha desktop. */
function columnValue(item: HTMLElement, label: string): string {
  return within(item).getByText(label).parentElement?.textContent ?? ''
}

function expectSubtotal(item: HTMLElement, formatted: string) {
  expect(columnValue(item, 'Subtotal')).toContain(formatted)
}

describe('OrcamentoPage — valor unitário com desconto', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('colunas na ordem pedida e quantidade 1 sem desconto: unitário = preço-base = subtotal', async () => {
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({})]))
    writeCartPriceList(user.id, 'EU', 'lojista')
    installHandlers([eurProduct()])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    const labels = ['Qtd', 'Preço-base unitário', 'Desconto (%)', 'Valor unitário com desconto', 'Subtotal']
    const positions = labels.map((label) => item.textContent!.indexOf(label))
    expect(positions.every((p) => p >= 0)).toBe(true)
    expect([...positions].sort((a, b) => a - b)).toEqual(positions)
    expect(columnValue(item, 'Preço-base unitário')).toContain(eur(1731.18))
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(eur(1731.18))
    expectSubtotal(item, eur(1731.18))
  })

  it('quantidade > 1 sem desconto: unitário mantém o preço-base e o subtotal multiplica', async () => {
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({ qty: 3 })]))
    writeCartPriceList(user.id, 'EU', 'lojista')
    installHandlers([eurProduct()])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(eur(1731.18))
    expectSubtotal(item, eur(5193.54))
  })

  it('restaura do carrinho qtd 2 com 10% (exemplo da especificação) na tabela PVP', async () => {
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({ qty: 2, discount: 10 })]))
    writeCartPriceList(user.id, 'EU', 'pvp')
    installHandlers([eurProduct()])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    expect(columnValue(item, 'Preço-base unitário')).toContain(eur(1731.18))
    // Indicação monetária do desconto por unidade, abaixo do campo (aprovada).
    expect(item.textContent).toContain(`− ${eur(173.12)}`)
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(eur(1558.06))
    expectSubtotal(item, eur(3116.12))
  })

  it('qtd 3 com 10%: subtotal oficial (linha arredondada uma vez) difere 1 centavo de unitário × qtd', async () => {
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({ qty: 3, discount: 10 })]))
    writeCartPriceList(user.id, 'EU', 'pvp')
    installHandlers([eurProduct()])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(eur(1558.06))
    // 1.558,062 × 3 = 4.674,186 → 4.674,19 (e não 1.558,06 × 3 = 4.674,18).
    expectSubtotal(item, eur(4674.19))
    expect(item.textContent).not.toContain(eur(4674.18))
  })

  it('IVA e total geral saem dos subtotais líquidos, sem aplicar o desconto duas vezes', async () => {
    const user = productTestUser('admin', 'EU')
    const product = eurProduct({ vat_rate: '23.00' })
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({ qty: 3, discount: 10 })]))
    writeCartPriceList(user.id, 'EU', 'pvp')
    installHandlers([product])

    renderProductPage(<OrcamentoPage />, user)

    await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    const summary = screen.getByText('Total do Orçamento:').parentElement?.textContent
    expect(summary).toContain(`Subtotal: ${eur(4674.19)}`)
    expect(summary).toContain(`IVA: ${eur(1075.06)}`)
    expect(summary).toContain(eur(5749.25))
  })

  it('edição de pedido: carrega qtd e desconto salvos e recalcula o unitário líquido', async () => {
    const user = productTestUser('admin', 'EU')
    const product = eurProduct()
    const orderId = 'order-unit-price'
    installHandlers([product])
    server.use(
      http.get(`*/orders/${orderId}`, () => HttpResponse.json({
        id: orderId, code: 'PED-EU-0100', client_id: 'client-1', rep_id: null,
        price_list_code: 'pvp', notes: null,
        items: [{
          id: 'item-1', product_code: product.product_code, qty: 2, sold_by_area: false,
          discount: '10.00', opt_categories: {}, optional_choices: [], comment: null,
        }],
      })),
      http.get('*/clients/client-1', () => HttpResponse.json({
        id: 'client-1', name: 'Cliente Portugal', market_code: 'EU', price_profile: 'lojista',
        max_discount: 0, rep_id: null, country: 'PT',
      })),
    )

    renderProductPage(<OrcamentoPage />, user, [`/orcamentos?edit=${orderId}`])

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(eur(1558.06))
    expectSubtotal(item, eur(3116.12))
  })

  it('muda o desconto e atualiza o desconto unitário, o valor unitário e o subtotal', async () => {
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({ qty: 2 })]))
    writeCartPriceList(user.id, 'EU', 'pvp')
    installHandlers([eurProduct()])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    fireEvent.change(within(item).getByLabelText('Desconto em Mesa PT'), { target: { value: '10' } })
    await waitFor(() => expectSubtotal(item, eur(3116.12)))
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(eur(1558.06))
  })

  it('cartão mobile mostra preço-base, desconto unitário, valor unitário e subtotal', async () => {
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({ qty: 2, discount: 10 })]))
    writeCartPriceList(user.id, 'EU', 'pvp')
    installHandlers([eurProduct()])

    renderProductPage(<OrcamentoPage />, user)

    await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    const term = screen.getAllByText('Valor unitário com desconto').find((el) => el.tagName === 'DT')
    const list = term?.closest('dl')
    expect(list).toBeTruthy()
    const text = list!.textContent!
    expect(text).toContain(eur(1731.18))
    expect(text).toContain(eur(173.12))
    expect(text).toContain(eur(1558.06))
    expect(text).toContain(eur(3116.12))
  })

  it('inglês: rótulos e valores da coluna nova', async () => {
    const user = productTestUser('admin', 'EU')
    localStorage.setItem(`ilya-locale:${user.id}:EU`, 'en-GB')
    localStorage.setItem(cartStorageKey(user.id, 'EU'), JSON.stringify([cartLine({ qty: 2, discount: 10 })]))
    writeCartPriceList(user.id, 'EU', 'pvp')
    installHandlers([eurProduct()])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-EU Mesa PT' })
    expect(within(item).getByText('Base unit price')).toBeInTheDocument()
    expect(columnValue(item, 'Unit price after discount')).toContain('1,558.06')
  })

  it('tapete: valor por m² com desconto e subtotal sobre a área total', async () => {
    const user = productTestUser('admin', 'BR')
    const rug = buildProduct('BR', {
      product_code: 'TAP-1', description: 'Tapete Teste',
      catalog_id: 'tapetes', catalog: { id: 'tapetes', name: 'Tapete' },
    })
    localStorage.setItem(cartStorageKey(user.id, 'BR'), JSON.stringify([cartLine({
      product_code: 'TAP-1', qty: 4.2, discount: 10, sold_by_area: true,
      area_width_m: 2.05, area_depth_m: 2.05, area_pieces: 1,
    })]))
    installHandlers([rug])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'TAP-1 Tapete Teste' })
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(`${brl(90)}/m²`)
    expectSubtotal(item, brl(378))
  })

  it('regressão BR: IPI continua na linha e o valor unitário não o inclui', async () => {
    const user = productTestUser('admin', 'BR')
    const product = buildProduct('BR', { type: 'Mesa' })
    localStorage.setItem(cartStorageKey(user.id, 'BR'), JSON.stringify([cartLine({
      product_code: 'SKU-BR', qty: 3, discount: 10,
    })]))
    installHandlers([product], [{ id: 't1', name: 'Mesa', group: { ipi: 10 } }])

    renderProductPage(<OrcamentoPage />, user)

    const item = await screen.findByRole('listitem', { name: 'SKU-BR Mesa BR' })
    expect(within(item).getByText('IPI')).toBeInTheDocument()
    await waitFor(() => expect(item.textContent).toContain('10%'))
    expect(columnValue(item, 'Valor unitário com desconto')).toContain(brl(90))
    // 3 × 90 = 270; com IPI 10% a linha mostra 297.
    expectSubtotal(item, brl(297))
  })
})
