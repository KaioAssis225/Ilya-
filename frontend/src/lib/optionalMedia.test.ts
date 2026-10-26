import { describe, expect, it } from 'vitest'
import { hasOptionalPhoto, optionalMedia } from './optionalMedia'

const variants = {
  thumb: { url: '/thumb.webp', max_side: 160 },
  gallery: { url: '/gallery.webp', max_side: 480 },
  zoom: { url: '/zoom.webp', max_side: 960 },
}

describe('optionalMedia', () => {
  it('seleciona a variante pedida e monta srcSet e sizes responsivos', () => {
    expect(optionalMedia({ photo_url: '/original.jpg', thumbnail_url: '/legacy.jpg', photo_variants: variants }, 'gallery', 320)).toEqual({
      src: '/gallery.webp',
      srcSet: '/thumb.webp 160w, /gallery.webp 480w, /zoom.webp 960w',
      sizes: '320px',
    })
  })

  it('cai para thumbnail e depois original quando não há variantes', () => {
    expect(optionalMedia({ photo_url: '/original.jpg', thumbnail_url: '/legacy.jpg', photo_variants: null })).toEqual({ src: '/legacy.jpg' })
    expect(optionalMedia({ photo_url: '/original.jpg', thumbnail_url: null, photo_variants: null })).toEqual({ src: '/original.jpg' })
    expect(optionalMedia({ photo_url: null, thumbnail_url: null, photo_variants: null })).toEqual({ src: null })
  })

  it('considera qualquer fonte de mídia como foto disponível', () => {
    expect(hasOptionalPhoto({ photo_url: null, thumbnail_url: null, photo_variants: variants })).toBe(true)
    expect(hasOptionalPhoto({ photo_url: null, thumbnail_url: null, photo_variants: null })).toBe(false)
  })
})
