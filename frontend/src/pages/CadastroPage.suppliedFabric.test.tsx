import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CadastroPage from './CadastroPage'
import { installProductHandlers, productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import { server } from '../test/setup'
import type { Product } from '../types'

// Cadastro do TECIDO FORNECIDO na ficha do produto EU (Cadastro > Produtos).

const FABRIC_CATEGORY = { id: 'cat-tecidos', code: 'TECIDOS_IBTW', name: 'Tecidos IBTW' }
const APPLICATION = {
  id: 'app-tecido', category_id: 'cat-tecidos', category_code: 'TECIDOS_IBTW', category_name: 'Tecidos IBTW',
  name: 'Tecido', name_en: null, required: false, display_order: 0, allow_all: true, allow_repeat: true, allowed_optionals: [],
}

function sofa(withData: boolean, overrides: Record<string, unknown> = {}) {
  return productFixture('EU', {
    id: 'eu-sofa', product_code: 'SF0343', description: 'Sofá', description_pt_pt: 'Sofá', description_en: 'Sofa',
    market_prices: { lojista: 100, corporativo: 90, pvp: 120, arquiteto: 80 },
    optional_applications: [APPLICATION] as never[],
    supplied_fabric: withData
      ? { linear_meters: '13.20', prices: { lojista: '700.10', corporativo: '800.20', pvp: '1400.30', arquiteto: '900.40' } }
      : null,
    ...overrides,
  } as never) as unknown as Product
}

function install(product: Product) {
  const patch = vi.fn((_id: string, payload: Record<string, unknown>) => HttpResponse.json({ ...product, ...payload }))
  const put = vi.fn((_body: Record<string, unknown>) => HttpResponse.json({ linear_meters: '1', prices: {} }))
  const remove = vi.fn(() => new HttpResponse(null, { status: 204 }))
  installProductHandlers({ products: [product as never], onPatch: patch })
  server.use(
    http.get('*/optional-categories', () => HttpResponse.json([FABRIC_CATEGORY])),
    http.put('*/products/:id/supplied-fabric', async ({ request }) => put(await request.json() as Record<string, unknown>)),
    http.delete('*/products/:id/supplied-fabric', () => remove()),
  )
  return { patch, put, remove }
}

async function openEdit(user: ReturnType<typeof userEvent.setup>) {
  await user.click((await screen.findAllByRole('button', { name: 'Editar' }))[0])
}

describe('CadastroPage — Tecido fornecido (EU)', () => {
  beforeEach(() => localStorage.clear())

  it('mostra a seção com os valores salvos e regrava tudo no PUT depois do PATCH', async () => {
    const user = userEvent.setup()
    const { patch, put } = install(sofa(true))
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await openEdit(user)

    expect(screen.getByLabelText('Tecido necessário (m)')).toHaveValue(13.2)
    expect(screen.getByLabelText('Sem tecido — PVP (€)')).toHaveValue(1400.3)
    expect(screen.getByLabelText('Sem tecido — Lojista (€)')).toHaveValue(700.1)
    expect(screen.getByLabelText('Sem tecido — Arquiteto (€)')).toHaveValue(900.4)
    expect(screen.getByLabelText('Sem tecido — Corporativo (€)')).toHaveValue(800.2)

    fireEvent.change(screen.getByLabelText('Sem tecido — Lojista (€)'), { target: { value: '650' } })
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    await waitFor(() => expect(put).toHaveBeenCalledOnce())
    expect(patch).toHaveBeenCalledOnce()
    expect(put.mock.calls[0][0]).toEqual({
      linear_meters: 13.2, price_lojista: 650, price_corporativo: 800.2, price_pvp: 1400.3, price_arquiteto: 900.4,
    })
  })

  it('produto com a categoria mas sem dados: avisa, não bloqueia o salvamento e não grava nada', async () => {
    const user = userEvent.setup()
    const { patch, put, remove } = install(sofa(false))
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await openEdit(user)

    expect(screen.getByText(/Para oferecer TECIDO FORNECIDO neste produto, preencha/)).toBeInTheDocument()
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)
    await waitFor(() => expect(patch).toHaveBeenCalledOnce())
    expect(put).not.toHaveBeenCalled()
    expect(remove).not.toHaveBeenCalled()
  })

  it('preencher os cinco campos de um produto sem dados grava com PUT', async () => {
    const user = userEvent.setup()
    const { put } = install(sofa(false))
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await openEdit(user)

    fireEvent.change(screen.getByLabelText('Tecido necessário (m)'), { target: { value: '10.4' } })
    fireEvent.change(screen.getByLabelText('Sem tecido — PVP (€)'), { target: { value: '3517.94' } })
    fireEvent.change(screen.getByLabelText('Sem tecido — Lojista (€)'), { target: { value: '1758.97' } })
    fireEvent.change(screen.getByLabelText('Sem tecido — Arquiteto (€)'), { target: { value: '2286.66' } })
    fireEvent.change(screen.getByLabelText('Sem tecido — Corporativo (€)'), { target: { value: '2638.45' } })
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    await waitFor(() => expect(put).toHaveBeenCalledOnce())
    expect(put.mock.calls[0][0]).toEqual({
      linear_meters: 10.4, price_lojista: 1758.97, price_corporativo: 2638.45, price_pvp: 3517.94, price_arquiteto: 2286.66,
    })
  })

  it('campos preenchidos pela metade bloqueiam o salvamento com mensagem', async () => {
    const user = userEvent.setup()
    const { patch, put } = install(sofa(false))
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await openEdit(user)

    fireEvent.change(screen.getByLabelText('Tecido necessário (m)'), { target: { value: '10.4' } })
    expect(await screen.findByText(/Falta preencher algum campo/)).toBeInTheDocument()
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)
    expect(await screen.findByText(/preencha a metragem e os quatro preços/)).toBeInTheDocument()
    expect(patch).not.toHaveBeenCalled()
    expect(put).not.toHaveBeenCalled()
  })

  it('esvaziar tudo num produto que tinha dados tira a opção (DELETE)', async () => {
    const user = userEvent.setup()
    const { remove, put } = install(sofa(true))
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await openEdit(user)

    for (const label of ['Tecido necessário (m)', 'Sem tecido — PVP (€)', 'Sem tecido — Lojista (€)', 'Sem tecido — Arquiteto (€)', 'Sem tecido — Corporativo (€)']) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: '' } })
    }
    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)
    await waitFor(() => expect(remove).toHaveBeenCalledOnce())
    expect(put).not.toHaveBeenCalled()
  })

  it('produto sem a categoria de tecidos IBTW não mostra a seção', async () => {
    const user = userEvent.setup()
    install(sofa(false, { optional_applications: [] }))
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))
    await openEdit(user)
    expect(screen.queryByLabelText('Tecido necessário (m)')).toBeNull()
  })

  it('quem não é admin/produtos não vê a seção', async () => {
    const user = userEvent.setup()
    install(sofa(true))
    renderProductPage(<CadastroPage />, productTestUser('vendedor', 'EU'))
    const edit = await screen.findAllByRole('button', { name: 'Editar' }).catch(() => [])
    if (edit.length) await user.click(edit[0])
    expect(screen.queryByLabelText('Tecido necessário (m)')).toBeNull()
  })

  it('no Brasil a seção não existe', async () => {
    const user = userEvent.setup()
    installProductHandlers({ products: [productFixture('BR', { id: 'br-1', optional_applications: [APPLICATION] as never[] })] })
    server.use(http.get('*/optional-categories', () => HttpResponse.json([FABRIC_CATEGORY])))
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))
    await user.click((await screen.findAllByRole('button', { name: 'Editar' }))[0])
    expect(screen.queryByLabelText('Tecido necessário (m)')).toBeNull()
  })
})
