import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { OptionalColor, OptionalColorCreate, OptionalColorUpdate } from '../types'

const KEY = 'optionals'

export function useOptionals(category?: string) {
  return useQuery<OptionalColor[]>({
    queryKey: category ? [KEY, category] : [KEY],
    queryFn: async () => {
      const params = category ? { category } : {}
      return (await api.get('/optionals', { params })).data
    },
  })
}

export function useOptionalsForCategories(categories: string[], enabled = true) {
  const normalized = Array.from(new Set(categories)).sort()
  return useQuery<OptionalColor[]>({
    queryKey: [KEY, 'categories', normalized],
    queryFn: async () => {
      const batches = Array.from(
        { length: Math.ceil(normalized.length / 50) },
        (_, index) => normalized.slice(index * 50, (index + 1) * 50),
      )
      const responses = await Promise.all(
        batches.map((categoryBatch) =>
          api.get<OptionalColor[]>('/optionals', {
            params: { categories: categoryBatch.join(','), limit: 5000 },
          }),
        ),
      )
      return responses.flatMap((response) => response.data)
    },
    enabled: enabled && normalized.length > 0,
  })
}

export function useCreateOptional() {
  const qc = useQueryClient()
  return useMutation<OptionalColor, Error, OptionalColorCreate>({
    mutationFn: (data) => api.post('/optionals', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdateOptional() {
  const qc = useQueryClient()
  return useMutation<OptionalColor, Error, { id: string; data: OptionalColorUpdate }>({
    mutationFn: ({ id, data }) => api.patch(`/optionals/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useDeleteOptional() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/optionals/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUploadOptionalPhoto() {
  const qc = useQueryClient()
  return useMutation<OptionalColor, Error, { id: string; file: File }>({
    mutationFn: async ({ id, file }) => {
      const fd = new FormData()
      fd.append('file', file)
      return api.post(`/optionals/${id}/upload-photo`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then((r) => r.data)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
