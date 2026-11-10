import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ProductGallery } from './ProductGallery'
import type { ProductPhoto } from '../types'

function photo(id: string, position: number, isPrimary = false): ProductPhoto {
  return {
    id, position, is_primary: isPrimary,
    photo_url: `/media/${id}.jpg`, thumbnail_url: `/media/${id}-thumb.jpg`,
  }
}

const THREE = [photo('a', 0), photo('b', 1, true), photo('c', 2)]

const renderImage = (current: ProductPhoto) => <img data-testid="main" src={current.photo_url ?? ''} alt="" />

function renderGallery(photos = THREE, extra: Partial<Parameters<typeof ProductGallery>[0]> = {}) {
  return render(<ProductGallery photos={photos} english={false} renderImage={renderImage} {...extra} />)
}

const mainSrc = () => screen.getByTestId('main').getAttribute('src')

describe('ProductGallery', () => {
  it('abre na foto principal, mesmo fora da primeira posição', () => {
    renderGallery()

    expect(mainSrc()).toBe('/media/b.jpg')
    expect(screen.getByRole('tab', { name: 'Foto 2 de 3' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('2/3')).toBeInTheDocument()
  })

  it('navega pelas setas dando a volta nas pontas', async () => {
    const user = userEvent.setup()
    renderGallery()

    await user.click(screen.getByRole('button', { name: 'Próxima foto' }))
    expect(mainSrc()).toBe('/media/c.jpg')
    await user.click(screen.getByRole('button', { name: 'Próxima foto' }))
    expect(mainSrc()).toBe('/media/a.jpg')
    await user.click(screen.getByRole('button', { name: 'Foto anterior' }))
    expect(mainSrc()).toBe('/media/c.jpg')
  })

  it('troca a foto ao clicar na miniatura', async () => {
    const user = userEvent.setup()
    renderGallery()

    await user.click(screen.getByRole('tab', { name: 'Foto 3 de 3' }))

    expect(mainSrc()).toBe('/media/c.jpg')
    expect(screen.getByRole('tab', { name: 'Foto 3 de 3' })).toHaveAttribute('aria-selected', 'true')
  })

  it('responde ao teclado: setas, Home e End', async () => {
    const user = userEvent.setup()
    renderGallery()
    screen.getByRole('group', { name: 'Fotos do produto' }).focus()

    await user.keyboard('{ArrowRight}')
    expect(mainSrc()).toBe('/media/c.jpg')
    await user.keyboard('{Home}')
    expect(mainSrc()).toBe('/media/a.jpg')
    await user.keyboard('{End}')
    expect(mainSrc()).toBe('/media/c.jpg')
    await user.keyboard('{ArrowLeft}')
    expect(mainSrc()).toBe('/media/b.jpg')
  })

  it('desliza no celular: para a esquerda avança, para a direita volta, curto é ignorado', () => {
    renderGallery()
    const area = screen.getByTestId('main').parentElement!.parentElement!

    fireEvent.touchStart(area, { touches: [{ clientX: 200 }] })
    fireEvent.touchEnd(area, { changedTouches: [{ clientX: 120 }] })
    expect(mainSrc()).toBe('/media/c.jpg')

    fireEvent.touchStart(area, { touches: [{ clientX: 100 }] })
    fireEvent.touchEnd(area, { changedTouches: [{ clientX: 180 }] })
    expect(mainSrc()).toBe('/media/b.jpg')

    fireEvent.touchStart(area, { touches: [{ clientX: 100 }] })
    fireEvent.touchEnd(area, { changedTouches: [{ clientX: 110 }] })
    expect(mainSrc()).toBe('/media/b.jpg')
  })

  it('pré-carrega os originais das fotos vizinhas', async () => {
    const user = userEvent.setup()
    const onPreload = vi.fn()
    renderGallery(THREE, { onPreload })

    expect(onPreload).toHaveBeenCalledWith('/media/c.jpg')
    expect(onPreload).toHaveBeenCalledWith('/media/a.jpg')
    onPreload.mockClear()
    await user.click(screen.getByRole('button', { name: 'Próxima foto' }))
    expect(onPreload).toHaveBeenCalledWith('/media/a.jpg')
  })

  it('mantém a foto atual quando a lista é recarregada com a mesma foto', async () => {
    const user = userEvent.setup()
    const { rerender } = renderGallery()
    await user.click(screen.getByRole('tab', { name: 'Foto 3 de 3' }))

    rerender(<ProductGallery photos={[...THREE]} english={false} renderImage={renderImage} />)

    expect(mainSrc()).toBe('/media/c.jpg')
  })

  it('volta para a principal quando a foto atual some da lista', async () => {
    const user = userEvent.setup()
    const { rerender } = renderGallery()
    await user.click(screen.getByRole('tab', { name: 'Foto 3 de 3' }))

    rerender(
      <ProductGallery photos={[photo('a', 0, true), photo('b', 1)]} english={false} renderImage={renderImage} />,
    )

    expect(mainSrc()).toBe('/media/a.jpg')
  })

  it('usa rótulos em inglês no mercado EU', () => {
    renderGallery(THREE, { english: true })

    expect(screen.getByRole('button', { name: 'Next photo' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Photo 1 of 3' })).toBeInTheDocument()
  })
})
