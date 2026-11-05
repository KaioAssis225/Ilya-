import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes, useLocation } from 'react-router'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import { CopyOrderModal } from './CopyOrderModal'
import type { Order } from '../types'

const item = (id: string, code: string, qty: number) => ({
  id, order_id: 'order-1', product_code: code, description: `Produto ${code}`, qty,
}) as unknown as Order['items'][number]

const source = {
  id: 'order-1', code: 'PED-0001', catalog_name: 'IBTW', price_list_code: 'corporativo', items: [item('i1', 'MESA-1', 1), item('i2', 'CAD-2', 4)],
} as unknown as Order

const sourceWithSpecial = {
  id: 'order-special', code: 'PED-0002', items: [
    { ...item('i-special', 'PAI', 1), is_special: true, special_code: 'PAI-E1', description: 'ESPECIAL - Mesa Portugal' },
  ],
} as unknown as Order

function Landing() {
  const location = useLocation()
  return <p>destino:{location.pathname}{location.search}</p>
}

function renderModal(english = false) {
  return renderProductPage(
    <Routes>
      <Route path="/" element={<CopyOrderModal order={source} english={english} onClose={() => {}} />} />
      <Route path="/orcamentos" element={<Landing />} />
    </Routes>,
    productTestUser('admin', 'BR'),
  )
}

describe('CopyOrderModal', () => {
  it('mostra o código e o badge do especial no item copiado', () => {
    renderProductPage(
      <CopyOrderModal order={sourceWithSpecial} english={false} onClose={() => {}} />,
      productTestUser('admin', 'EU'),
    )

    expect(screen.getByText('PAI-E1')).toBeInTheDocument()
    expect(screen.getByText('ESPECIAL')).toBeInTheDocument()
    expect(screen.getByText('ESPECIAL - Mesa Portugal')).toBeInTheDocument()
  })

  it('envia só os itens marcados e abre o orçamento novo', async () => {
    const user = userEvent.setup()
    let body: unknown = null
    server.use(http.post('*/orders/order-1/copy', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ order: { id: 'novo-1', code: 'PED-0002' }, skipped: [] }, { status: 201 })
    }))
    renderModal()

    // Começa com tudo marcado; "Selecionar todos" limpa e remarca.
    const all = screen.getByLabelText('Selecionar todos')
    expect(all).toBeChecked()
    await user.click(all)
    expect(screen.getByRole('button', { name: 'Criar orçamento' })).toBeDisabled()
    await user.click(screen.getByLabelText(/CAD-2/))
    await user.click(screen.getByRole('button', { name: 'Criar orçamento' }))
    await user.click(await screen.findByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByText('destino:/orcamentos?edit=novo-1')).toBeInTheDocument()
    expect(body).toEqual({ item_ids: ['i2'] })
  })

  it('avisa os itens não copiados antes de abrir o orçamento', async () => {
    const user = userEvent.setup()
    server.use(http.post('*/orders/order-1/copy', () => HttpResponse.json({
      order: { id: 'novo-2', code: 'PED-0003' },
      skipped: [{ product_code: 'MESA-1', reason: 'Produto inativo ou fora do catálogo.' }],
    }, { status: 201 })))
    renderModal()

    await user.click(screen.getByRole('button', { name: 'Criar orçamento' }))
    await user.click(await screen.findByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('MESA-1: Produto inativo ou fora do catálogo.')
    await user.click(screen.getByRole('button', { name: 'Abrir orçamento' }))
    await waitFor(() => expect(screen.getByText('destino:/orcamentos?edit=novo-2')).toBeInTheDocument())
  })

  it('mostra o erro do servidor e mantém o modal aberto', async () => {
    const user = userEvent.setup()
    server.use(http.post('*/orders/order-1/copy', () => HttpResponse.json(
      { detail: 'Nenhum item pôde ser copiado: MESA-1: Produto indisponível neste mercado.' }, { status: 422 },
    )))
    renderModal(true)

    await user.click(screen.getByRole('button', { name: 'Create quote' }))
    await user.click(await screen.findByRole('button', { name: 'Confirm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nenhum item pôde ser copiado')
    expect(screen.getByRole('button', { name: 'Create quote' })).toBeInTheDocument()
  })

  it('confirma o catálogo e a tabela antes de criar; Voltar não cria e Confirmar cria', async () => {
    const user = userEvent.setup()
    let posts = 0
    server.use(http.post('*/orders/order-1/copy', () => {
      posts += 1
      return HttpResponse.json({ order: { id: 'novo-3', code: 'PED-0004' }, skipped: [] }, { status: 201 })
    }))
    renderModal()

    await user.click(screen.getByRole('button', { name: 'Criar orçamento' }))
    const dialog = await screen.findByRole('dialog', { name: 'Confirmar o catálogo' })
    expect(dialog).toHaveTextContent('Este orçamento será feito no catálogo IBTW, tabela Corporativo. Está correto?')
    expect(posts).toBe(0)

    await user.click(screen.getByRole('button', { name: 'Voltar' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Confirmar o catálogo' })).toBeNull())
    // O modal de cópia segue aberto e nada foi criado.
    expect(screen.getByRole('button', { name: 'Criar orçamento' })).toBeInTheDocument()
    expect(posts).toBe(0)

    await user.click(screen.getByRole('button', { name: 'Criar orçamento' }))
    await user.click(await screen.findByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText('destino:/orcamentos?edit=novo-3')).toBeInTheDocument()
    expect(posts).toBe(1)
  })

  it('em inglês o pop-up usa o texto em inglês', async () => {
    const user = userEvent.setup()
    renderModal(true)

    await user.click(screen.getByRole('button', { name: 'Create quote' }))
    expect(await screen.findByRole('dialog', { name: 'Confirm the catalogue' }))
      .toHaveTextContent('This quote will be made in the IBTW catalogue, price list Corporate. Is that correct?')
    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
  })
})
