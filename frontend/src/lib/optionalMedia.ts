import type { OptionalColor, OptionalPhotoVariants } from '../types'

export type OptionalMediaVariant = keyof OptionalPhotoVariants

export interface OptionalMediaSource {
  src: string | null
  srcSet?: string
  sizes?: string
}

const VARIANT_WIDTH: Record<OptionalMediaVariant, number> = {
  thumb: 160,
  gallery: 480,
  zoom: 960,
}

export function hasOptionalPhoto(optional: Pick<OptionalColor, 'photo_url' | 'thumbnail_url' | 'photo_variants'>) {
  return Boolean(optional.photo_variants?.thumb.url || optional.thumbnail_url || optional.photo_url)
}

export function optionalMedia(
  optional: Pick<OptionalColor, 'photo_url' | 'thumbnail_url' | 'photo_variants'>,
  variant: OptionalMediaVariant = 'thumb',
  displaySize = VARIANT_WIDTH[variant],
): OptionalMediaSource {
  const variants = optional.photo_variants
  if (!variants) {
    return { src: optional.thumbnail_url ?? optional.photo_url }
  }

  return {
    src: variants[variant].url,
    srcSet: [
      `${variants.thumb.url} 160w`,
      `${variants.gallery.url} 480w`,
      `${variants.zoom.url} 960w`,
    ].join(', '),
    sizes: `${displaySize}px`,
  }
}

export function optionalMediaWidth(variant: OptionalMediaVariant) {
  return VARIANT_WIDTH[variant]
}
