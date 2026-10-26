import { ImageOff } from 'lucide-react'
import { useState } from 'react'
import { useLocale } from '../hooks/useLocale'
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
  const [failedSources, setFailedSources] = useState<string[]>([])
  const media = optionalMedia(optional, variant, displaySize)
  const primaryFailed = Boolean(media.src && failedSources.includes(media.src))
  const fallback = optional.photo_url && optional.photo_url !== media.src ? optional.photo_url : null
  const fallbackFailed = Boolean(fallback && failedSources.includes(fallback))
  const source = primaryFailed && fallback && !fallbackFailed ? fallback : primaryFailed ? null : media.src
  const usingFallback = source === fallback
  const unavailableLabel = locale === 'en-GB' ? 'Image being updated' : 'Imagem em atualização'

  return (
    <span aria-hidden={decorative || undefined} className={`relative flex aspect-square items-center justify-center overflow-hidden bg-swatch-bg ${className}`}>
      {source ? (
        <img
          src={source}
          srcSet={usingFallback || !responsive ? undefined : media.srcSet}
          sizes={usingFallback || !responsive ? undefined : media.sizes}
          alt={decorative ? '' : optional.color_name}
          aria-hidden={decorative || undefined}
          width={displaySize}
          height={displaySize}
          loading={priority ? 'eager' : 'lazy'}
          fetchPriority={priority ? 'high' : 'auto'}
          decoding="async"
          onError={() => setFailedSources(current => current.includes(source) ? current : [...current, source])}
          className={`h-full w-full object-contain ${imageClassName}`}
        />
      ) : (
        <span
          role={decorative ? undefined : 'img'}
          aria-label={decorative ? undefined : `${unavailableLabel}: ${optional.color_name}`}
          className="flex h-full w-full flex-col items-center justify-center gap-1.5 p-2 text-center text-muted"
        >
          <ImageOff className="h-5 w-5 shrink-0" aria-hidden="true" />
          <span className="text-[10px] font-medium leading-tight">
            {unavailableLabel}
            <span className="block [overflow-wrap:anywhere]">{optional.color_name}</span>
          </span>
        </span>
      )}
    </span>
  )
}
