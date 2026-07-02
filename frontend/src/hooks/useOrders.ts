import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { Order, OrderCreate, OrderUpdate, OrderHistory } from '../types'

const KEY = 'orders'

export function useOrders() {
  return useQuery<Order[]>({
    queryKey: [KEY],
    queryFn: async () => (await api.get('/orders')).data,
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

export function useOrderHistory(orderId: string | null) {
  return useQuery<OrderHistory[]>({
    queryKey: [KEY, orderId, 'history'],
    queryFn: async () => (await api.get(`/orders/${orderId}/history`)).data,
    enabled: !!orderId,
  })
}

export function useGlobalOrderHistory(enabled = true) {
  return useQuery<OrderHistory[]>({
    queryKey: [KEY, 'history'],
    queryFn: async () => (await api.get('/orders/history')).data,
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
