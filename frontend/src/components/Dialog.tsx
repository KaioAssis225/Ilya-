import { useId, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { useDialog } from '../hooks/useDialog'

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
