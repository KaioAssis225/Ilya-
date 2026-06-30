import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface OptionalCategory {
  id: string
  name: string
  code: string
}

const KEY = ['optional-categories']

export function useOptionalCategories() {
  return useQuery<OptionalCategory[]>({
    queryKey: KEY,
    queryFn: () => api.get<OptionalCategory[]>('/optional-categories').then(r => r.data),
  })
}

export function useCreateOptionalCategory() {
  const qc = useQueryClient()
  return useMutation<OptionalCategory, { response?: { data?: { detail?: string } } }, { name: string; code: string }>({
    mutationFn: (payload) => api.post<OptionalCategory>('/optional-categories', payload).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateOptionalCategory() {
  const qc = useQueryClient()
  return useMutation<OptionalCategory, { response?: { data?: { detail?: string } } }, { id: string; name: string; code: string }>({
    mutationFn: ({ id, ...rest }) => api.put<OptionalCategory>(`/optional-categories/${id}`, rest).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteOptionalCategory() {
  const qc = useQueryClient()
  return useMutation<void, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (id) => api.delete(`/optional-categories/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
