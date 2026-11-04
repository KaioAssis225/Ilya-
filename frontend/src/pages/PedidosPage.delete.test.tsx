import { beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import PedidosPage from './PedidosPage'
import type { OrderSummary } from '../types'

const summary: OrderSummary = {
  id: 'order-1',
  code: 'PED-0001',
  orc_id: 'ORC-0001',
  market_code: 'BR',
  currency: 'BRL',
  client_id: 'client-1',
  client_name: 'Cliente Teste',
  rep_id: 'rep-1',
  rep_name: 'Representante Teste',
  total_value: 100,
  total_with_ipi: 100,
  is_finalized: true,
  is_cancelled: false,
  finalized_at: '2024-01-02T00:00:00.000Z',
  cancelled_at: null,
  order_stage: 'production',
  items: [],
  created_at: '2024-01-01T00:00:00.000Z',
}

function installBackend(status: number, body: Record<string, unknown> | null) {
  const deletes: string[] = []
  server.use(
    http.get('*/orders', () => HttpResponse.json([summary], { headers: { 'X-Has-More': 'false' } })),
    http.get('*/optional-categories', () => HttpResponse.json([])),
    http.get('*/orders/history', () => HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })),
    http.delete('*/orders/:id', ({ params }) => {
      deletes.push(String(params.id))
      return body === null ? new HttpResponse(null, { status }) : HttpResponse.json(body, { status })
    }),
  )
  return deletes
}

async function openDeleteDialog() {
  renderProductPage(<PedidosPage scope="orders" />, productTestUser('admin', 'BR'))
  const [trigger] = await screen.findAllByLabelText(`Excluir orçamento ${summary.code}`)
  await userEvent.click(trigger)
  return screen.getByText('Confirmar exclusão').closest('div') as HTMLElement
}

describe('PedidosPage: exclusão de pedido', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('mostra no modal o motivo devolvido pela API quando o pedido não pode ser excluído', async () => {
    const message = 'Pedido já tem documento no Moloni e não pode ser excluído.'
    const deletes = installBackend(409, { detail: message })
    const dialog = await openDeleteDialog()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Excluir' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(deletes).toEqual(['order-1'])
    expect(screen.getByText('Confirmar exclusão')).toBeInTheDocument()
  })

  it('usa mensagem genérica quando a API não explica o erro', async () => {
    installBackend(500, {})
    const dialog = await openDeleteDialog()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Excluir' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível excluir o pedido.')
  })

  it('fecha o modal quando a exclusão dá certo', async () => {
    installBackend(204, null)
    const dialog = await openDeleteDialog()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Excluir' }))

    await waitFor(() => expect(screen.queryByText('Confirmar exclusão')).not.toBeInTheDocument())
  })
})
