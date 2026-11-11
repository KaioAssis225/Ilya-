import { useQuery } from '@tanstack/react-query'
import { fetchStockOrigin } from '../lib/stockHandoff'

/**
 * Origem do Estoque, vinda do servidor. Falha (403/503) significa "sem link":
 * o menu esconde o item, sem repetir a chamada.
 */
export function useStockLink(userId: string | undefined, enabled: boolean) {
  return useQuery<string>({
    queryKey: ['stock', 'link', userId],
    queryFn: fetchStockOrigin,
    enabled: enabled && Boolean(userId),
    retry: false,
    staleTime: 5 * 60_000,
  })
}
