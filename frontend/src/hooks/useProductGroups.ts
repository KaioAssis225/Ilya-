import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface ProductGroup {
  id: string
  name: string
  ipi: number
  market_code?: 'BR' | 'EU'
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

// IVA aprovado dos produtos de cada grupo (Portugal) — só exibição; o IVA é
// aprovado por produto. A chave fica sob 'product-types' porque mover um
// subgrupo (useUpdateProductType) muda o resumo e já invalida esse prefixo.
export interface ProductGroupVatSummary {
  group_id: string
  approved_rates: (string | number)[]
  approved_products: number
  pending_products: number
}

export function useProductGroupVatSummary(enabled: boolean) {
  return useQuery<ProductGroupVatSummary[]>({
    queryKey: ['product-types', 'group-vat-summary'],
    queryFn: () => api.get<ProductGroupVatSummary[]>('/product-groups/vat-summary').then(r => r.data),
    enabled,
  })
}
