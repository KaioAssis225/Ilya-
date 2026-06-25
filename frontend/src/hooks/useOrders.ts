import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { Order, OrderCreate } from '../types'

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

export function useDeleteOrder() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/orders/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
