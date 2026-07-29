import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface AppNotification {
  id: string
  message: string
  is_read: boolean
  created_at: string
}

const KEY = ['notifications']

export function useNotifications(enabled = true) {
  return useQuery<AppNotification[]>({
    queryKey: KEY,
    queryFn: () => api.get<AppNotification[]>('/notifications').then(r => r.data),
    refetchInterval: 30_000,
    enabled,
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.patch(`/notifications/${id}/read`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
