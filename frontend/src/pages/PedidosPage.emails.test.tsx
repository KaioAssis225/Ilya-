import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { renderProductPage, productTestUser } from '../test/productTestUtils'
import { server } from '../test/setup'
import PedidosPage from './PedidosPage'
import type { Order, OrderEmailDelivery, OrderEmailHistory, OrderSummary } from '../types'

// O Blob do jsdom não tem .stream(). No Node 22 o interceptor XHR do MSW monta um
// Response com esse Blob (responseType 'blob') e o undici exige .stream(); o
// navegador real devolve um Blob nativo, então isto é só do ambiente de teste.
if (typeof Blob.prototype.stream !== 'function') {
  Object.defineProperty(Blob.prototype, 'stream', {
    configurable: true,
    writable: true,
    value(this: Blob) {
      return readBlobStream(this)
    },
  })
}

function readBlobStream(blob: Blob) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      return new Promise<void>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => {
          controller.enqueue(new Uint8Array(reader.result as ArrayBuffer))
          controller.close()
          resolve()
        }
        reader.onerror = () => reject(reader.error)
        reader.readAsArrayBuffer(blob)
      })
    },
  })
}

const makeSummary = (overrides: Partial<OrderSummary> = {}): OrderSummary => ({
  id: 'order-1',
  code: 'PED-0001',
  orc_id: 'ORC-0001',
  market_code: 'BR',
  currency: 'BRL',
  client_id: 'client-1',
  client_name: 'Cliente Teste',
  rep_id: 'rep-1',
  rep_name: 'Representante Teste',
  total_value: 100,
  total_with_ipi: 100,
  is_finalized: true,
  is_cancelled: false,
  finalized_at: '2024-01-02T00:00:00.000Z',
  cancelled_at: null,
  items: [],
  created_at: '2024-01-01T00:00:00.000Z',
  ...overrides,
})

const makeDetail = (summary: OrderSummary): Order => ({
  ...summary,
  price_list_code: 'lojista',
  locale: summary.market_code === 'EU' ? 'pt-PT' : 'pt-BR',
  total_ipi: 0,
  external_code: null,
  notes: null,
  updated_at: summary.created_at,
  history: [],
  items: [],
})

const makeDelivery = (overrides: Partial<OrderEmailDelivery> = {}): OrderEmailDelivery => ({
  id: 'delivery-1',
  document_id: 'doc-1',
  recipient_roles: ['client'],
  recipient_email: 'cliente@example.test',
  status: 'delivered',
  attempts: 1,
  created_at: '2024-01-02T10:00:00.000Z',
  updated_at: '2024-01-02T10:05:00.000Z',
  first_attempt_at: '2024-01-02T10:00:00.000Z',
  next_attempt_at: null,
  accepted_at: '2024-01-02T10:01:00.000Z',
  delivered_at: '2024-01-02T10:02:00.000Z',
  last_event_type: 'email.delivered',
  last_event_at: '2024-01-02T10:02:00.000Z',
  last_error: null,
  origin: 'finalization',
  resend_of_id: null,
  can_resend: true,
  ...overrides,
})

const makeHistory = (deliveries: OrderEmailDelivery[], documentStatus = 'ready'): OrderEmailHistory => ({
  document: {
    id: 'doc-1', version: 1, status: documentStatus, sha256: 'a'.repeat(64),
    size_bytes: 120 * 1024, generated_at: '2024-01-02T09:59:00.000Z',
  },
  deliveries,
})

function setupHandlers(summary: OrderSummary, history: OrderEmailHistory | 'empty' | number) {
  const calls = { emails: 0 }
  server.use(
    http.get('*/orders', () => HttpResponse.json([summary], { headers: { 'X-Has-More': 'false' } })),
    http.get('*/orders/history', () => HttpResponse.json([], { headers: { 'X-Has-More': 'false' } })),
    http.get('*/orders/order-1', () => HttpResponse.json(makeDetail(summary))),
    http.get('*/orders/order-1/emails', () => {
      calls.emails += 1
      if (typeof history === 'number') return HttpResponse.json({ detail: 'erro' }, { status: history })
      if (history === 'empty') return HttpResponse.json({ document: null, deliveries: [] })
      return HttpResponse.json(history)
    }),
    http.post('*/products/batch', () => HttpResponse.json([])),
    http.get('*/optionals', () => HttpResponse.json([])),
    http.get('*/optional-categories', () => HttpResponse.json([])),
  )
  return calls
}

async function openOrder(summary: OrderSummary) {
  const user = userEvent.setup()
  await screen.findAllByText(summary.code)
  await user.click(screen.getByLabelText(`Ver detalhes do orçamento ${summary.code}`))
  return user
}

describe('PedidosPage — aba E-mails', () => {
  beforeEach(() => server.resetHandlers())
  afterEach(() => vi.restoreAllMocks())

  it('não mostra a aba (nem muda a tela) com documento nulo, erro ou pedido em andamento', async () => {
    for (const scenario of ['empty', 500, 404] as const) {
      const summary = makeSummary()
      const calls = setupHandlers(summary, scenario)
      const { unmount } = renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
      await openOrder(summary)
      await screen.findByRole('button', { name: 'Detalhes' })
      await waitFor(() => expect(calls.emails).toBe(1))
      expect(screen.getByRole('button', { name: 'Histórico' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'E-mails' })).not.toBeInTheDocument()
      unmount()
    }

    const draft = makeSummary({ is_finalized: false, finalized_at: null })
    const calls = setupHandlers(draft, makeHistory([makeDelivery()]))
    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    await openOrder(draft)
    await screen.findByRole('button', { name: 'Detalhes' })
    expect(calls.emails).toBe(0)
    expect(screen.queryByRole('button', { name: 'E-mails' })).not.toBeInTheDocument()
  })

  it('lista as entregas com status legível e sem confundir aceito com entregue', async () => {
    const summary = makeSummary()
    setupHandlers(summary, makeHistory([
      makeDelivery({ id: 'd1', status: 'delivered' }),
      makeDelivery({ id: 'd2', status: 'accepted', delivered_at: null, recipient_roles: ['representative'], recipient_email: 'rep@example.test' }),
      makeDelivery({ id: 'd3', status: 'pending', accepted_at: null, delivered_at: null, next_attempt_at: '2024-01-02T11:00:00.000Z', attempts: 2, last_error: 'provider_unavailable' }),
      makeDelivery({ id: 'd4', status: 'processing', recipient_email: 'a@example.test' }),
      makeDelivery({ id: 'd5', status: 'failed', last_error: 'bounced', recipient_email: 'b@example.test' }),
      makeDelivery({ id: 'd6', status: 'blocked', recipient_email: null, last_error: 'missing_recipient', origin: 'manual_resend' }),
    ]))
    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user = await openOrder(summary)
    await user.click(await screen.findByRole('button', { name: 'E-mails' }))

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(6)
    expect(items[0]).toHaveTextContent('Entregue')
    expect(items[1]).toHaveTextContent('Aceito pelo serviço')
    expect(items[1]).not.toHaveTextContent('Entregue')
    expect(items[1]).toHaveTextContent('Aguardando confirmação de entrega.')
    expect(items[1]).toHaveTextContent('Representante')
    expect(items[2]).toHaveTextContent('Pendente')
    expect(items[2]).toHaveTextContent('Próxima tentativa em')
    expect(items[2]).toHaveTextContent('2 tentativas')
    expect(items[2]).toHaveTextContent('Serviço de e-mail indisponível')
    expect(items[3]).toHaveTextContent('Processando')
    expect(items[4]).toHaveTextContent('Falhou')
    expect(items[4]).toHaveTextContent('O endereço recusou a mensagem')
    expect(items[5]).toHaveTextContent('Sem e-mail válido')
    expect(items[5]).toHaveTextContent('Reenvio')
    expect(screen.getByText('PDF enviado').parentElement).toHaveTextContent('versão 1')
  })

  it('mostra Reenviar só para quem opera o pedido e quando a entrega permite', async () => {
    const summary = makeSummary()
    setupHandlers(summary, makeHistory([
      makeDelivery({ id: 'd1', can_resend: true }),
      makeDelivery({ id: 'd2', can_resend: false, recipient_email: 'x@example.test' }),
    ]))
    const first = renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user = await openOrder(summary)
    await user.click(await screen.findByRole('button', { name: 'E-mails' }))
    expect(screen.getAllByRole('button', { name: /^Reenviar para / })).toHaveLength(1)
    first.unmount()

    setupHandlers(summary, makeHistory([makeDelivery({ id: 'd1', can_resend: true })]))
    renderProductPage(<PedidosPage />, { ...productTestUser('cliente', 'BR'), linked_id: 'client-1' })
    const clientUser = await openOrder(summary)
    await clientUser.click(await screen.findByRole('button', { name: 'E-mails' }))
    expect(screen.getByRole('button', { name: 'Baixar PDF enviado' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Reenviar/ })).not.toBeInTheDocument()
  })

  it('confirma o reenvio e envia o payload; bloqueada força o e-mail atual do cadastro', async () => {
    const summary = makeSummary()
    const bodies: unknown[] = []
    setupHandlers(summary, makeHistory([
      makeDelivery({ id: 'd1' }),
      makeDelivery({ id: 'd2', status: 'blocked', recipient_email: null, last_error: 'missing_recipient', delivered_at: null, accepted_at: null }),
    ]))
    server.use(http.post('*/orders/order-1/emails/resend', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json(makeDelivery({ id: 'new', status: 'pending' }), { status: 201 })
    }))
    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user = await openOrder(summary)
    await user.click(await screen.findByRole('button', { name: 'E-mails' }))

    const [firstResend, secondResend] = screen.getAllByRole('button', { name: /^Reenviar para / })
    await user.click(firstResend)
    let dialog = await screen.findByRole('dialog', { name: 'Reenviar PDF' })
    expect(dialog).toHaveTextContent('cliente@example.test')
    const checkbox = screen.getByRole('checkbox', { name: /Usar o e-mail atual do cadastro/ })
    expect(checkbox).not.toBeChecked()
    await user.click(checkbox)
    await user.click(screen.getByRole('button', { name: 'Reenviar' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Reenvio solicitado.')
    expect(bodies[0]).toEqual({ delivery_id: 'd1', use_current_address: true })

    await user.click(secondResend)
    dialog = await screen.findByRole('dialog', { name: 'Reenviar PDF' })
    const forced = screen.getByRole('checkbox', { name: /Usar o e-mail atual do cadastro/ })
    expect(forced).toBeChecked()
    expect(forced).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Reenviar' }))
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1]).toEqual({ delivery_id: 'd2', use_current_address: true })
  })

  it('traduz os erros do reenvio (409 pendente, 409 desativado, 403, 500)', async () => {
    const cases: Array<[number, { detail: string }, string]> = [
      [409, { detail: 'Já existe uma entrega pendente.' }, 'Já existe um envio pendente para este destinatário.'],
      [409, { detail: 'Envio de e-mail desativado.' }, 'O envio de e-mails está desativado.'],
      [403, { detail: 'Acesso negado.' }, 'Você não tem permissão para reenviar.'],
      [500, { detail: 'x' }, 'Não foi possível solicitar o reenvio. Tente novamente.'],
    ]
    for (const [status, body, message] of cases) {
      const summary = makeSummary()
      setupHandlers(summary, makeHistory([makeDelivery()]))
      server.use(http.post('*/orders/order-1/emails/resend', () => HttpResponse.json(body, { status })))
      const { unmount } = renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
      const user = await openOrder(summary)
      await user.click(await screen.findByRole('button', { name: 'E-mails' }))
      await user.click(screen.getByRole('button', { name: /^Reenviar para / }))
      await screen.findByRole('dialog', { name: 'Reenviar PDF' })
      await user.click(screen.getByRole('button', { name: 'Reenviar' }))
      expect(await screen.findByRole('alert')).toHaveTextContent(message)
      unmount()
    }
  })

  it('baixa o PDF enviado com o cliente autenticado e trata 403/404', async () => {
    const summary = makeSummary()
    setupHandlers(summary, makeHistory([makeDelivery()]))
    const create = vi.fn(() => 'blob:pdf')
    const revoke = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: create })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: revoke })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    server.use(http.get('*/orders/order-1/email-document', () => new HttpResponse(new Uint8Array([37, 80, 68, 70]), {
      headers: { 'Content-Type': 'application/pdf' },
    })))
    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user = await openOrder(summary)
    await user.click(await screen.findByRole('button', { name: 'E-mails' }))
    await user.click(screen.getByRole('button', { name: 'Baixar PDF enviado' }))
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1))
    expect(create).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:pdf'), { timeout: 3000 })

    server.use(http.get('*/orders/order-1/email-document', () => HttpResponse.json({ detail: 'x' }, { status: 403 })))
    await user.click(screen.getByRole('button', { name: 'Baixar PDF enviado' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Você não tem permissão para baixar este PDF.')

    server.use(http.get('*/orders/order-1/email-document', () => HttpResponse.json({ detail: 'x' }, { status: 404 })))
    await user.click(screen.getByRole('button', { name: 'Baixar PDF enviado' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('O PDF ainda não está disponível.'))
  })

  it('sem PDF pronto não oferece download', async () => {
    const summary = makeSummary()
    setupHandlers(summary, makeHistory([makeDelivery({ status: 'pending', accepted_at: null, delivered_at: null })], 'pending'))
    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user = await openOrder(summary)
    await user.click(await screen.findByRole('button', { name: 'E-mails' }))
    expect(screen.queryByRole('button', { name: 'Baixar PDF enviado' })).not.toBeInTheDocument()
    expect(screen.getByText('O PDF está sendo preparado.')).toBeInTheDocument()
  })

  it('pedido europeu em inglês usa rótulos em inglês', async () => {
    const summary = makeSummary({ market_code: 'EU', currency: 'EUR' })
    const euUser = productTestUser('admin', 'EU')
    localStorage.setItem(`ilya-locale:${euUser.id}:EU`, 'en-GB')
    setupHandlers(summary, makeHistory([
      makeDelivery({ id: 'd1', status: 'accepted', delivered_at: null }),
      makeDelivery({ id: 'd2', status: 'delivered', recipient_roles: ['client', 'representative'] }),
    ]))
    renderProductPage(<PedidosPage />, euUser)
    const user = userEvent.setup()
    await screen.findAllByText(summary.code)
    await user.click(screen.getByLabelText('Ver detalhes do orçamento PED-0001'))
    await user.click(await screen.findByRole('button', { name: 'Emails' }))
    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Accepted by the service')
    expect(items[0]).toHaveTextContent('Awaiting delivery confirmation.')
    expect(items[1]).toHaveTextContent('Client and representative')
    expect(screen.getByRole('button', { name: 'Download sent PDF' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Resend to / })).toHaveLength(2)
  })

  it('atualiza a lista enquanto houver entrega em andamento e para quando todas terminam', async () => {
    const summary = makeSummary()
    let version = 0
    setupHandlers(summary, makeHistory([makeDelivery({ status: 'pending', accepted_at: null, delivered_at: null })]))
    server.use(http.get('*/orders/order-1/emails', () => {
      version += 1
      return HttpResponse.json(makeHistory([makeDelivery({ status: version === 1 ? 'pending' : 'delivered' })]))
    }))
    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user = await openOrder(summary)
    await user.click(await screen.findByRole('button', { name: 'E-mails' }))
    expect(await screen.findByText('Pendente')).toBeInTheDocument()

    vi.useFakeTimers({ toFake: ['setTimeout', 'setInterval'], shouldAdvanceTime: true })
    try {
      await vi.advanceTimersByTimeAsync(15_500)
      await waitFor(() => expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('Entregue'))
      const afterTerminal = version
      await vi.advanceTimersByTimeAsync(45_000)
      expect(version).toBe(afterTerminal)
    } finally {
      vi.useRealTimers()
    }
  })

  it('mostra Enviar e-mail de teste apenas quando test_send_available é verdadeiro', async () => {
    const summary = makeSummary()
    setupHandlers(summary, makeHistory([makeDelivery()]))
    const absent = renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user1 = await openOrder(summary)
    await user1.click(await screen.findByRole('button', { name: 'E-mails' }))
    expect(screen.queryByRole('button', { name: 'Enviar e-mail de teste' })).not.toBeInTheDocument()
    absent.unmount()

    setupHandlers(summary, { ...makeHistory([makeDelivery()]), test_send_available: false })
    const repRender = renderProductPage(<PedidosPage />, productTestUser('representante', 'BR'))
    const repUser = await openOrder(summary)
    await repUser.click(await screen.findByRole('button', { name: 'E-mails' }))
    expect(screen.queryByRole('button', { name: 'Enviar e-mail de teste' })).not.toBeInTheDocument()
    repRender.unmount()

    setupHandlers(summary, { ...makeHistory([makeDelivery()]), test_send_available: true })
    renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const adminUser = await openOrder(summary)
    await adminUser.click(await screen.findByRole('button', { name: 'E-mails' }))
    expect(screen.getByRole('button', { name: 'Enviar e-mail de teste' })).toBeInTheDocument()
  })

  it('solicita envio de teste via POST com recipient_email, exibe aviso e traduz rótulo em en-GB', async () => {
    const summary = makeSummary()
    const bodies: unknown[] = []
    setupHandlers(summary, { ...makeHistory([makeDelivery()]), test_send_available: true })
    server.use(http.post('*/orders/order-1/emails/test-send', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json(
        makeDelivery({ id: 'test-1', status: 'pending', recipient_email: 'admin@example.test', origin: 'manual_resend' }),
        { status: 201 },
      )
    }))

    const brRender = renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
    const user = await openOrder(summary)
    await user.click(await screen.findByRole('button', { name: 'E-mails' }))
    await user.click(screen.getByRole('button', { name: 'Enviar e-mail de teste' }))

    const dialog = await screen.findByRole('dialog', { name: 'Enviar e-mail de teste' })
    expect(dialog).toHaveTextContent('O envio passa pela fila e só chega a endereços da lista de teste.')
    const input = screen.getByLabelText('E-mail de teste')
    expect(input).toHaveAttribute('type', 'email')
    expect(input).toBeRequired()
    await user.type(input, 'admin@example.test')
    await user.click(screen.getByRole('button', { name: 'Enviar teste' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Envio de teste solicitado.')
    expect(bodies).toEqual([{ recipient_email: 'admin@example.test' }])
    brRender.unmount()

    const euSummary = makeSummary({ market_code: 'EU', currency: 'EUR' })
    const euUser = productTestUser('admin', 'EU')
    localStorage.setItem(`ilya-locale:${euUser.id}:EU`, 'en-GB')
    setupHandlers(euSummary, { ...makeHistory([makeDelivery()]), test_send_available: true })
    renderProductPage(<PedidosPage />, euUser)
    const euInteraction = userEvent.setup()
    await screen.findAllByText(euSummary.code)
    await euInteraction.click(screen.getByLabelText('Ver detalhes do orçamento PED-0001'))
    await euInteraction.click(await screen.findByRole('button', { name: 'Emails' }))
    expect(screen.getByRole('button', { name: 'Send test email' })).toBeInTheDocument()
  })

  it('traduz os erros do envio de teste (409 modo, 409 pendente, 403, 422, 500)', async () => {
    const cases: Array<[number, { detail: string }, string]> = [
      [409, { detail: 'Envio de teste disponível apenas no modo de teste.' }, 'O modo de teste não está ativo.'],
      [409, { detail: 'Já existe um envio pendente para este destinatário.' }, 'Já existe um envio pendente para este e-mail.'],
      [403, { detail: 'Acesso negado.' }, 'Você não tem permissão para enviar o teste.'],
      [422, { detail: 'E-mail inválido.' }, 'E-mail inválido.'],
      [500, { detail: 'x' }, 'Não foi possível solicitar o envio de teste. Tente novamente.'],
    ]
    for (const [status, body, message] of cases) {
      const summary = makeSummary()
      setupHandlers(summary, { ...makeHistory([makeDelivery()]), test_send_available: true })
      server.use(http.post('*/orders/order-1/emails/test-send', () => HttpResponse.json(body, { status })))
      const { unmount } = renderProductPage(<PedidosPage />, productTestUser('admin', 'BR'))
      const user = await openOrder(summary)
      await user.click(await screen.findByRole('button', { name: 'E-mails' }))
      await user.click(screen.getByRole('button', { name: 'Enviar e-mail de teste' }))
      await screen.findByRole('dialog', { name: 'Enviar e-mail de teste' })
      await user.type(screen.getByLabelText('E-mail de teste'), 'admin@example.test')
      await user.click(screen.getByRole('button', { name: 'Enviar teste' }))
      expect(await screen.findByRole('alert')).toHaveTextContent(message)
      unmount()
    }
  })
})
