import { ImageOff } from 'lucide-react'
import { useImageRetry } from '../hooks/useImageRetry'
import { useLocale } from '../hooks/useLocale'
import { optionalName } from '../lib/optionalLabels'
import { optionalMedia, optionalMediaWidth, type OptionalMediaVariant } from '../lib/optionalMedia'
import type { OptionalColor } from '../types'

interface OptionalSwatchImageProps {
  optional: Pick<OptionalColor, 'color_name' | 'photo_url' | 'thumbnail_url' | 'photo_variants'>
  variant?: OptionalMediaVariant
  displaySize?: number
  priority?: boolean
  responsive?: boolean
  decorative?: boolean
  className?: string
  imageClassName?: string
}

export function OptionalSwatchImage({
  optional,
  variant = 'thumb',
  displaySize = optionalMediaWidth(variant),
  priority = false,
  responsive = true,
  decorative = false,
  className = '',
  imageClassName = '',
}: OptionalSwatchImageProps) {
  const { locale } = useLocale()
  const label = optionalName(optional.color_name, locale === 'en-GB')
  const media = optionalMedia(optional, variant, displaySize)
  const image = useImageRetry(media.src)
  // Na nova tentativa o srcSet sai: o navegador poderia escolher de novo a
  // mesma candidata que falhou, sem o parâmetro que força o novo pedido.
  const withSrcSet = responsive && !image.retried
  const unavailableLabel = locale === 'en-GB' ? 'Image being updated' : 'Imagem em atualização'

  return (
    <span aria-hidden={decorative || undefined} className={`relative flex aspect-square items-center justify-center overflow-hidden bg-swatch-bg ${className}`}>
      {image.src ? (
        <img
          src={image.src}
          srcSet={withSrcSet ? media.srcSet : undefined}
          sizes={withSrcSet ? media.sizes : undefined}
          alt={decorative ? '' : label}
          aria-hidden={decorative || undefined}
          width={displaySize}
          height={displaySize}
          loading={priority ? 'eager' : 'lazy'}
          fetchPriority={priority ? 'high' : 'auto'}
          decoding="async"
          onError={image.onError}
          className={`h-full w-full object-contain ${image.waiting ? 'opacity-0' : ''} ${imageClassName}`}
        />
      ) : (
        <span
          role={decorative ? undefined : 'img'}
          aria-label={decorative ? undefined : `${unavailableLabel}: ${label}`}
          className="flex h-full w-full flex-col items-center justify-center gap-1.5 p-2 text-center text-muted"
        >
          <ImageOff className="h-5 w-5 shrink-0" aria-hidden="true" />
          <span className="text-[10px] font-medium leading-tight">
            {unavailableLabel}
            <span className="block [overflow-wrap:anywhere]">{label}</span>
          </span>
        </span>
      )}
    </span>
  )
}
