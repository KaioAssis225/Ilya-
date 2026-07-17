import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { Order, OrderCreate, OrderUpdate, OrderHistory, OrderSummary } from '../types'

const KEY = 'orders'

export interface OrderListFilters {
  cursor?: string
  limit?: number
  q?: string
  client_id?: string
  rep_id?: string
  client_name?: string
  rep_name?: string
  status?: 'in_progress' | 'finalized' | 'cancelled' | ''
  date_from?: string
  date_to?: string
}

export interface OrderListPage {
  items: OrderSummary[]
  nextCursor: string | null
  hasMore: boolean
}

export interface OrderHistoryPage {
  items: OrderHistory[]
  nextCursor: string | null
  hasMore: boolean
}

export function useOrders(filters: OrderListFilters = {}) {
  return useQuery<OrderListPage>({
    queryKey: [KEY, 'list', filters],
    queryFn: async () => {
      const params = Object.fromEntries(
        Object.entries(filters).filter(([, value]) => value !== undefined && value !== ''),
      )
      const response = await api.get<OrderSummary[]>('/orders', { params })
      return {
        items: response.data,
        nextCursor: response.headers['x-next-cursor'] ?? null,
        hasMore: response.headers['x-has-more'] === 'true',
      }
    },
  })
}

export function useOrder(idOrCode: string) {
  return useQuery<Order>({
    queryKey: [KEY, idOrCode],
    queryFn: async () => (await api.get(`/orders/${idOrCode}`)).data,
    enabled: !!idOrCode,
  })
}

export function useCreateOrder() {
  const qc = useQueryClient()
  return useMutation<Order, Error, OrderCreate>({
    mutationFn: (data) => api.post('/orders', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdateOrder() {
  const qc = useQueryClient()
  return useMutation<Order, Error, { id: string; data: OrderUpdate }>({
    mutationFn: ({ id, data }) => api.put(`/orders/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useFinalizeOrder() {
  const qc = useQueryClient()
  return useMutation<Order, Error, { id: string; external_code?: string }>({
    mutationFn: ({ id, external_code }) =>
      api.post(`/orders/${id}/finalize`, { external_code: external_code ?? null }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useCancelOrder() {
  const qc = useQueryClient()
  return useMutation<Order, Error, { id: string; reason?: string }>({
    mutationFn: ({ id, reason }) =>
      api.post(`/orders/${id}/cancel`, { reason: reason ?? null }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useOrderHistory(orderId: string | null) {
  return useQuery<OrderHistory[]>({
    queryKey: [KEY, orderId, 'history'],
    queryFn: async () => (await api.get(`/orders/${orderId}/history`)).data,
    enabled: !!orderId,
  })
}

export function useGlobalOrderHistory(cursor?: string, enabled = true) {
  return useQuery<OrderHistoryPage>({
    queryKey: [KEY, 'history', cursor],
    queryFn: async () => {
      const response = await api.get<OrderHistory[]>('/orders/history', {
        params: { cursor, limit: 100 },
      })
      return {
        items: response.data,
        nextCursor: response.headers['x-next-cursor'] ?? null,
        hasMore: response.headers['x-has-more'] === 'true',
      }
    },
    enabled,
  })
}

export function useDeleteOrder() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/orders/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
