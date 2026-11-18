import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import CadastroPage from './CadastroPage'
import { installProductHandlers, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'

const VAT_VIEW = { market: 'EU', vat_rate: '23.00', can_edit: true, history: [] }

function installVat() {
  installProductHandlers({})
  server.use(http.get('*/markets/EU/vat-rate', () => HttpResponse.json(VAT_VIEW)))
}

describe('CadastroPage — aba IVA (taxa única de Portugal)', () => {
  it('o admin do EU vê a aba IVA e edita a taxa ali', async () => {
    installVat()
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'), ['/cadastros'])

    const tabs = await screen.findAllByRole('button', { name: /^IVA$/ })
    await userEvent.click(tabs[0])

    expect(await screen.findByTestId('eu-vat-current')).toHaveTextContent('23%')
    expect(screen.getByLabelText('Taxa de IVA (%)')).toBeInTheDocument()
  })

  it('o link /cadastros?aba=iva (destino do antigo /iva) abre direto na aba IVA', async () => {
    installVat()
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'), ['/cadastros?aba=iva'])

    expect(await screen.findByTestId('eu-vat-current')).toHaveTextContent('23%')
  })

  it('quem não é admin do EU não vê a aba nem abre o IVA pelo link', async () => {
    installVat()
    renderProductPage(<CadastroPage />, productTestUser('vendedor', 'EU'), ['/cadastros?aba=iva'])

    await screen.findAllByRole('button', { name: /Produtos/ })
    expect(screen.queryByRole('button', { name: /^IVA$/ })).not.toBeInTheDocument()
    expect(screen.queryByTestId('eu-vat-current')).not.toBeInTheDocument()
  })

  it('o admin do Brasil não tem aba IVA', async () => {
    installProductHandlers({})
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'), ['/cadastros?aba=iva'])

    await screen.findAllByRole('button', { name: /Produtos/ })
    expect(screen.queryByRole('button', { name: /^IVA$/ })).not.toBeInTheDocument()
    expect(screen.queryByTestId('eu-vat-current')).not.toBeInTheDocument()
  })
})
