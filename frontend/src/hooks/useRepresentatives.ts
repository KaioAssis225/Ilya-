import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { Representative, RepresentativeCreate, RepresentativeUpdate } from '../types'

const KEY = 'representatives'

export function useRepresentatives() {
  return useQuery<Representative[]>({
    queryKey: [KEY],
    queryFn: async () => (await api.get('/representatives')).data,
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
