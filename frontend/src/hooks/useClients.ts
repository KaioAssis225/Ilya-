import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { Client, ClientCreate, ClientUpdate, PageResult } from '../types'

const KEY = 'clients'

export interface ClientPageParams {
  skip?: number
  limit?: number
  q?: string
  include_total?: boolean
  sort_by?: 'name' | 'email' | 'phone' | 'city' | 'state' | 'max_discount'
  sort_dir?: 'asc' | 'desc'
}

export function useClientsPage(params: ClientPageParams, enabled = true) {
  return useQuery<PageResult<Client>>({
    queryKey: [KEY, 'page', params],
    queryFn: async () => {
      const response = await api.get<Client[]>('/clients', { params })
      return {
        items: response.data,
        total: Number(response.headers['x-total-count'] ?? response.data.length),
        hasMore: String(response.headers['x-has-more'] ?? 'false') === 'true',
        pageSize: Number(response.headers['x-page-size'] ?? response.data.length),
      }
    },
    enabled,
    staleTime: 30_000,
  })
}

export function useClient(id: string, enabled = true) {
  return useQuery<Client>({
    queryKey: [KEY, id],
    queryFn: async () => (await api.get(`/clients/${id}`)).data,
    enabled: enabled && !!id,
  })
}

export function useCreateClient() {
  const qc = useQueryClient()
  return useMutation<Client, Error, ClientCreate>({
    mutationFn: (data) => api.post('/clients', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdateClient() {
  const qc = useQueryClient()
  return useMutation<Client, Error, { id: string; data: ClientUpdate }>({
    mutationFn: ({ id, data }) => api.patch(`/clients/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useDeleteClient() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/clients/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
