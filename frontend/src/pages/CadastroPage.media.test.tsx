import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import CadastroPage from './CadastroPage'
import { server } from '../test/setup'
import {
  installProductHandlers,
  productFixture,
  productTestUser,
  renderProductPage,
  type ProductFixture,
} from '../test/productTestUtils'

// P06: upload, preview e exclusão de foto no formulário de produto. O contrato
// de storage (buckets BR/EU, thumbnails, 503) é provado em
// backend/tests/integration/test_media_storage.py; aqui só o DOM e as chamadas.

const SIGNED_PHOTO = '/api/v1/media/products/p06-atual.png?expires=1&signature=p06'

const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL
let revokeObjectURL: Mock<(url: string) => void>

beforeEach(() => {
  // jsdom não implementa object URLs; o preview depende deles.
  URL.createObjectURL = vi.fn((obj: Blob | MediaSource) => `blob:p06/${obj instanceof File ? obj.name : 'blob'}`)
  revokeObjectURL = vi.fn<(url: string) => void>()
  URL.revokeObjectURL = revokeObjectURL
})

afterEach(() => {
  // Desmonta antes de restaurar: o efeito de limpeza do preview chama revokeObjectURL.
  cleanup()
  URL.createObjectURL = originalCreateObjectURL
  URL.revokeObjectURL = originalRevokeObjectURL
  vi.restoreAllMocks()
})

function pngFile(name: string) {
  return new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])], name, { type: 'image/png' })
}

/** Registra upload/exclusão de foto em ordem, junto das mutações do produto. */
function installPhotoHandlers(options: {
  market: 'BR' | 'EU'
  calls: string[]
  onUpload?: () => Response
}) {
  // A captura pelo FormData independe de como o jsdom serializa o multipart.
  const append = vi.spyOn(FormData.prototype, 'append')
  server.use(
    http.post('*/products/:id/upload-photo', ({ params }) => {
      options.calls.push(`upload:${String(params.id)}`)
      return options.onUpload?.() ?? HttpResponse.json(productFixture(options.market, {
        id: String(params.id), photo_url: SIGNED_PHOTO, thumbnail_url: SIGNED_PHOTO,
      }))
    }),
    http.delete('*/products/:id/photo', ({ params }) => {
      options.calls.push(`delete-photo:${String(params.id)}`)
      return HttpResponse.json(productFixture(options.market, {
        id: String(params.id), photo_url: null, thumbnail_url: null,
      }))
    }),
  )
  return {
    uploadedFileNames: () => append.mock.calls
      .filter(([field, value]) => field === 'file' && value instanceof File)
      .map(([, value]) => (value as File).name),
  }
}

function productForm() {
  const form = screen.getByLabelText('Código *').closest('form')
  if (!form) throw new Error('Formulário de produto não encontrado')
  return form
}

function photoInput() {
  const input = productForm().querySelector<HTMLInputElement>('input[type="file"]')
  if (!input) throw new Error('Campo de foto não encontrado')
  return input
}

async function clickNewProduct(user: ReturnType<typeof userEvent.setup>) {
  const button = await waitFor(() => Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find((candidate) => candidate.textContent?.includes('Novo Produto')))
  if (!button) throw new Error('Botão Novo Produto não foi renderizado')
  await user.click(button)
}

async function fillNewBrProduct(user: ReturnType<typeof userEvent.setup>, code: string, description: string) {
  await clickNewProduct(user)
  await user.type(screen.getByLabelText('Código *'), code)
  await user.type(screen.getByLabelText(/Preço Lojista/), '100')
  await user.type(screen.getByLabelText(/Preço Corporativo/), '90')
  await user.type(screen.getByLabelText('Descrição *'), description)
}

async function openEdit(user: ReturnType<typeof userEvent.setup>) {
  const editButtons = await screen.findAllByRole('button', { name: 'Editar' })
  await user.click(editButtons[0])
}

function installBrCreate(calls: string[]) {
  installProductHandlers({
    onCreate: (payload) => {
      calls.push('create')
      return HttpResponse.json({ ...productFixture('BR'), ...payload, id: 'created-br' }, { status: 201 })
    },
  })
}

function installEuEdit(calls: string[], overrides: Partial<ProductFixture> = {}) {
  const product = productFixture('EU', {
    id: 'eu-photo-1', product_code: 'EU-FOTO-01',
    description: 'Mesa com foto', description_pt_pt: 'Mesa com foto', description_en: 'Table with photo',
    photo_url: SIGNED_PHOTO, thumbnail_url: SIGNED_PHOTO,
    ...overrides,
  })
  installProductHandlers({
    products: [product],
    onPatch: (id, payload) => {
      calls.push(`patch:${id}`)
      return HttpResponse.json({ ...product, ...payload })
    },
  })
}

describe('CadastroPage — foto do produto', () => {
  it('REG-MEDIA-FE-01: novo produto BR mostra preview e envia a foto após criar', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    installBrCreate(calls)
    const photos = installPhotoHandlers({ market: 'BR', calls })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    await fillNewBrProduct(user, 'BR-FOTO-01', 'Mesa com foto')
    expect(screen.getByText('JPG, PNG, WEBP — máx. 5MB')).toBeVisible()

    await user.upload(photoInput(), pngFile('mesa.png'))

    expect(screen.getByRole('img', { name: 'Mesa com foto' })).toHaveAttribute('src', 'blob:p06/mesa.png')
    expect(screen.getByText('Clique para trocar')).toBeVisible()
    expect(calls).toEqual([])

    fireEvent.submit(productForm())

    await waitFor(() => expect(calls).toEqual(['create', 'upload:created-br']))
    expect(photos.uploadedFileNames()).toEqual(['mesa.png'])
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Novo Produto' })).not.toBeInTheDocument())
  })

  it('REG-MEDIA-FE-02: remover foto pendente de produto novo não envia upload', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    installBrCreate(calls)
    installPhotoHandlers({ market: 'BR', calls })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    await fillNewBrProduct(user, 'BR-FOTO-02', 'Mesa sem foto')
    await user.upload(photoInput(), pngFile('descartada.png'))
    await user.click(screen.getByRole('button', { name: 'Remover foto' }))

    expect(screen.queryByRole('img', { name: 'Mesa sem foto' })).not.toBeInTheDocument()
    // Sem foto salva não há o que remover no servidor: nenhum aviso.
    expect(screen.queryByText('A foto será removida ao salvar.')).not.toBeInTheDocument()
    expect(photoInput().value).toBe('')
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:p06/descartada.png'))

    fireEvent.submit(productForm())

    await waitFor(() => expect(calls).toEqual(['create']))
  })

  it('REG-MEDIA-FE-03: edição EU carrega a foto atual e exclui no servidor só ao salvar', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    installEuEdit(calls)
    installPhotoHandlers({ market: 'EU', calls })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    await openEdit(user)
    expect(screen.getByRole('img', { name: 'Mesa com foto' })).toHaveAttribute('src', SIGNED_PHOTO)

    await user.click(screen.getByRole('button', { name: 'Remover foto' }))

    expect(screen.queryByRole('img', { name: 'Mesa com foto' })).not.toBeInTheDocument()
    expect(screen.getByText('A foto será removida ao salvar.')).toBeVisible()
    expect(calls).toEqual([])
    // URL assinada do servidor não é object URL: nada a revogar.
    expect(revokeObjectURL).not.toHaveBeenCalled()

    fireEvent.submit(productForm())

    await waitFor(() => expect(calls).toEqual(['patch:eu-photo-1', 'delete-photo:eu-photo-1']))
  })

  it('REG-MEDIA-FE-04: trocar a foto na edição envia upload, revoga o preview anterior e não exclui', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    installEuEdit(calls)
    const photos = installPhotoHandlers({ market: 'EU', calls })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    await openEdit(user)
    await user.upload(photoInput(), pngFile('primeira.png'))
    expect(screen.getByRole('img', { name: 'Mesa com foto' })).toHaveAttribute('src', 'blob:p06/primeira.png')
    await user.upload(photoInput(), pngFile('segunda.png'))

    expect(screen.getByRole('img', { name: 'Mesa com foto' })).toHaveAttribute('src', 'blob:p06/segunda.png')
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:p06/primeira.png'))
    expect(screen.queryByText('A foto será removida ao salvar.')).not.toBeInTheDocument()

    fireEvent.submit(productForm())

    await waitFor(() => expect(calls).toEqual(['patch:eu-photo-1', 'upload:eu-photo-1']))
    expect(photos.uploadedFileNames()).toEqual(['segunda.png'])
  })

  it('REG-MEDIA-FE-05: escolher nova foto depois de remover cancela a exclusão', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    installEuEdit(calls)
    installPhotoHandlers({ market: 'EU', calls })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    await openEdit(user)
    await user.click(screen.getByRole('button', { name: 'Remover foto' }))
    expect(screen.getByText('A foto será removida ao salvar.')).toBeVisible()
    await user.upload(photoInput(), pngFile('nova.png'))

    expect(screen.queryByText('A foto será removida ao salvar.')).not.toBeInTheDocument()
    fireEvent.submit(productForm())

    await waitFor(() => expect(calls).toEqual(['patch:eu-photo-1', 'upload:eu-photo-1']))
  })

  it('REG-MEDIA-FE-06: falha do upload mantém o formulário aberto com o erro do servidor', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    installEuEdit(calls)
    installPhotoHandlers({
      market: 'EU',
      calls,
      onUpload: () => HttpResponse.json(
        { detail: 'Armazenamento de fotos do mercado europeu não configurado.' }, { status: 503 },
      ),
    })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'EU'))

    await openEdit(user)
    await user.upload(photoInput(), pngFile('mesa.png'))
    fireEvent.submit(productForm())

    expect(await screen.findByText('Armazenamento de fotos do mercado europeu não configurado.')).toBeVisible()
    expect(calls).toEqual(['patch:eu-photo-1', 'upload:eu-photo-1'])
    expect(screen.getByRole('heading', { name: 'Editar Produto' })).toBeVisible()
    expect(screen.getByRole('img', { name: 'Mesa com foto' })).toHaveAttribute('src', 'blob:p06/mesa.png')
  })
})

describe('CadastroPage — miniatura da lista', () => {
  const THUMB = '/api/v1/media/product-thumbnails/legada.png.webp?expires=1&signature=t'

  it('REG-MEDIA-FE-07: miniatura que falha cai para a foto original uma única vez', async () => {
    installProductHandlers({
      products: [productFixture('BR', { photo_url: SIGNED_PHOTO, thumbnail_url: THUMB })],
    })
    renderProductPage(<CadastroPage />, productTestUser('admin', 'BR'))

    const image = await screen.findByRole('img', { name: 'Foto de P05-BR-SKU' })
    expect(image).toHaveAttribute('src', THUMB)

    fireEvent.error(image)
    await waitFor(() => expect(image).toHaveAttribute('src', SIGNED_PHOTO))

    // A original também falhou: nada de alternar de volta para a miniatura.
    fireEvent.error(image)
    fireEvent.error(image)
    expect(screen.getByRole('img', { name: 'Foto de P05-BR-SKU' })).toHaveAttribute('src', SIGNED_PHOTO)
  })
})
