import { useEffect, useRef, useState } from 'react'
import {
  fetchStockAssertion,
  fetchStockOrigin,
  sendAssertionToOpener,
} from '../lib/stockHandoff'

type Phase = 'working' | 'no-opener' | 'sent' | 'error'

/**
 * Caminho 2 do login único: o Estoque abre esta página num popup (com ele como
 * `opener`). Exige sessão normal do Ilya (a rota fica atrás de PrivateGate),
 * pede a autorização, entrega SÓ a `window.opener` — com `targetOrigin` exato —
 * e fecha. Sem `opener` não há para quem entregar: orienta a pessoa.
 */
export default function EstoqueConectarPage() {
  const [phase, setPhase] = useState<Phase>(() => (window.opener ? 'working' : 'no-opener'))
  const startedRef = useRef(false)

  useEffect(() => {
    if (!window.opener || startedRef.current) return
    startedRef.current = true
    let closeTimer: number | undefined
    ;(async () => {
      try {
        const origin = await fetchStockOrigin()
        const assertion = await fetchStockAssertion()
        if (!sendAssertionToOpener(origin, assertion)) {
          setPhase('no-opener')
          return
        }
        setPhase('sent')
        closeTimer = window.setTimeout(() => window.close(), 300)
      } catch {
        setPhase('error')
      }
    })()
    return () => window.clearTimeout(closeTimer)
  }, [])

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-base font-semibold text-ink">Entrar no Estoque</h1>
      {phase === 'working' && <p role="status" className="text-sm text-muted">Conectando ao Estoque…</p>}
      {phase === 'sent' && <p role="status" className="text-sm text-muted">Pronto. Você já pode fechar esta janela.</p>}
      {phase === 'no-opener' && (
        <p role="alert" className="text-sm text-ink-2">
          Abra o Estoque e clique em <strong>Entrar pelo Ilya</strong>.
        </p>
      )}
      {phase === 'error' && (
        <p role="alert" className="text-sm text-terracotta">
          Você não tem acesso ao Estoque ou a integração está indisponível.
        </p>
      )}
    </main>
  )
}
