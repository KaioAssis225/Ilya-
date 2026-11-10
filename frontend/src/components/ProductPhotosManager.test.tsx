import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { ProductPhotosManager, MAX_PRODUCT_PHOTOS } from './ProductPhotosManager'
import { server } from '../test/setup'
import { installProductHandlers, productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import type { Product, ProductPhoto } from '../types'

const PRODUCT_ID = 'prod-galeria'

function photo(id: string, position: number, isPrimary = false): ProductPhoto {
  return {
    id, position, is_primary: isPrimary,
    photo_url: `/media/${id}.jpg`, thumbnail_url: `/media/${id}-thumb.jpg`,
  }
}

function productWith(photos: ProductPhoto[]): Product {
  const primary = photos.find(item => item.is_primary)
  return {
    ...productFixture('BR', { id: PRODUCT_ID }),
    photo_url: primary?.photo_url ?? null,
    thumbnail_url: primary?.thumbnail_url ?? null,
    photos,
    photo_count: photos.length,
  } as unknown as Product
}

const THREE = [photo('a', 0, true), photo('b', 1), photo('c', 2)]

function pngFile(name: string) {
  return new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, { type: 'image/png' })
}

function renderManager(photos = THREE, onUpdated = vi.fn()) {
  installProductHandlers()
  const user = userEvent.setup()
  renderProductPage(
    <ProductPhotosManager product={productWith(photos)} color="#b8860b" onUpdated={onUpdated} />,
    productTestUser('admin', 'BR'),
  )
  return { user, onUpdated }
}

const tiles = () => within(screen.getByRole('list', { name: 'Fotos do produto' })).getAllByRole('listitem')

describe('ProductPhotosManager', () => {
  it('lista as fotos, marca a principal e só oferece "definir principal" nas outras', () => {
    renderManager()

    expect(tiles()).toHaveLength(3)
    expect(within(tiles()[0]).getByText('Principal')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Definir a foto 1 como principal' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Definir a foto 2 como principal' })).toBeEnabled()
    expect(screen.getByText(/3 de 10 fotos/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mover a foto 1 para a esquerda' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Mover a foto 3 para a direita' })).toBeDisabled()
  })

  it('define a principal pelo servidor e mostra o que ele devolveu', async () => {
    const calls: string[] = []
    const { user, onUpdated } = renderManager()
    server.use(http.put('*/products/:id/photos/:photoId/primary', ({ params }) => {
      calls.push(`primary:${String(params.photoId)}`)
      return HttpResponse.json(productWith([photo('a', 0), photo('b', 1, true), photo('c', 2)]))
    }))

    await user.click(screen.getByRole('button', { name: 'Definir a foto 2 como principal' }))

    await waitFor(() => expect(within(tiles()[1]).getByText('Principal')).toBeInTheDocument())
    expect(calls).toEqual(['primary:b'])
    expect(within(tiles()[0]).queryByText('Principal')).not.toBeInTheDocument()
    expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ photo_url: '/media/b.jpg' }))
  })

  it('pede confirmação antes de remover e só então chama o servidor', async () => {
    const calls: string[] = []
    const { user } = renderManager()
    server.use(http.delete('*/products/:id/photos/:photoId', ({ params }) => {
      calls.push(`delete:${String(params.photoId)}`)
      return HttpResponse.json(productWith([photo('a', 0, true), photo('c', 1)]))
    }))

    await user.click(screen.getByRole('button', { name: 'Remover a foto 2 da galeria' }))
    expect(calls).toEqual([])
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('button', { name: 'Confirmar a remoção da foto 2' })).not.toBeInTheDocument()
    expect(calls).toEqual([])

    await user.click(screen.getByRole('button', { name: 'Remover a foto 2 da galeria' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar a remoção da foto 2' }))

    await waitFor(() => expect(tiles()).toHaveLength(2))
    expect(calls).toEqual(['delete:b'])
  })

  it('reordena trocando vizinhas e envia a lista completa de ids', async () => {
    const bodies: unknown[] = []
    const { user } = renderManager()
    server.use(http.put('*/products/:id/photos/order', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json(productWith([photo('b', 0), photo('a', 1, true), photo('c', 2)]))
    }))

    await user.click(screen.getByRole('button', { name: 'Mover a foto 1 para a direita' }))

    await waitFor(() => expect(bodies).toEqual([{ photo_ids: ['b', 'a', 'c'] }]))
    await waitFor(() => expect(within(tiles()[1]).getByText('Principal')).toBeInTheDocument())
  })

  it('envia várias fotos em fila, uma por requisição', async () => {
    const order: string[] = []
    const { user } = renderManager([photo('a', 0, true)])
    let count = 1
    server.use(http.post('*/products/:id/photos', () => {
      count += 1
      order.push(`add:${count}`)
      const next = [photo('a', 0, true), ...Array.from({ length: count - 1 }, (_, i) => photo(`n${i}`, i + 1))]
      return HttpResponse.json(productWith(next), { status: 201 })
    }))

    await user.upload(screen.getByLabelText('Adicionar fotos à galeria'), [pngFile('x.png'), pngFile('y.png')])

    await waitFor(() => expect(tiles()).toHaveLength(3))
    expect(order).toEqual(['add:2', 'add:3'])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('no limite desabilita "Adicionar fotos"', () => {
    const full = Array.from({ length: MAX_PRODUCT_PHOTOS }, (_, i) => photo(`p${i}`, i, i === 0))
    renderManager(full)

    expect(screen.getByRole('button', { name: /Adicionar fotos/ })).toBeDisabled()
    expect(screen.getByText(/10 de 10 fotos/)).toBeInTheDocument()
  })

  it('mostra o erro do servidor (EU compartilhado com BR) e para o envio', async () => {
    const posts: string[] = []
    const { user } = renderManager()
    server.use(http.post('*/products/:id/photos', () => {
      posts.push('post')
      return HttpResponse.json({ detail: 'Altere as fotos do catálogo-base no mercado Brasil.' }, { status: 403 })
    }))

    await user.upload(screen.getByLabelText('Adicionar fotos à galeria'), [pngFile('x.png'), pngFile('y.png')])

    expect(await screen.findByRole('alert')).toHaveTextContent('Altere as fotos do catálogo-base no mercado Brasil.')
    expect(posts).toHaveLength(1)
    expect(tiles()).toHaveLength(3)
  })
})
