import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { PageResult, Product, ProductCreate, ProductUpdate } from '../types'

const KEY = 'products'

export interface ProductPageParams {
  skip?: number
  limit?: number
  q?: string
  type?: string
  group_id?: string
  include_total?: boolean
  sort_by?: 'product_code' | 'description' | 'type' | 'price_lojista' | 'price_corporativo'
  sort_dir?: 'asc' | 'desc'
}

export function useProductsPage(params: ProductPageParams, enabled = true) {
  return useQuery<PageResult<Product>>({
    queryKey: [KEY, 'page', params],
    queryFn: async () => {
      const response = await api.get<Product[]>('/products', { params })
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

export function useProductsByCodes(productCodes: string[], enabled = true) {
  const codes = Array.from(new Set(productCodes)).sort()
  return useQuery<Product[]>({
    queryKey: [KEY, 'batch', codes],
    queryFn: async () => {
      const batches = Array.from(
        { length: Math.ceil(codes.length / 100) },
        (_, index) => codes.slice(index * 100, (index + 1) * 100),
      )
      const responses = await Promise.all(
        batches.map((productCodesBatch) =>
          api.post<Product[]>('/products/batch', {
            product_codes: productCodesBatch,
          }),
        ),
      )
      return responses.flatMap((response) => response.data)
    },
    enabled: enabled && codes.length > 0,
  })
}

export function useCreateProduct() {
  const qc = useQueryClient()
  return useMutation<Product, Error, ProductCreate>({
    mutationFn: (data) => api.post('/products', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdateProduct() {
  const qc = useQueryClient()
  return useMutation<Product, Error, { id: string; data: ProductUpdate }>({
    mutationFn: ({ id, data }) => api.patch(`/products/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useDeleteProduct() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/products/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUploadProductPhoto() {
  const qc = useQueryClient()
  return useMutation<Product, Error, { id: string; file: File }>({
    mutationFn: ({ id, file }) => {
      const form = new FormData()
      form.append('file', file)
      return api
        .post(`/products/${id}/upload-photo`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
