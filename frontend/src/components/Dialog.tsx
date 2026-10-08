import { useEffect, useId, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { useDialog } from '../hooks/useDialog'

// Painel de modal que mantém o markup existente da tela e só acrescenta a
// semântica: role="dialog", aria-modal, rótulo pelo primeiro título interno,
// Escape e foco preso. Para modais com cabeçalho próprio (fotos, detalhes).
export function DialogPanel({
  onClose,
  className,
  children,
  label,
}: {
  onClose: () => void
  className?: string
  children: ReactNode
  /** Rótulo explícito quando o painel não tem título visível. */
  label?: string
}) {
  const ref = useDialog(onClose)
  const fallbackId = useId()

  useEffect(() => {
    const panel = ref.current
    if (!panel || label) return
    const heading = panel.querySelector<HTMLElement>('h1, h2, h3, h4')
    if (!heading) return
    if (!heading.id) heading.id = fallbackId
    panel.setAttribute('aria-labelledby', heading.id)
  })

  return (
    <div
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      tabIndex={-1}
      className={className}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>
  )
}

// Casca canônica de modal: .modal-overlay + .modal-panel, role="dialog",
// título ligado por aria-labelledby, fechar por Escape/clique fora e foco
// preso no painel. `layer="sub"` empilha sobre outro modal aberto.
export function Dialog({
  title,
  onClose,
  children,
  className = 'max-w-md',
  layer = 'modal',
  dismissible = true,
}: {
  title: ReactNode
  onClose: () => void
  children: ReactNode
  className?: string
  layer?: 'modal' | 'sub'
  /** false enquanto uma operação está em andamento (bloqueia Escape/clique fora). */
  dismissible?: boolean
}) {
  const titleId = useId()
  const close = () => { if (dismissible) onClose() }
  const ref = useDialog(close)

  return (
    <div
      className={`modal-overlay items-center ${layer === 'sub' ? 'z-modal-sub' : 'z-modal'}`}
      onClick={(e) => { if (e.target === e.currentTarget) close() }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`modal-panel w-full p-6 my-auto ${className}`}
      >
        <div className="flex items-center justify-between gap-3 mb-4">
          <h3 id={titleId} className="font-semibold text-ink">{title}</h3>
          <button type="button" onClick={close} aria-label="Fechar" className="btn-icon -mr-2">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
