import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import CadastroPage from './CadastroPage'
import { fittedProductColumnWidths } from '../lib/productColumns'
import { formatDimensions } from '../lib/measurements'
import {
  installProductHandlers,
  productFixture,
  productTestUser,
  renderProductPage,
} from '../test/productTestUtils'

describe('CadastroPage — layout de produtos', () => {
  it('mantém preço e ações na linha principal e revela os detalhes por clique e teclado', async () => {
    const user = userEvent.setup()
    const product = productFixture('BR', {
      id: 'layout-br-1',
      product_code: 'BR-LAYOUT-01',
      description: 'Mesa de jantar extensível com descrição longa para validar a leitura integral',
      largura: 1.2,
      profundidade: 0.8,
      altura: 0.75,
      price_lojista: 1234567.89,
      market_prices: { lojista: 1234567.89, corporativo: 987654.32 },
    })
    installProductHandlers({ products: [product] })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    const detailsButton = await screen.findByRole('button', { name: 'Ver detalhes de BR-LAYOUT-01' })
    const table = screen.getByRole('table')
    const mainRow = within(table).getByText('BR-LAYOUT-01').closest('tr')
    if (!mainRow) throw new Error('Linha principal do produto não encontrada')
    const dimensions = formatDimensions(product, 'BR', 'pt-BR')
    const lojistaPrice = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(1234567.89)

    expect(within(mainRow).getByText((_content, node) => node?.textContent === lojistaPrice)).toBeVisible()
    expect(within(mainRow).getByRole('button', { name: 'Editar' })).toBeVisible()
    expect(within(mainRow).getByRole('button', { name: 'Excluir' })).toBeVisible()
    expect(within(table).queryByText(dimensions)).not.toBeInTheDocument()
    expect(detailsButton).toHaveAttribute('aria-expanded', 'false')

    await user.click(detailsButton)
    expect(detailsButton).toHaveAttribute('aria-expanded', 'true')
    expect(within(table).getByText(dimensions)).toBeVisible()

    await user.click(detailsButton)
    expect(detailsButton).toHaveAttribute('aria-expanded', 'false')
    expect(within(table).queryByText(dimensions)).not.toBeInTheDocument()

    detailsButton.focus()
    await user.keyboard('{Enter}')
    expect(detailsButton).toHaveAttribute('aria-expanded', 'true')
    expect(within(table).getByText(dimensions)).toBeVisible()
  })

  it('alterna o menu desktop e persiste a preferência de recolhimento', async () => {
    const user = userEvent.setup()
    installProductHandlers()
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    const toggle = await screen.findByRole('button', { name: /(?:Expandir|Recolher) menu/ })
    const expandedBefore = toggle.getAttribute('aria-expanded') === 'true'

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', String(!expandedBefore))
    await waitFor(() => {
      expect(localStorage.getItem('cadastros_sidebar_collapsed')).toBe(expandedBefore ? '1' : '0')
    })
    // A preferência não pode herdar o TTL de 5 min do estado de aba/página.
    expect(JSON.parse(localStorage.getItem('cadastros_ui_state') ?? '{}')).not.toHaveProperty('sidebarCollapsed')
  })

  it('relê a preferência do menu ao remontar a página', async () => {
    installProductHandlers()
    localStorage.setItem('cadastros_sidebar_collapsed', '0')
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    const toggle = await screen.findByRole('button', { name: 'Recolher menu' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })

  it('mostra PVP e Arquiteto na linha principal para o mercado EU', async () => {
    const product = productFixture('EU', {
      id: 'layout-eu-1',
      product_code: 'EU-LAYOUT-01',
      description: 'Mesa europeia com descrição longa',
      market_prices: {
        lojista: 1234567.89,
        corporativo: 987654.32,
        pvp: 2345678.91,
        arquiteto: 3456789.12,
      },
    })
    installProductHandlers({ products: [product] })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    await screen.findByRole('button', { name: 'Ver detalhes de EU-LAYOUT-01' })
    const table = screen.getByRole('table')
    const mainRow = within(table).getByText('EU-LAYOUT-01').closest('tr')
    if (!mainRow) throw new Error('Linha principal EU não encontrada')
    const euro = (value: number) => new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(value)

    expect(within(table).getByRole('columnheader', { name: 'PVP' })).toBeVisible()
    expect(within(table).getByRole('columnheader', { name: 'Arquiteto' })).toBeVisible()
    expect(within(mainRow).getByText((_content, node) => node?.textContent === euro(2345678.91))).toBeVisible()
    expect(within(mainRow).getByText((_content, node) => node?.textContent === euro(3456789.12))).toBeVisible()
  })
})

describe('fittedProductColumnWidths — encaixe das colunas no container', () => {
  const BR = ['details', 'code', 'description', 'type', 'price_lojista', 'price_corporativo', 'actions'] as const
  const EU = [...BR.slice(0, -1), 'price_pvp', 'price_arquiteto', 'actions'] as const
  const sum = (widths: Record<string, number>, columns: readonly string[]) => columns.reduce((total, column) => total + widths[column], 0)

  it('distribui exatamente a largura disponível sem descer de nenhum mínimo', () => {
    const minimums = fittedProductColumnWidths([...BR], 0, false)
    const fitted = fittedProductColumnWidths([...BR], 1084, false)
    expect(sum(fitted, BR)).toBe(1084)
    for (const column of BR) expect(fitted[column]).toBeGreaterThanOrEqual(minimums[column])
    expect(fitted.description).toBeGreaterThan(minimums.description)
  })

  it('cabe em 1440px com o menu em rail nos dois mercados e devolve os mínimos quando não cabe', () => {
    // 1440 − 64 (px-8) − 72 (rail) − 24 (gap) − 48 (p-6) − 2 (borda) − 17 (barra de rolagem)
    const available = 1211
    const minimumsEu = fittedProductColumnWidths([...EU], 0, true)
    expect(sum(minimumsEu, EU)).toBeLessThanOrEqual(available)
    expect(sum(fittedProductColumnWidths([...EU], available, true), EU)).toBe(available)

    const tooNarrow = fittedProductColumnWidths([...EU], 900, true)
    expect(tooNarrow).toEqual(minimumsEu)
  })
})
