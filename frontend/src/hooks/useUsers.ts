import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { PageResult } from '../types'

export interface UserRead {
  id: string
  email: string
  username: string | null
  full_name: string
  role: 'admin' | 'vendedor' | 'representante' | 'cadastros' | 'produtos' | 'cliente' | 'executivo'
  rep_id: string | null
  is_active: boolean
  can_view_dashboard: boolean
}

export interface UserCreate {
  email: string
  password: string
  full_name: string
  role: 'admin' | 'vendedor' | 'representante' | 'cadastros' | 'produtos' | 'cliente' | 'executivo'
  rep_id?: string | null
}

export interface UserUpdate {
  email?: string
  full_name?: string
  role?: 'admin' | 'vendedor' | 'representante' | 'cadastros' | 'produtos' | 'cliente' | 'executivo'
  rep_id?: string | null
  is_active?: boolean
  can_view_dashboard?: boolean
}

export interface UserPageParams {
  skip?: number
  limit?: number
  q?: string
  include_total?: boolean
  sort_by?: 'full_name' | 'email' | 'role' | 'is_active'
  sort_dir?: 'asc' | 'desc'
}

export function useUsersPage(params: UserPageParams, enabled = true) {
  return useQuery<PageResult<UserRead>>({
    queryKey: ['users', 'page', params],
    queryFn: async () => {
      const response = await api.get<UserRead[]>('/users', { params })
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

export interface UserCreateResponse {
  id: string
  email: string
  username: string
  full_name: string
  role: string
  temp_password: string
}

export function useCreateUserFromClient() {
  const qc = useQueryClient()
  return useMutation<UserCreateResponse, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (clientId: string) =>
      api.post<UserCreateResponse>(`/users/from-client/${clientId}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useCreateUserFromRep() {
  const qc = useQueryClient()
  return useMutation<UserCreateResponse, { response?: { data?: { detail?: string } } }, string>({
    mutationFn: (repId: string) =>
      api.post<UserCreateResponse>(`/users/from-rep/${repId}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}
