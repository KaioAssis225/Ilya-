import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface ProductGroup {
  id: string
  name: string
  ipi: number
}

export interface ProductType {
  id: string
  name: string
  group_id: string | null
  group: ProductGroup | null
}

const KEY = ['product-types']

export function useProductTypes() {
  return useQuery<ProductType[]>({
    queryKey: KEY,
    queryFn: () => api.get<ProductType[]>('/product-types').then(r => r.data),
  })
}

export function useCreateProductType() {
  const qc = useQueryClient()
  return useMutation<ProductType, { response?: { data?: { detail?: string } } }, { name: string; group_id?: string | null }>({
    mutationFn: (payload) => api.post<ProductType>('/product-types', payload).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateProductType() {
  const qc = useQueryClient()
  return useMutation<ProductType, { response?: { data?: { detail?: string } } }, { id: string; name: string; group_id?: string | null }>({
    mutationFn: ({ id, name, group_id }) => api.put<ProductType>(`/product-types/${id}`, { name, group_id }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteProductType() {
  const qc = useQueryClient()
  return useMutation<void, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (id) => api.delete(`/product-types/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
