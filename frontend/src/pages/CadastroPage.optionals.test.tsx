import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import CadastroPage from './CadastroPage'
import {
  installProductHandlers,
  productFixture,
  productTestUser,
  renderProductPage,
} from '../test/productTestUtils'
import { server } from '../test/setup'

async function clickNewProduct(user: ReturnType<typeof userEvent.setup>) {
  const button = await waitFor(() => {
    const candidate = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find(
      (el) => el.textContent?.includes('Novo Produto'),
    )
    expect(candidate).toBeTruthy()
    return candidate
  })
  if (!button) throw new Error('Botão Novo Produto não foi renderizado')
  await user.click(button)
}

describe('CadastroPage aplicações de opcionais independentes (BR)', () => {
  it('cadastra a marca explicitamente e permite alterá-la sem perder o nome e o ID', async () => {
    const user = userEvent.setup()
    const record = { id: 'optional-brand', category: 'COR', color_name: 'Areia', brand: 'ILYA', photo_url: null }
    const create = vi.fn((payload: Record<string, unknown>) => HttpResponse.json({ ...record, ...payload }, { status: 201 }))
    const update = vi.fn((payload: Record<string, unknown>) => HttpResponse.json({ ...record, ...payload }))
    installProductHandlers({ products: [] })
    server.use(
      http.get('*/optional-categories', () => HttpResponse.json([{ id: 'cat', code: 'COR', name: 'Cor', display_order: 0 }])),
      http.get('*/optionals', () => HttpResponse.json([record])),
      http.post('*/optionals', async ({ request }) => create(await request.json() as Record<string, unknown>)),
      http.patch('*/optionals/:id', async ({ request }) => update(await request.json() as Record<string, unknown>)),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))
    await user.click((await screen.findAllByRole('button', { name: /^Opcionais/ }))[0])
    await user.click(await screen.findByRole('button', { name: 'Novo Opcional' }))
    await user.selectOptions(screen.getByLabelText('Marca *'), 'IBTW')
    await user.type(screen.getByLabelText('Nome da Cor *'), 'Nova cor')
    await user.click(screen.getByRole('button', { name: 'Criar' }))
    await waitFor(() => expect(create).toHaveBeenCalledWith({ category: 'COR', color_name: 'Nova cor', brand: 'IBTW' }))
    const brands = screen.getByRole('group', { name: 'Marca dos opcionais' })
    await user.click(within(brands).getByRole('button', { name: /ILYA/ }))
    await user.click(await screen.findByRole('button', { name: 'Editar' }))
    expect(screen.getByLabelText('Nome da Cor *')).toHaveValue('Areia')
    await user.selectOptions(screen.getByLabelText('Marca *'), 'IBTW')
    await user.click(screen.getByRole('button', { name: 'Salvar' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith({ category: 'COR', color_name: 'Areia', brand: 'IBTW' }))
  })
  it('REG-PROD-OPT-01: duas aplicações da mesma categoria ficam independentes no payload', async () => {
    const user = userEvent.setup()
    const create = vi.fn((payload: Record<string, unknown>) =>
      HttpResponse.json({ ...productFixture('BR'), ...payload, id: 'created-opt' }, { status: 201 }),
    )
    installProductHandlers({
      onCreate: create,
      catalogs: [],
      products: [],
    })
    server.use(
      http.get('*/optional-categories', () =>
        HttpResponse.json([{ id: 'cat-cor', code: 'COR', name: 'Cor' }]),
      ),
      http.get('*/optionals', () =>
        HttpResponse.json([
          { id: 'opt-azul', category: 'COR', color_name: 'Azul', photo_url: null },
          { id: 'opt-verde', category: 'COR', color_name: 'Verde', photo_url: null },
        ]),
      ),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    await clickNewProduct(user)
    await user.type(screen.getByLabelText('Código *'), 'BR-OPT-01')
    await user.type(screen.getByLabelText(/Preço Lojista/), '100')
    await user.type(screen.getByLabelText(/Preço Corporativo/), '90')
    await user.type(screen.getByLabelText('Descrição *'), 'Produto com opcionais')

    const categoriaCor = await screen.findByRole('checkbox', { name: /Cor/i })
    await user.click(categoriaCor)

    const group = await screen.findByRole('region', {
      name: 'Aplicações do opcional Cor',
    })
    expect(within(group).getByRole('button', { name: 'Adicionar outra aplicação' })).toBeInTheDocument()

    await user.click(within(group).getByRole('button', { name: 'Adicionar outra aplicação' }))

    const nameInputs = await within(group).findAllByLabelText('Nome exibido *')
    expect(nameInputs).toHaveLength(1)
    await user.type(nameInputs[0], 'Pintura A')

    await user.click(within(group).getByRole('button', { name: 'Adicionar outra aplicação' }))

    const updatedNameInputs = await within(group).findAllByLabelText('Nome exibido *')
    expect(updatedNameInputs).toHaveLength(2)
    await user.clear(updatedNameInputs[1])
    await user.type(updatedNameInputs[1], 'Pintura B')

    expect(updatedNameInputs[0]).toHaveValue('Pintura A')
    expect(updatedNameInputs[1]).toHaveValue('Pintura B')

    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    await waitFor(() => expect(create).toHaveBeenCalledOnce())
    const payload = create.mock.calls[0][0] as Record<string, unknown>
    const applications = (payload.optional_applications ?? []) as Array<Record<string, unknown>>
    expect(Array.isArray(applications)).toBe(true)
    const categoriaApplications = applications.filter((app) => app.category_id === 'cat-cor')
    expect(categoriaApplications).toHaveLength(2)
    expect(categoriaApplications.map((app) => app.name)).toEqual(['Pintura A', 'Pintura B'])
  })

  it('REG-PROD-OPT-02: remover uma aplicação da categoria não remove a outra', async () => {
    const user = userEvent.setup()
    const create = vi.fn((payload: Record<string, unknown>) =>
      HttpResponse.json({ ...productFixture('BR'), ...payload, id: 'created-opt-remove' }, { status: 201 }),
    )
    installProductHandlers({ onCreate: create })
    server.use(
      http.get('*/optional-categories', () =>
        HttpResponse.json([{ id: 'cat-cor', code: 'COR', name: 'Cor' }]),
      ),
      http.get('*/optionals', () =>
        HttpResponse.json([
          { id: 'opt-azul', category: 'COR', color_name: 'Azul', photo_url: null },
          { id: 'opt-verde', category: 'COR', color_name: 'Verde', photo_url: null },
        ]),
      ),
    )
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    await clickNewProduct(user)
    await user.type(screen.getByLabelText('Código *'), 'BR-OPT-02')
    await user.type(screen.getByLabelText(/Preço Lojista/), '100')
    await user.type(screen.getByLabelText(/Preço Corporativo/), '90')
    await user.type(screen.getByLabelText('Descrição *'), 'Produto com duas aplicações')

    const categoriaCor = await screen.findByRole('checkbox', { name: /Cor/i })
    await user.click(categoriaCor)

    const group = await screen.findByRole('region', {
      name: 'Aplicações do opcional Cor',
    })

    await user.click(within(group).getByRole('button', { name: 'Adicionar outra aplicação' }))

    const firstNames = await within(group).findAllByLabelText('Nome exibido *')
    await user.type(firstNames[0], 'Pintura A')

    await user.click(within(group).getByRole('button', { name: 'Adicionar outra aplicação' }))

    const namesBefore = await within(group).findAllByLabelText('Nome exibido *')
    expect(namesBefore).toHaveLength(2)
    await user.clear(namesBefore[1])
    await user.type(namesBefore[1], 'Pintura B')

    const removeButtons = within(group).getAllByRole('button', { name: /Remover aplicação/i })
    expect(removeButtons).toHaveLength(2)
    await user.click(removeButtons[0])

    await waitFor(() => {
      expect(within(group).queryAllByLabelText('Nome exibido *')).toHaveLength(1)
    })
    expect(within(group).getByLabelText('Nome exibido *')).toHaveValue('Pintura B')

    fireEvent.submit(screen.getByLabelText('Código *').closest('form')!)

    await waitFor(() => expect(create).toHaveBeenCalledOnce())
    const payload = create.mock.calls[0][0] as Record<string, unknown>
    const applications = (payload.optional_applications ?? []) as Array<Record<string, unknown>>
    expect(Array.isArray(applications)).toBe(true)
    const categoriaApplications = applications.filter((app) => app.category_id === 'cat-cor')
    expect(categoriaApplications).toHaveLength(1)
    expect(categoriaApplications[0]).toMatchObject({ name: 'Pintura B' })
  })
})
