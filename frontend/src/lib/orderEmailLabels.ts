import type { OrderEmailRole, OrderEmailStatus } from '../types'

// Rótulos, dicas e tom visual do histórico de e-mails do pedido. Funções puras:
// `english` segue o mesmo critério do modal (pedido EU com o usuário em en-GB).

export type EmailTone = 'success' | 'danger' | 'warning' | 'info' | 'neutral'
export type EmailStatusIcon =
  | 'clock' | 'loader' | 'send' | 'delivered' | 'failed' | 'alert' | 'blocked' | 'skipped'

export interface EmailStatusInfo {
  label: string
  hint: string | null
  tone: EmailTone
  icon: EmailStatusIcon
}

const pick = (english: boolean, pt: string, en: string) => (english ? en : pt)

// Estados em que o resultado ainda pode mudar sozinho (justificam atualizar a lista).
export const LIVE_EMAIL_STATUSES: ReadonlySet<string> = new Set(['pending', 'processing', 'accepted'])

export function emailStatusInfo(status: OrderEmailStatus | string, english: boolean): EmailStatusInfo {
  switch (status) {
    case 'pending':
      return { label: pick(english, 'Pendente', 'Pending'), hint: null, tone: 'warning', icon: 'clock' }
    case 'processing':
      return { label: pick(english, 'Processando', 'Processing'), hint: null, tone: 'info', icon: 'loader' }
    case 'accepted':
      return {
        label: pick(english, 'Aceito pelo serviço', 'Accepted by the service'),
        hint: pick(english, 'Aguardando confirmação de entrega.', 'Awaiting delivery confirmation.'),
        tone: 'info',
        icon: 'send',
      }
    case 'delivered':
      return { label: pick(english, 'Entregue', 'Delivered'), hint: null, tone: 'success', icon: 'delivered' }
    case 'failed':
      return { label: pick(english, 'Falhou', 'Failed'), hint: null, tone: 'danger', icon: 'failed' }
    case 'needs_review':
      return {
        label: pick(english, 'Requer revisão', 'Needs review'),
        hint: pick(english, 'Resultado incerto; confira antes de reenviar.', 'Outcome uncertain; check before resending.'),
        tone: 'warning',
        icon: 'alert',
      }
    case 'blocked':
      return { label: pick(english, 'Sem e-mail válido', 'No valid email'), hint: null, tone: 'danger', icon: 'blocked' }
    case 'skipped':
      return {
        label: pick(english, 'Não enviado (modo de teste)', 'Not sent (test mode)'),
        hint: null,
        tone: 'neutral',
        icon: 'skipped',
      }
    default:
      return { label: String(status), hint: null, tone: 'neutral', icon: 'clock' }
  }
}

export function emailRolesLabel(roles: OrderEmailRole[], english: boolean): string {
  // Envio de teste manual (admin): sem papel de cliente/representante.
  if (roles.length === 0) return pick(english, 'Teste', 'Test')
  const client = roles.includes('client')
  const rep = roles.includes('representative')
  if (client && rep) return pick(english, 'Cliente e representante', 'Client and representative')
  if (rep) return pick(english, 'Representante', 'Representative')
  return pick(english, 'Cliente', 'Client')
}

const ERROR_MESSAGES: Record<string, [string, string]> = {
  missing_recipient: ['O cadastro não tem e-mail.', 'The record has no email address.'],
  invalid_recipient: ['O e-mail cadastrado é inválido.', 'The registered email address is invalid.'],
  not_in_allowlist: ['Destinatário fora da lista de teste.', 'Recipient is not on the test list.'],
  provider_unavailable: ['Serviço de e-mail indisponível; nova tentativa automática.', 'Email service unavailable; retrying automatically.'],
  provider_auth: ['Falha de autenticação no serviço de e-mail.', 'Authentication failed with the email service.'],
  provider_rejected: ['O serviço de e-mail recusou a mensagem.', 'The email service rejected the message.'],
  provider_invalid_response: ['Resposta inesperada do serviço de e-mail.', 'Unexpected response from the email service.'],
  attachment_too_large: ['O PDF excede o tamanho permitido.', 'The PDF exceeds the allowed size.'],
  bounced: ['O endereço recusou a mensagem (e-mail devolvido).', 'The address bounced the message.'],
  provider_failed: ['O serviço de e-mail não conseguiu entregar.', 'The email service could not deliver.'],
  renderer_unavailable: ['O PDF ainda não pôde ser gerado.', 'The PDF could not be generated yet.'],
  render_failed: ['Falha ao gerar o PDF.', 'Failed to generate the PDF.'],
  invalid_pdf: ['O PDF gerado é inválido.', 'The generated PDF is invalid.'],
  storage_not_configured: ['Armazenamento do PDF não configurado.', 'PDF storage is not configured.'],
  storage_unavailable: ['Armazenamento do PDF indisponível.', 'PDF storage unavailable.'],
  document_not_found: ['O arquivo do PDF não foi encontrado.', 'The PDF file was not found.'],
}

export function emailErrorMessage(code: string | null | undefined, english: boolean): string | null {
  if (!code) return null
  const entry = ERROR_MESSAGES[code]
  return entry ? pick(english, entry[0], entry[1]) : pick(english, 'Erro no envio.', 'Sending error.')
}

export function formatEmailFileSize(bytes: number | null | undefined, locale: string): string | null {
  if (bytes == null) return null
  const kb = bytes / 1024
  if (kb < 1024) return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Math.max(1, Math.round(kb)))} KB`
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(kb / 1024)} MB`
}
