// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { OptionalSwatchImage } from './OptionalSwatchImage'
import { IMAGE_RETRY_DELAY_MS } from '../hooks/useImageRetry'
import { LocaleContext } from '../hooks/useLocale'
import type { OptionalColor } from '../types'

const THUMB = '/api/v1/media/eu-optional-variants/neve.png.v1-thumb.webp?expires=1&signature=a'
const ORIGINAL = '/api/v1/media/eu-optionals/neve.png?expires=1&signature=b'

const optional: Pick<OptionalColor, 'color_name' | 'photo_url' | 'thumbnail_url' | 'photo_variants'> = {
  color_name: 'Neve',
  photo_url: ORIGINAL,
  thumbnail_url: null,
  photo_variants: {
    thumb: { url: THUMB, max_side: 160 },
    gallery: { url: THUMB.replace('thumb', 'gallery'), max_side: 480 },
    zoom: { url: THUMB.replace('thumb', 'zoom'), max_side: 960 },
  },
}

function renderSwatch() {
  return render(
    <LocaleContext.Provider value={{ locale: 'pt-PT', setLocale: () => undefined, t: key => key }}>
      <OptionalSwatchImage optional={optional} />
    </LocaleContext.Provider>,
  )
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

it('refaz a mesma miniatura após falha passageira, sem cair para o original', () => {
  renderSwatch()
  const image = screen.getByRole('img', { name: 'Neve' })
  expect(image).toHaveAttribute('src', THUMB)

  fireEvent.error(image)
  // Durante a espera não troca de URL nem baixa o original pesado.
  expect(image).toHaveAttribute('src', THUMB)

  act(() => { vi.advanceTimersByTime(IMAGE_RETRY_DELAY_MS) })
  const retried = screen.getByRole('img', { name: 'Neve' })
  expect(retried).toHaveAttribute('src', `${THUMB}&retry=1`)
  expect(retried).not.toHaveAttribute('srcset')
  expect(retried.getAttribute('src')).not.toContain('eu-optionals/')
})

it('mostra o placeholder quando a nova tentativa também falha', () => {
  renderSwatch()
  fireEvent.error(screen.getByRole('img', { name: 'Neve' }))
  act(() => { vi.advanceTimersByTime(IMAGE_RETRY_DELAY_MS) })
  fireEvent.error(screen.getByRole('img', { name: 'Neve' }))

  expect(screen.getByRole('img', { name: 'Imagem em atualização: Neve' })).toBeVisible()
  expect(document.querySelector('img')).toBeNull()
})
