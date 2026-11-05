import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
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
  id: 'order-1', code: 'PED-0001', items: [item('i1', 'MESA-1', 1), item('i2', 'CAD-2', 4)],
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

  it('só escolhe os itens e abre a tela de orçamento NOVO (?copy=), sem criar nada nem usar ?edit=', async () => {
    const user = userEvent.setup()
    let posts = 0
    server.use(
      http.post('*/orders/order-1/copy', () => { posts += 1; return HttpResponse.json({}, { status: 201 }) }),
      http.post('*/orders', () => { posts += 1; return HttpResponse.json({}, { status: 201 }) }),
    )
    renderModal()

    // Começa com tudo marcado; "Selecionar todos" limpa e remarca.
    const all = screen.getByLabelText('Selecionar todos')
    expect(all).toBeChecked()
    await user.click(all)
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeDisabled()
    await user.click(screen.getByLabelText(/CAD-2/))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    expect(await screen.findByText('destino:/orcamentos?copy=order-1&items=i2')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(posts).toBe(0)
  })

  it('leva todos os itens marcados, na ordem do pedido', async () => {
    const user = userEvent.setup()
    renderModal(true)

    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    expect(await screen.findByText('destino:/orcamentos?copy=order-1&items=i1,i2')).toBeInTheDocument()
  })
})
