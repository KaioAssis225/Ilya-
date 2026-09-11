import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface Catalog {
  id: string
  name: string
}

const KEY = ['catalogs']

export function useCatalogs() {
  return useQuery<Catalog[]>({
    queryKey: KEY,
    queryFn: () => api.get<Catalog[]>('/catalogs').then(r => r.data),
  })
}

export function useCreateCatalog() {
  const qc = useQueryClient()
  return useMutation<Catalog, { response?: { data?: { detail?: string } } }, { name: string }>({
    mutationFn: (payload) => api.post<Catalog>('/catalogs', payload).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateCatalog() {
  const qc = useQueryClient()
  return useMutation<Catalog, { response?: { data?: { detail?: string } } }, { id: string; name: string }>({
    mutationFn: ({ id, name }) => api.put<Catalog>(`/catalogs/${id}`, { name }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteCatalog() {
  const qc = useQueryClient()
  return useMutation<void, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (id) => api.delete(`/catalogs/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
