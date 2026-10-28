import { useEffect, useState } from 'react'

export const IMAGE_RETRY_DELAY_MS = 1500

type Phase = 'initial' | 'waiting' | 'retry' | 'failed'

/**
 * Falha de foto costuma ser 503 passageiro do storage. Tenta a MESMA URL mais
 * uma vez (com parâmetro novo, senão o navegador não refaz o pedido) e, se
 * falhar de novo, sinaliza `failed` para a tela mostrar o placeholder.
 *
 * Nunca troca para o original: ele é mais pesado e vem do mesmo storage que
 * acabou de falhar, então só agravava a rajada.
 */
export function useImageRetry(source: string | null | undefined) {
  // A fase vale para a URL em que foi registrada; URL nova recomeça do zero
  // sem precisar de setState dentro de efeito.
  const [state, setState] = useState<{ source: string | null | undefined; phase: Phase }>({ source, phase: 'initial' })
  const phase: Phase = state.source === source ? state.phase : 'initial'

  useEffect(() => {
    if (phase !== 'waiting') return
    const timer = window.setTimeout(() => setState({ source, phase: 'retry' }), IMAGE_RETRY_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [phase, source])

  return {
    src: !source || phase === 'failed' ? null : phase === 'retry' ? withRetryParam(source) : source,
    retried: phase === 'retry',
    waiting: phase === 'waiting',
    failed: Boolean(source) && phase === 'failed',
    onError: () => setState({ source, phase: phase === 'retry' ? 'failed' : 'waiting' }),
  }
}

function withRetryParam(source: string) {
  return `${source}${source.includes('?') ? '&' : '?'}retry=1`
}
