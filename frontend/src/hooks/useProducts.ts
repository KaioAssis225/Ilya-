import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { Product, ProductCreate, ProductUpdate } from '../types'

const KEY = 'products'

export function useProducts() {
  return useQuery<Product[]>({
    queryKey: [KEY],
    queryFn: async () => (await api.get('/products', { params: { limit: 200 } })).data,
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
