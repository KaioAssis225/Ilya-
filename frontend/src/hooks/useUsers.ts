import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface UserRead {
  id: string
  email: string
  full_name: string
  role: 'admin' | 'vendedor' | 'representante'
  rep_id: string | null
  is_active: boolean
}

export interface UserCreate {
  email: string
  password: string
  full_name: string
  role: 'admin' | 'vendedor' | 'representante'
  rep_id?: string | null
}

export interface UserUpdate {
  email?: string
  full_name?: string
  role?: 'admin' | 'vendedor' | 'representante'
  rep_id?: string | null
  is_active?: boolean
}

export function useUsers() {
  return useQuery<UserRead[]>({
    queryKey: ['users'],
    queryFn: async () => {
      const res = await api.get('/users')
      return res.data
    },
  })
}

export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: UserCreate) => api.post('/users', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: UserUpdate & { id: string }) =>
      api.patch(`/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useResetUserPassword() {
  return useMutation({
    mutationFn: ({ id, new_password }: { id: string; new_password: string }) =>
      api.post(`/users/${id}/reset-password`, { new_password }),
  })
}

export function useDeleteUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useCreateUserFromClient() {
  const qc = useQueryClient()
  return useMutation<UserRead, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (clientId: string) =>
      api.post<UserRead>(`/users/from-client/${clientId}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useCreateUserFromRep() {
  const qc = useQueryClient()
  return useMutation<UserRead, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (repId: string) =>
      api.post<UserRead>(`/users/from-rep/${repId}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}
