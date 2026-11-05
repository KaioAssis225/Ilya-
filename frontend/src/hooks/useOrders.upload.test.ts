import type { InternalAxiosRequestConfig } from 'axios'
import { afterEach, describe, expect, it } from 'vitest'
import api from '../lib/api'
import { uploadOrderItemAttachment } from './useOrders'

const originalAdapter = api.defaults.adapter

afterEach(() => {
  api.defaults.adapter = originalAdapter
})

/**
 * Substitui só o último passo (a rede). O axios já aplicou cabeçalhos
 * padrão e `transformRequest`, então o que chega aqui é o que o navegador
 * enviaria.
 */
function captureRequest() {
  const captured: { config?: InternalAxiosRequestConfig } = {}
  api.defaults.adapter = async (config) => {
    captured.config = config
    return { data: {}, status: 201, statusText: 'Created', headers: {}, config }
  }
  return captured
}

describe('uploadOrderItemAttachment', () => {
  it('envia o PDF como multipart com a entrada `file` sendo um arquivo', async () => {
    const captured = captureRequest()
    const pdf = new File(['%PDF-1.7\n%%EOF'], 'ficha-tecnica.pdf', { type: 'application/pdf' })

    await uploadOrderItemAttachment(pdf)

    const config = captured.config
    expect(config?.url).toBe('/order-item-attachments')
    // Se o cabeçalho continuar application/json, o axios converte o FormData em
    // JSON e o backend responde que `file` é obrigatório.
    expect(config?.data).toBeInstanceOf(FormData)
    const sent = (config!.data as FormData).get('file')
    expect(sent).toBeInstanceOf(File)
    expect((sent as File).name).toBe('ficha-tecnica.pdf')
    const contentType = String(config?.headers.getContentType() ?? '')
    expect(contentType).not.toContain('application/json')
  })

  it('mantém chamadas JSON comuns como JSON', async () => {
    const captured = captureRequest()

    await api.post('/qualquer-rota', { nome: 'x' })

    expect(captured.config?.data).toBe('{"nome":"x"}')
    expect(String(captured.config?.headers.getContentType())).toContain('application/json')
  })
})
