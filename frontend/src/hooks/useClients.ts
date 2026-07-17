import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { Client, ClientCreate, ClientUpdate } from '../types'

const KEY = 'clients'

export function useClients() {
  return useQuery<Client[]>({
    queryKey: [KEY],
    queryFn: async () => (await api.get('/clients')).data,
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
