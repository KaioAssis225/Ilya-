import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { server } from '../test/setup'
import EstoqueConectarPage from './EstoqueConectarPage'

const ORIGIN = 'https://ilya-estoque.vercel.app'

function setOpener(value: unknown) {
  Object.defineProperty(window, 'opener', { value, configurable: true, writable: true })
}

describe('EstoqueConectarPage (Caminho 2)', () => {
  afterEach(() => {
    setOpener(null)
    vi.restoreAllMocks()
  })

  it('sem opener orienta a abrir o Estoque e não chama o servidor', async () => {
    let called = false
    server.use(
      http.get('*/stock/link', () => { called = true; return HttpResponse.json({ origin: ORIGIN }) }),
      http.post('*/stock/handoff', () => { called = true; return HttpResponse.json({ assertion: 'x', expires_in: 60 }) }),
    )
    setOpener(null)
    render(<EstoqueConectarPage />)
    expect(screen.getByRole('alert')).toHaveTextContent('Abra o Estoque e clique em Entrar pelo Ilya')
    await new Promise(resolve => setTimeout(resolve, 30))
    expect(called).toBe(false)
  })

  it('com opener pede a autorização, entrega só ao opener (targetOrigin exato) e fecha', async () => {
    server.use(
      http.get('*/stock/link', () => HttpResponse.json({ origin: ORIGIN })),
      http.post('*/stock/handoff', () => HttpResponse.json({ assertion: 'jwt-de-teste', expires_in: 60 })),
    )
    const opener = { closed: false, postMessage: vi.fn() }
    setOpener(opener)
    const close = vi.spyOn(window, 'close').mockImplementation(() => undefined)
    render(<EstoqueConectarPage />)

    await waitFor(() => expect(opener.postMessage).toHaveBeenCalledWith(
      { type: 'autorizacao', assertion: 'jwt-de-teste' }, ORIGIN,
    ))
    await waitFor(() => expect(close).toHaveBeenCalled())
  })

  it('sem permissão (403) mostra erro e não envia nada', async () => {
    server.use(http.get('*/stock/link', () => HttpResponse.json({ detail: 'x' }, { status: 403 })))
    const opener = { closed: false, postMessage: vi.fn() }
    setOpener(opener)
    render(<EstoqueConectarPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/não tem acesso/i)
    expect(opener.postMessage).not.toHaveBeenCalled()
  })
})
