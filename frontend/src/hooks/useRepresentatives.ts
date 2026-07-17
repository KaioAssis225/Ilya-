import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { PageResult, Representative, RepresentativeCreate, RepresentativeUpdate } from '../types'

const KEY = 'representatives'

export interface RepresentativePageParams {
  skip?: number
  limit?: number
  q?: string
  include_total?: boolean
  sort_by?: 'name' | 'email' | 'phone' | 'city' | 'state' | 'max_discount'
  sort_dir?: 'asc' | 'desc'
}

export function useRepresentativesPage(
  params: RepresentativePageParams,
  enabled = true,
) {
  return useQuery<PageResult<Representative>>({
    queryKey: [KEY, 'page', params],
    queryFn: async () => {
      const response = await api.get<Representative[]>(
        '/representatives',
        { params },
      )
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

export function useRepresentative(id: string, enabled = true) {
  return useQuery<Representative>({
    queryKey: [KEY, id],
    queryFn: async () => (await api.get(`/representatives/${id}`)).data,
    enabled: enabled && !!id,
  })
}

export function useCreateRepresentative() {
  const qc = useQueryClient()
  return useMutation<Representative, Error, RepresentativeCreate>({
    mutationFn: (data) => api.post('/representatives', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdateRepresentative() {
  const qc = useQueryClient()
  return useMutation<Representative, Error, { id: string; data: RepresentativeUpdate }>({
    mutationFn: ({ id, data }) => api.patch(`/representatives/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useDeleteRepresentative() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`/representatives/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  })
}
