import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface ProductGroup {
  id: string
  name: string
  ipi: number
}

const KEY = ['product-groups']

export function useProductGroups() {
  return useQuery<ProductGroup[]>({
    queryKey: KEY,
    queryFn: () => api.get<ProductGroup[]>('/product-groups').then(r => r.data),
  })
}

export function useCreateProductGroup() {
  const qc = useQueryClient()
  return useMutation<ProductGroup, { response?: { data?: { detail?: string } } }, { name: string; ipi: number }>({
    mutationFn: (payload) => api.post<ProductGroup>('/product-groups', payload).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateProductGroup() {
  const qc = useQueryClient()
  return useMutation<ProductGroup, { response?: { data?: { detail?: string } } }, { id: string; name?: string; ipi?: number }>({
    mutationFn: ({ id, ...data }) => api.put<ProductGroup>(`/product-groups/${id}`, data).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteProductGroup() {
  const qc = useQueryClient()
  return useMutation<void, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (id) => api.delete(`/product-groups/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
