import api from './api'

/**
 * Login único com o Estoque Brasil — lado do Ilya (contrato do postMessage,
 * PEDIDO-AO-MAESTRO-DO-ILYA.md, seção 5).
 *
 * A autorização NUNCA vai na URL: viaja entre duas janelas por `postMessage`,
 * sempre com `targetOrigin` exato (a origem do Estoque, vinda do servidor) e
 * respondendo apenas à janela que nós mesmos abrimos.
 */
export const READY_MESSAGE = 'estoque-pronto'
export const AUTH_MESSAGE = 'autorizacao'
const ENTER_PATH = '/entrar-ilya'
const LISTEN_TIMEOUT_MS = 2 * 60_000

export async function fetchStockOrigin(): Promise<string> {
  const { data } = await api.get<{ origin: string }>('/stock/link')
  return data.origin
}

export async function fetchStockAssertion(): Promise<string> {
  const { data } = await api.post<{ assertion: string }>('/stock/handoff')
  return data.assertion
}

function assertExactOrigin(origin: string): void {
  // `*` nunca: a autorização só pode ser entregue à origem do Estoque.
  if (!origin || origin === '*' || !/^https?:\/\/[^/*]+$/.test(origin)) {
    throw new Error('Origem do Estoque inválida.')
  }
}

/** Abre o Estoque mantendo `window.opener` (sem `noopener`/`noreferrer`). */
export function openStockWindow(origin: string): Window {
  assertExactOrigin(origin)
  const popup = window.open(`${origin}${ENTER_PATH}`, '_blank')
  if (!popup) throw new Error('O navegador bloqueou a nova janela. Libere pop-ups para o Ilya.')
  return popup
}

interface ReadyListenerOptions {
  origin: string
  popup: Window
  requestAssertion?: () => Promise<string>
  onSent?: () => void
  onError?: (error: unknown) => void
  timeoutMs?: number
}

/**
 * Espera `{ type: 'estoque-pronto' }` e responde com a autorização.
 * Só reage se `event.origin` for exatamente a do Estoque E `event.source` for a
 * janela que abrimos; qualquer outra coisa é ignorada. Devolve a função que
 * cancela a escuta.
 */
export function listenForStockReady({
  origin,
  popup,
  requestAssertion = fetchStockAssertion,
  onSent,
  onError,
  timeoutMs = LISTEN_TIMEOUT_MS,
}: ReadyListenerOptions): () => void {
  assertExactOrigin(origin)
  let handled = false
  const cancel = () => {
    window.removeEventListener('message', handler)
    window.clearTimeout(timer)
  }
  function handler(event: MessageEvent) {
    if (event.origin !== origin) return
    if (event.source !== popup) return
    if ((event.data as { type?: unknown } | null)?.type !== READY_MESSAGE) return
    if (handled) return
    handled = true
    requestAssertion()
      .then(assertion => {
        if (popup.closed) return
        popup.postMessage({ type: AUTH_MESSAGE, assertion }, origin)
        onSent?.()
      })
      .catch(error => onError?.(error))
      .finally(cancel)
  }
  const timer = window.setTimeout(cancel, timeoutMs)
  window.addEventListener('message', handler)
  return cancel
}

/**
 * Caminho 2: a janela foi aberta pelo Estoque (`/estoque/conectar`). Entrega a
 * autorização a `window.opener`, e só se ele existir. Devolve se entregou.
 */
export function sendAssertionToOpener(
  origin: string,
  assertion: string,
  opener: Window | null = window.opener as Window | null,
): boolean {
  assertExactOrigin(origin)
  if (!opener || opener.closed) return false
  opener.postMessage({ type: AUTH_MESSAGE, assertion }, origin)
  return true
}
