import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import type { EuVatRateView } from '../lib/euVatRate'

/**
 * Taxa única de IVA de Portugal, só para a prévia do orçamento. O valor oficial
 * (e o que fica gravado no pedido) é sempre o do servidor.
 */
export function useEuVatRate(enabled: boolean) {
  return useQuery<EuVatRateView>({
    queryKey: ['markets', 'eu-vat-rate'],
    queryFn: () => api.get<EuVatRateView>('/markets/EU/vat-rate').then(response => response.data),
    enabled,
    staleTime: 60_000,
  })
}
