import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { LIVE_EMAIL_STATUSES } from '../lib/orderEmailLabels'
import type { OrderEmailDelivery, OrderEmailHistory } from '../types'

const POLL_MS = 15_000

export const orderEmailsKey = (orderId: string) => ['orders', orderId, 'emails'] as const

/**
 * Histórico de e-mails do pedido. Falha (404, 500) ou `document: null` significam
 * "nada a mostrar": o chamador não renderiza nada, então a tela fica igual à de
 * antes enquanto ORDER_EMAIL_MODE=off. Só atualiza sozinho com a aba aberta e
 * enquanto houver entrega cujo resultado ainda pode mudar.
 */
export function useOrderEmails(orderId: string, options: { enabled: boolean; active: boolean }) {
  return useQuery<OrderEmailHistory>({
    queryKey: orderEmailsKey(orderId),
    queryFn: async () => (await api.get<OrderEmailHistory>(`/orders/${orderId}/emails`)).data,
    enabled: options.enabled && !!orderId,
    retry: false,
    refetchInterval: (query) =>
      options.active && query.state.data?.deliveries.some((d) => LIVE_EMAIL_STATUSES.has(d.status))
        ? POLL_MS
        : false,
  })
}

export function useResendOrderEmail(orderId: string) {
  const queryClient = useQueryClient()
  return useMutation<OrderEmailDelivery, Error, { deliveryId: string; useCurrentAddress: boolean }>({
    mutationFn: async ({ deliveryId, useCurrentAddress }) =>
      (await api.post<OrderEmailDelivery>(`/orders/${orderId}/emails/resend`, {
        delivery_id: deliveryId,
        use_current_address: useCurrentAddress,
      })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: orderEmailsKey(orderId) }),
  })
}

/** Baixa o PDF enviado pelo cliente autenticado (o endpoint exige o token). */
export async function downloadOrderEmailDocument(orderId: string, filename: string): Promise<void> {
  const response = await api.get<Blob>(`/orders/${orderId}/email-document`, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    // Safari/Firefox podem abortar o download se a URL for revogada na hora.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
