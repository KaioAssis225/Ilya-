import { useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, Star, Trash2 } from 'lucide-react'
import {
  useAddProductPhotoToGallery,
  useRemoveProductGalleryPhoto,
  useReorderProductGalleryPhotos,
  useSetPrimaryProductPhoto,
} from '../hooks/useProducts'
import { useCadastroText } from '../hooks/useCadastroText'
import { parseApiError } from '../lib/personForm'
import type { Product, ProductPhoto } from '../types'

/** Mesmo teto do servidor (`MAX_PRODUCT_PHOTOS`); o servidor é quem decide, aqui só evita envio inútil. */
export const MAX_PRODUCT_PHOTOS = 10

interface ProductPhotosManagerProps {
  product: Product
  /** Cor do mercado (ouro BR / verde EU), como no resto do formulário. */
  color: string
  /** Recebe o produto devolvido pelo servidor após cada mudança. */
  onUpdated?: (product: Product) => void
  /** Prefixo da API das fotos (`/prototypes` na área de protótipos). */
  basePath?: string
}

const byPosition = (photos: ProductPhoto[]) => [...photos].sort((a, b) => a.position - b.position)

/**
 * Gerenciador da galeria no formulário de produto existente. Cada ação é uma
 * requisição própria e vale na hora (não espera o "Salvar" do formulário); o
 * servidor devolve o produto e a lista abaixo reflete exatamente esse retorno.
 */
export function ProductPhotosManager({ product, color, onUpdated, basePath }: ProductPhotosManagerProps) {
  const tx = useCadastroText()
  const addM = useAddProductPhotoToGallery()
  const removeM = useRemoveProductGalleryPhoto()
  const reorderM = useReorderProductGalleryPhotos()
  const primaryM = useSetPrimaryProductPhoto()
  const inputRef = useRef<HTMLInputElement>(null)
  const [photos, setPhotos] = useState<ProductPhoto[]>(() => byPosition(product.photos ?? []))
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)

  function accept(updated: Product) {
    setPhotos(byPosition(updated.photos ?? []))
    onUpdated?.(updated)
  }

  async function run(action: () => Promise<Product>) {
    setBusy(true)
    setError(null)
    try {
      accept(await action())
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setBusy(false)
    }
  }

  async function addFiles(files: File[]) {
    const room = MAX_PRODUCT_PHOTOS - photos.length
    const accepted = files.slice(0, Math.max(0, room))
    if (accepted.length === 0) {
      setError(tx('Limite de {max} fotos por produto.', { max: MAX_PRODUCT_PHOTOS }))
      return
    }
    setBusy(true)
    setError(null)
    const failures: string[] = []
    for (const [index, file] of accepted.entries()) {
      setProgress({ current: index + 1, total: accepted.length })
      try {
        accept(await addM.mutateAsync({ id: product.id, file, basePath }))
      } catch (err) {
        failures.push(`${file.name}: ${parseApiError(err)}`)
        break // 403/409 se repetem para os demais; para no primeiro erro
      }
    }
    if (files.length > accepted.length && failures.length === 0) {
      failures.push(tx('Limite de {max} fotos por produto.', { max: MAX_PRODUCT_PHOTOS }))
    }
    setProgress(null)
    setError(failures.length ? failures.join(' · ') : null)
    setBusy(false)
  }

  function move(index: number, delta: -1 | 1) {
    const ids = photos.map(photo => photo.id)
    const target = index + delta
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    void run(() => reorderM.mutateAsync({ id: product.id, photoIds: ids, basePath }))
  }

  const atLimit = photos.length >= MAX_PRODUCT_PHOTOS

  return (
    <section aria-label={tx('Galeria de fotos')} className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted">
          {tx('Galeria de fotos')} · {tx('{count} de {max} fotos', { count: photos.length, max: MAX_PRODUCT_PHOTOS })}
        </span>
        <button
          type="button"
          className="btn-secondary inline-flex min-h-11 items-center gap-1 px-3 text-xs"
          disabled={busy || atLimit}
          onClick={() => inputRef.current?.click()}
        >
          <Plus className="h-4 w-4" aria-hidden="true" /> {tx('Adicionar fotos')}
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.webp"
          className="hidden"
          aria-label={tx('Adicionar fotos à galeria')}
          onChange={(event) => {
            const files = Array.from(event.target.files ?? [])
            event.target.value = ''
            if (files.length) void addFiles(files)
          }}
        />
      </div>
      <p className="text-[11px] text-muted">{tx('A foto principal é a que aparece no catálogo, no orçamento e no PDF.')}</p>

      {progress && (
        <p role="status" className="text-xs text-muted">
          {tx('Enviando foto {current} de {total}…', progress)}
        </p>
      )}
      {error && <p role="alert" className="text-xs font-medium text-danger">{error}</p>}

      {photos.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label={tx('Fotos do produto')}>
          {photos.map((photo, index) => {
            const number = index + 1
            const src = photo.thumbnail_url ?? photo.photo_url
            const confirming = confirmingId === photo.id
            return (
              <li
                key={photo.id}
                className={`flex flex-col gap-2 rounded-xl border bg-white p-2 ${photo.is_primary ? 'border-2' : 'border-line'}`}
                style={photo.is_primary ? { borderColor: color } : undefined}
              >
                <div className="relative aspect-square overflow-hidden rounded-lg bg-white">
                  {src && <img src={src} alt={tx('Foto {n} de {total}', { n: number, total: photos.length })} loading="lazy" decoding="async" className="h-full w-full object-contain" />}
                  {photo.is_primary && (
                    <span className="absolute left-1 top-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold text-white" style={{ backgroundColor: color }}>
                      <Star className="h-3 w-3" aria-hidden="true" /> {tx('Principal')}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  {!photo.is_primary && (
                    <button
                      type="button"
                      className="btn-secondary min-h-11 flex-1 px-2 text-xs"
                      disabled={busy}
                      aria-label={tx('Definir a foto {n} como principal', { n: number })}
                      onClick={() => void run(() => primaryM.mutateAsync({ id: product.id, photoId: photo.id, basePath }))}
                    >
                      {tx('Definir como principal')}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-icon h-11 w-11"
                    disabled={busy || index === 0}
                    aria-label={tx('Mover a foto {n} para a esquerda', { n: number })}
                    onClick={() => move(index, -1)}
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="btn-icon h-11 w-11"
                    disabled={busy || index === photos.length - 1}
                    aria-label={tx('Mover a foto {n} para a direita', { n: number })}
                    onClick={() => move(index, 1)}
                  >
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                  {confirming ? (
                    <>
                      <button
                        type="button"
                        className="min-h-11 rounded-lg bg-danger px-3 text-xs font-semibold text-white"
                        disabled={busy}
                        aria-label={tx('Confirmar a remoção da foto {n}', { n: number })}
                        onClick={() => {
                          setConfirmingId(null)
                          void run(() => removeM.mutateAsync({ id: product.id, photoId: photo.id, basePath }))
                        }}
                      >
                        {tx('Confirmar remoção')}
                      </button>
                      <button type="button" className="btn-secondary min-h-11 px-2 text-xs" onClick={() => setConfirmingId(null)}>
                        {tx('Cancelar')}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn-icon h-11 w-11 hover:text-danger"
                      disabled={busy}
                      aria-label={tx('Remover a foto {n} da galeria', { n: number })}
                      onClick={() => setConfirmingId(photo.id)}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
