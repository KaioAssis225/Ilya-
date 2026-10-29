import { useState } from 'react'
import axios from 'axios'
import {
  AlertTriangle, Ban, CheckCircle2, Clock, Download, LoaderCircle, MinusCircle, Send, XCircle,
} from 'lucide-react'
import { Dialog } from './Dialog'
import { downloadOrderEmailDocument, useResendOrderEmail } from '../hooks/useOrderEmails'
import {
  emailErrorMessage, emailRolesLabel, emailStatusInfo, formatEmailFileSize,
  type EmailStatusIcon, type EmailTone,
} from '../lib/orderEmailLabels'
import type { OrderEmailDelivery, OrderEmailHistory } from '../types'

const TONE_CLASS: Record<EmailTone, string> = {
  success: 'bg-success-soft text-success border-success/25',
  danger: 'bg-danger-soft text-danger border-danger/25',
  warning: 'bg-warning-soft text-warning border-warning/25',
  info: 'bg-info-soft text-info border-info/25',
  neutral: 'bg-bg-2 text-ink-3 border-line',
}

const STATUS_ICON: Record<EmailStatusIcon, typeof Clock> = {
  clock: Clock,
  loader: LoaderCircle,
  send: Send,
  delivered: CheckCircle2,
  failed: XCircle,
  alert: AlertTriangle,
  blocked: Ban,
  skipped: MinusCircle,
}

interface PanelProps {
  orderId: string
  orderCode: string
  history: OrderEmailHistory
  /** Mesmo critério de `viewText` do modal: pedido EU com o usuário em en-GB. */
  english: boolean
  /** Locale de datas e números (pt-BR, pt-PT ou en-GB). */
  dateLocale: string
  /** Quem opera o pedido (a API ainda valida; aqui só decide se o botão existe). */
  canResend: boolean
}

function errorStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined
}

function errorDetail(error: unknown): string | undefined {
  if (!axios.isAxiosError(error)) return undefined
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
  return typeof detail === 'string' ? detail : undefined
}

export function OrderEmailsPanel({ orderId, orderCode, history, english, dateLocale, canResend }: PanelProps) {
  const tx = (pt: string, en: string) => (english ? en : pt)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [resendTarget, setResendTarget] = useState<OrderEmailDelivery | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const { document: doc, deliveries } = history

  const fmtDateTime = (value: string) =>
    new Date(value).toLocaleString(dateLocale, { dateStyle: 'short', timeStyle: 'short' })

  async function download() {
    setDownloading(true)
    setDownloadError(null)
    try {
      await downloadOrderEmailDocument(orderId, `${orderCode}.pdf`)
    } catch (error) {
      const status = errorStatus(error)
      setDownloadError(
        status === 403
          ? tx('Você não tem permissão para baixar este PDF.', 'You do not have permission to download this PDF.')
          : status === 404
            ? tx('O PDF ainda não está disponível.', 'The PDF is not available yet.')
            : tx('Não foi possível baixar o PDF. Tente novamente.', 'Could not download the PDF. Please try again.'),
      )
    } finally {
      setDownloading(false)
    }
  }

  const size = formatEmailFileSize(doc?.size_bytes, dateLocale)

  return (
    <div className="space-y-4 pt-1">
      {doc && (
        <div className="flex flex-col gap-2 rounded-lg border border-line bg-bg p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-2">
            <span className="font-medium text-ink">{tx('PDF enviado', 'PDF sent')}</span>
            {' · '}{tx('versão', 'version')} {doc.version}
            {size && <> · {size}</>}
            {doc.generated_at && <> · {tx('gerado em', 'generated on')} {fmtDateTime(doc.generated_at)}</>}
          </p>
          {doc.status === 'ready' ? (
            <button
              type="button"
              onClick={download}
              disabled={downloading}
              className="btn-secondary inline-flex min-h-11 items-center justify-center gap-1.5 text-xs disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              {downloading ? tx('Baixando…', 'Downloading…') : tx('Baixar PDF enviado', 'Download sent PDF')}
            </button>
          ) : (
            <p className="text-xs text-muted">
              {doc.status === 'failed'
                ? tx('Não foi possível gerar o PDF.', 'Could not generate the PDF.')
                : tx('O PDF está sendo preparado.', 'The PDF is being prepared.')}
            </p>
          )}
        </div>
      )}
      {downloadError && <p role="alert" className="text-xs font-medium text-danger">{downloadError}</p>}
      {notice && <p role="status" className="text-xs font-medium text-success">{notice}</p>}

      <ul role="list" className="space-y-2">
        {deliveries.map((delivery) => {
          const info = emailStatusInfo(delivery.status, english)
          const Icon = STATUS_ICON[info.icon]
          const errorText = emailErrorMessage(delivery.last_error, english)
          const dates: string[] = []
          if (delivery.accepted_at) dates.push(`${tx('Aceito em', 'Accepted on')} ${fmtDateTime(delivery.accepted_at)}`)
          if (delivery.delivered_at) dates.push(`${tx('Entregue em', 'Delivered on')} ${fmtDateTime(delivery.delivered_at)}`)
          if (delivery.status === 'pending' && delivery.next_attempt_at) {
            dates.push(`${tx('Próxima tentativa em', 'Next attempt on')} ${fmtDateTime(delivery.next_attempt_at)}`)
          }
          if (delivery.attempts > 0) {
            dates.push(
              english
                ? `${delivery.attempts} ${delivery.attempts === 1 ? 'attempt' : 'attempts'}`
                : `${delivery.attempts} ${delivery.attempts === 1 ? 'tentativa' : 'tentativas'}`,
            )
          }
          return (
            <li key={delivery.id} className="rounded-lg border border-line bg-white p-3 sm:p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    {emailRolesLabel(delivery.recipient_roles, english)}
                    {delivery.origin === 'manual_resend' && (
                      <span className="rounded border border-line bg-bg-2 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ink-3">
                        {tx('Reenvio', 'Resend')}
                      </span>
                    )}
                  </p>
                  <p className="break-all text-sm text-ink">{delivery.recipient_email ?? '—'}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold ${TONE_CLASS[info.tone]}`}>
                    <Icon className="h-3 w-3" aria-hidden="true" />
                    {info.label}
                  </span>
                  {canResend && delivery.can_resend && (
                    <button
                      type="button"
                      onClick={() => { setNotice(null); setResendTarget(delivery) }}
                      aria-label={delivery.recipient_email
                        ? `${tx('Reenviar para', 'Resend to')} ${delivery.recipient_email}`
                        : tx('Reenviar para o e-mail atual do cadastro', 'Resend to the email currently on record')}
                      className="btn-secondary min-h-11 text-xs sm:min-h-0"
                    >
                      {tx('Reenviar', 'Resend')}
                    </button>
                  )}
                </div>
              </div>
              {dates.length > 0 && <p className="mt-2 text-xs text-ink-3">{dates.join(' · ')}</p>}
              {info.hint && <p className="mt-1 text-xs text-muted">{info.hint}</p>}
              {errorText && <p className="mt-1 text-xs text-danger">{errorText}</p>}
            </li>
          )
        })}
      </ul>

      {resendTarget && (
        <ResendDialog
          key={resendTarget.id}
          orderId={orderId}
          delivery={resendTarget}
          english={english}
          onClose={() => setResendTarget(null)}
          onDone={() => {
            setResendTarget(null)
            setNotice(tx('Reenvio solicitado.', 'Resend requested.'))
          }}
        />
      )}
    </div>
  )
}

function ResendDialog({ orderId, delivery, english, onClose, onDone }: {
  orderId: string
  delivery: OrderEmailDelivery
  english: boolean
  onClose: () => void
  onDone: () => void
}) {
  const tx = (pt: string, en: string) => (english ? en : pt)
  const forced = delivery.status === 'blocked' || !delivery.recipient_email
  const [useCurrent, setUseCurrent] = useState(forced)
  const [error, setError] = useState<string | null>(null)
  const resend = useResendOrderEmail(orderId)

  async function confirm() {
    setError(null)
    try {
      await resend.mutateAsync({ deliveryId: delivery.id, useCurrentAddress: forced || useCurrent })
      onDone()
    } catch (err) {
      const status = errorStatus(err)
      if (status === 409) {
        setError(
          errorDetail(err) === 'Envio de e-mail desativado.'
            ? tx('O envio de e-mails está desativado.', 'Email sending is turned off.')
            : tx('Já existe um envio pendente para este destinatário.', 'There is already a pending send for this recipient.'),
        )
      } else if (status === 403) {
        setError(tx('Você não tem permissão para reenviar.', 'You do not have permission to resend.'))
      } else {
        setError(tx('Não foi possível solicitar o reenvio. Tente novamente.', 'Could not request the resend. Please try again.'))
      }
    }
  }

  return (
    <Dialog
      layer="sub"
      title={tx('Reenviar PDF', 'Resend PDF')}
      onClose={onClose}
      dismissible={!resend.isPending}
    >
      <p className="mb-3 text-sm text-ink-2">
        {delivery.recipient_email
          ? <>{tx('Reenviar o PDF para', 'Resend the PDF to')} <span className="break-all font-medium text-ink">{delivery.recipient_email}</span>?</>
          : tx('Reenviar o PDF usando o e-mail atual do cadastro?', 'Resend the PDF using the email currently on record?')}
      </p>
      <label className="mb-4 flex items-start gap-2 text-sm text-ink-2">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4"
          checked={useCurrent}
          disabled={forced}
          onChange={(event) => setUseCurrent(event.target.checked)}
        />
        <span>
          {tx('Usar o e-mail atual do cadastro', 'Use the email currently on record')}
          {forced && (
            <span className="mt-0.5 block text-xs text-muted">
              {tx('O cadastro será lido novamente porque esta entrega não tem e-mail válido.', 'The record will be read again because this delivery has no valid email.')}
            </span>
          )}
        </span>
      </label>
      {error && <p role="alert" className="mb-3 text-xs font-medium text-danger">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} disabled={resend.isPending} className="btn-secondary min-h-11 text-xs sm:min-h-0">
          {tx('Cancelar', 'Cancel')}
        </button>
        <button type="button" onClick={confirm} disabled={resend.isPending} className="btn-primary min-h-11 text-xs sm:min-h-0">
          {resend.isPending ? tx('Enviando…', 'Sending…') : tx('Reenviar', 'Resend')}
        </button>
      </div>
    </Dialog>
  )
}
