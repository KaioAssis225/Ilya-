import { useEffect, useRef } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Comportamento de diálogo modal (WAI-ARIA): Escape fecha, Tab fica preso no
// painel, o foco entra no painel ao abrir e volta ao gatilho ao fechar.
// Uso: const ref = useDialog(onClose); <div ref={ref} role="dialog" aria-modal="true" …>
// Diálogos aninhados funcionam: só o mais recente (último montado) reage.
const stack: HTMLElement[] = []

export function useDialog<T extends HTMLElement = HTMLDivElement>(onClose: () => void, enabled = true) {
  const ref = useRef<T>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose })

  useEffect(() => {
    const panel = ref.current
    if (!enabled || !panel) return
    const previous = document.activeElement as HTMLElement | null
    stack.push(panel)

    if (!panel.contains(document.activeElement)) {
      const first = panel.querySelector<HTMLElement>('[autofocus]') ?? panel.querySelector<HTMLElement>(FOCUSABLE)
      ;(first ?? panel).focus({ preventScroll: true })
    }

    function onKey(e: KeyboardEvent) {
      if (stack[stack.length - 1] !== panel || !panel) return
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab') return
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(el => el.offsetParent !== null)
      if (items.length === 0) { e.preventDefault(); return }
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
        e.preventDefault(); first.focus()
      }
    }

    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      const i = stack.lastIndexOf(panel)
      if (i >= 0) stack.splice(i, 1)
      if (previous && document.contains(previous)) previous.focus({ preventScroll: true })
    }
  }, [enabled])

  return ref
}
