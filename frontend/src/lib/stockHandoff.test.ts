import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AUTH_MESSAGE,
  listenForStockReady,
  openStockWindow,
  READY_MESSAGE,
  sendAssertionToOpener,
} from './stockHandoff'

const ORIGIN = 'https://ilya-estoque.vercel.app'

function fakePopup() {
  return { closed: false, postMessage: vi.fn() } as unknown as Window & { postMessage: ReturnType<typeof vi.fn> }
}

function dispatch(data: unknown, origin: string, source: unknown) {
  window.dispatchEvent(new MessageEvent('message', { data, origin, source: source as MessageEventSource }))
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('listenForStockReady', () => {
  afterEach(() => vi.restoreAllMocks())

  it('responde com a autorização à janela certa, com targetOrigin exato', async () => {
    const popup = fakePopup()
    const requestAssertion = vi.fn().mockResolvedValue('jwt-de-teste')
    const onSent = vi.fn()
    const cancel = listenForStockReady({ origin: ORIGIN, popup, requestAssertion, onSent })

    dispatch({ type: READY_MESSAGE }, ORIGIN, popup)
    await flush()

    expect(requestAssertion).toHaveBeenCalledTimes(1)
    expect(popup.postMessage).toHaveBeenCalledWith({ type: AUTH_MESSAGE, assertion: 'jwt-de-teste' }, ORIGIN)
    const [, targetOrigin] = popup.postMessage.mock.calls[0]
    expect(targetOrigin).not.toBe('*')
    expect(onSent).toHaveBeenCalled()
    cancel()
  })

  it('ignora mensagem de origem errada', async () => {
    const popup = fakePopup()
    const requestAssertion = vi.fn().mockResolvedValue('x')
    const cancel = listenForStockReady({ origin: ORIGIN, popup, requestAssertion })

    dispatch({ type: READY_MESSAGE }, 'https://atacante.example', popup)
    dispatch({ type: READY_MESSAGE }, `${ORIGIN}.atacante.example`, popup)
    await flush()

    expect(requestAssertion).not.toHaveBeenCalled()
    expect(popup.postMessage).not.toHaveBeenCalled()
    cancel()
  })

  it('ignora mensagem cujo source não é a janela que abrimos', async () => {
    const popup = fakePopup()
    const requestAssertion = vi.fn().mockResolvedValue('x')
    const cancel = listenForStockReady({ origin: ORIGIN, popup, requestAssertion })

    dispatch({ type: READY_MESSAGE }, ORIGIN, fakePopup())
    dispatch({ type: READY_MESSAGE }, ORIGIN, null)
    await flush()

    expect(requestAssertion).not.toHaveBeenCalled()
    cancel()
  })

  it('ignora mensagens de outro tipo ou sem tipo', async () => {
    const popup = fakePopup()
    const requestAssertion = vi.fn().mockResolvedValue('x')
    const cancel = listenForStockReady({ origin: ORIGIN, popup, requestAssertion })

    dispatch({ type: 'outra-coisa' }, ORIGIN, popup)
    dispatch('estoque-pronto', ORIGIN, popup)
    dispatch(null, ORIGIN, popup)
    await flush()

    expect(requestAssertion).not.toHaveBeenCalled()
    cancel()
  })

  it('só envia uma autorização por abertura', async () => {
    const popup = fakePopup()
    const requestAssertion = vi.fn().mockResolvedValue('jwt')
    listenForStockReady({ origin: ORIGIN, popup, requestAssertion })

    dispatch({ type: READY_MESSAGE }, ORIGIN, popup)
    dispatch({ type: READY_MESSAGE }, ORIGIN, popup)
    await flush()

    expect(requestAssertion).toHaveBeenCalledTimes(1)
    expect(popup.postMessage).toHaveBeenCalledTimes(1)
  })

  it('não envia se a janela já foi fechada e reporta erro de rede', async () => {
    const closed = fakePopup()
    ;(closed as { closed: boolean }).closed = true
    listenForStockReady({ origin: ORIGIN, popup: closed, requestAssertion: vi.fn().mockResolvedValue('jwt') })
    dispatch({ type: READY_MESSAGE }, ORIGIN, closed)
    await flush()
    expect(closed.postMessage).not.toHaveBeenCalled()

    const popup = fakePopup()
    const onError = vi.fn()
    listenForStockReady({ origin: ORIGIN, popup, requestAssertion: vi.fn().mockRejectedValue(new Error('403')), onError })
    dispatch({ type: READY_MESSAGE }, ORIGIN, popup)
    await flush()
    expect(onError).toHaveBeenCalled()
    expect(popup.postMessage).not.toHaveBeenCalled()
  })

  it('recusa origem curinga ou malformada', () => {
    for (const bad of ['*', '', 'javascript:alert(1)', 'https://x.app/caminho', 'https://*.x.app']) {
      expect(() => listenForStockReady({ origin: bad, popup: fakePopup() })).toThrow()
    }
  })
})

describe('openStockWindow', () => {
  afterEach(() => vi.restoreAllMocks())

  it('abre /entrar-ilya mantendo o opener (sem noopener/noreferrer)', () => {
    const popup = fakePopup()
    const open = vi.spyOn(window, 'open').mockReturnValue(popup)
    expect(openStockWindow(ORIGIN)).toBe(popup)
    expect(open).toHaveBeenCalledWith(`${ORIGIN}/entrar-ilya`, '_blank')
    expect(open.mock.calls[0]).toHaveLength(2) // sem o 3º argumento "noopener,noreferrer"
  })

  it('avisa quando o navegador bloqueia a janela', () => {
    vi.spyOn(window, 'open').mockReturnValue(null)
    expect(() => openStockWindow(ORIGIN)).toThrow(/bloqueou/i)
  })
})

describe('sendAssertionToOpener (Caminho 2)', () => {
  it('entrega só ao opener, com targetOrigin exato', () => {
    const opener = fakePopup()
    expect(sendAssertionToOpener(ORIGIN, 'jwt', opener)).toBe(true)
    expect(opener.postMessage).toHaveBeenCalledWith({ type: AUTH_MESSAGE, assertion: 'jwt' }, ORIGIN)
  })

  it('sem opener (ou opener fechado) não entrega nada', () => {
    expect(sendAssertionToOpener(ORIGIN, 'jwt', null)).toBe(false)
    const closed = fakePopup()
    ;(closed as { closed: boolean }).closed = true
    expect(sendAssertionToOpener(ORIGIN, 'jwt', closed)).toBe(false)
    expect(closed.postMessage).not.toHaveBeenCalled()
  })

  it('nunca aceita "*" como destino', () => {
    expect(() => sendAssertionToOpener('*', 'jwt', fakePopup())).toThrow()
  })
})
