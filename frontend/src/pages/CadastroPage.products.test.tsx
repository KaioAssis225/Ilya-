import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import CadastroPage from './CadastroPage'
import {
  installProductHandlers,
  productFixture,
  productTestUser,
  renderProductPage,
} from '../test/productTestUtils'

async function clickNewProduct(user: ReturnType<typeof userEvent.setup>) {
  const button = await waitFor(() => Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find((candidate) => candidate.textContent?.includes('Novo Produto')))
  if (!button) throw new Error('Botão Novo Produto não foi renderizado')
  await user.click(button)
}

// Escopo do P05: os contratos HTTP abaixo provam a autorização real no backend.
// A revisão detectou que CadastroPage ainda mostra controles de mutação a papéis
// sem permissão efetiva. O plano determina PR próprio para defeitos funcionais;
// registrar para correção separada: ocultar criar/editar/excluir conforme os
// guards por mercado sem alterar este branch de regressão.
describe('CadastroPage de produtos em DOM', () => {
  it('REG-PROD-01: formulário BR envia payload sem traduções exclusivas EU', async () => {
    const user = userEvent.setup()
    const create = vi.fn((payload: Record<string, unknown>) => HttpResponse.json(
      { ...productFixture('BR'), ...payload, id: 'created-br' }, { status: 201 },
    ))
    installProductHandlers({ onCreate: create })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    await clickNewProduct(user)
    await user.type(screen.getByLabelText('Código *'), 'BR-FORM-01')
    await user.type(screen.getByLabelText(/Preço Lojista/), '100')
    await user.type(screen.getByLabelText(/Preço Corporativo/), '90')
    await user.type(screen.getByLabelText('Descrição *'), 'Mesa brasileira')
    expect(screen.queryByLabelText('Nome em inglês *')).not.toBeInTheDocument()
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    await waitFor(() => expect(create).toHaveBeenCalledOnce())
    const payload = create.mock.calls[0][0]
    expect(payload).toMatchObject({ product_code: 'BR-FORM-01', description: 'Mesa brasileira' })
    expect(payload).not.toHaveProperty('description_pt_pt')
    expect(payload).not.toHaveProperty('description_en')
  })

  it('REG-PROD-02: formulário EU exibe os nomes e envia descrição PT e inglês', async () => {
    const user = userEvent.setup()
    const create = vi.fn((payload: Record<string, unknown>) => HttpResponse.json(
      { ...productFixture('EU'), ...payload, id: 'created-eu' }, { status: 201 },
    ))
    installProductHandlers({ onCreate: create })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    await clickNewProduct(user)
    expect(screen.getByLabelText('Nome em inglês *')).toBeVisible()
    await user.type(screen.getByLabelText('Código *'), 'EU-FORM-01')
    await user.type(screen.getByLabelText(/Preço Lojista/), '100')
    await user.type(screen.getByLabelText(/Preço Corporativo/), '90')
    await user.type(screen.getByLabelText(/Preço PVP/), '120')
    await user.type(screen.getByLabelText(/Preço Arquiteto/), '80')
    await user.type(screen.getByLabelText('Descrição *'), 'Mesa em português')
    await user.type(screen.getByLabelText('Nome em inglês *'), 'Table in English')
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    await waitFor(() => expect(create).toHaveBeenCalledOnce())
    expect(create.mock.calls[0][0]).toMatchObject({
      product_code: 'EU-FORM-01',
      description: 'Mesa em português',
      description_pt_pt: 'Mesa em português',
      description_en: 'Table in English',
      price_arquiteto: 80,
    })
  })

  it('REG-PROD-03: edição carrega e reenvia traduções e preço Arquiteto', async () => {
    const user = userEvent.setup()
    const product = productFixture('EU', {
      id: 'eu-edit-1', product_code: 'EU-EDIT-01',
      description: 'Mesa portuguesa', description_pt_pt: 'Mesa portuguesa',
      description_en: 'Portuguese table',
      market_prices: { lojista: 100, corporativo: 90, pvp: 120, arquiteto: 80 },
    })
    const patch = vi.fn((_id: string, payload: Record<string, unknown>) =>
      HttpResponse.json({ ...product, ...payload }),
    )
    installProductHandlers({ products: [product], onPatch: patch })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    const editButtons = await screen.findAllByRole('button', { name: 'Editar' })
    await user.click(editButtons[0])
    expect(screen.getByLabelText('Descrição *')).toHaveValue('Mesa portuguesa')
    expect(screen.getByLabelText('Nome em inglês *')).toHaveValue('Portuguese table')
    expect(screen.getByLabelText(/Preço Arquiteto/)).toHaveValue(80)
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    await waitFor(() => expect(patch).toHaveBeenCalledOnce())
    expect(patch.mock.calls[0][1]).toMatchObject({
      description: 'Mesa portuguesa',
      description_pt_pt: 'Mesa portuguesa',
      description_en: 'Portuguese table',
      price_arquiteto: 80,
    })
  })


  it('REG-PROD-04: erro 422 continua visível no formulário e permite corrigir', async () => {
    const user = userEvent.setup()
    const create = vi.fn(() => HttpResponse.json(
      { detail: 'Nome em inglês inválido.' }, { status: 422 },
    ))
    installProductHandlers({ onCreate: create })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    await clickNewProduct(user)
    await user.type(screen.getByLabelText('Código *'), 'EU-INVALID-01')
    await user.type(screen.getByLabelText(/Preço Lojista/), '100')
    await user.type(screen.getByLabelText(/Preço Corporativo/), '90')
    await user.type(screen.getByLabelText(/Preço PVP/), '120')
    await user.type(screen.getByLabelText(/Preço Arquiteto/), '80')
    await user.type(screen.getByLabelText('Descrição *'), 'Mesa portuguesa')
    await user.type(screen.getByLabelText('Nome em inglês *'), 'Table')
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    expect(await screen.findByText('Nome em inglês inválido.')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Novo Produto em Portugal' })).toBeVisible()
  })
})