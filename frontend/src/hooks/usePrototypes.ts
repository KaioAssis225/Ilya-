import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import type { OptionalApplicationInput, PageResult, Product } from '../types'
import { useAuth } from './useAuth'
import { useLocale } from './useLocale'

/** Prefixo da API da área de protótipos (EU, só para quem tem a permissão). */
export const PROTOTYPES_PATH = '/prototypes'

const KEY = 'prototypes'
/** Os protótipos também alimentam o catálogo/orçamento: invalida os dois. */
const PRODUCTS_KEY = 'products'

export interface PrototypePageParams {
  skip?: number
  limit?: number
  q?: string
  sort_dir?: 'asc' | 'desc'
  language?: 'pt-PT' | 'en-GB'
}

export interface PrototypeInput {
  description_pt_pt: string
  description_en: string
  summary?: string | null
  type: string
  catalog_id: string
  is_circular: boolean
  altura: number
  largura: number
  profundidade: number
  price_lojista: number
  price_corporativo: number
  price_pvp: number
  price_arquiteto: number
  vat_rate: number
  observacao?: string | null
  optional_applications?: OptionalApplicationInput[]
}

export interface PrototypeOptionalGroup {
  id: string
  code: string
  name: string
  options: Array<{ id: string; name: string }>
}

export interface PrototypeGroupInput {
  name: string
  options: Array<{ id?: string; name: string }>
}

export function prototypesPageQueryOptions(params: PrototypePageParams) {
  return queryOptions<PageResult<Product>>({
    queryKey: [KEY, 'page', params],
    queryFn: async () => {
      const response = await api.get<Product[]>(PROTOTYPES_PATH, { params })
      return {
        items: response.data,
        total: Number(response.headers['x-total-count'] ?? response.data.length),
        hasMore: String(response.headers['x-has-more'] ?? 'false') === 'true',
        pageSize: Number(response.headers['x-page-size'] ?? response.data.length),
      }
    },
    staleTime: 15_000,
  })
}

export function usePrototypesPage(params: PrototypePageParams, enabled = true) {
  const { locale } = useLocale()
  const { user } = useAuth()
  return useQuery({
    ...prototypesPageQueryOptions({ ...params, language: locale }),
    enabled: enabled && Boolean(user?.can_manage_prototypes),
  })
}

function useInvalidate() {
  const qc = useQueryClient()
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: [KEY] }),
    qc.invalidateQueries({ queryKey: [PRODUCTS_KEY] }),
  ])
}

export function useCreatePrototype() {
  const invalidate = useInvalidate()
  return useMutation<Product, Error, PrototypeInput>({
    mutationFn: (data) => api.post<Product>(PROTOTYPES_PATH, data).then((r) => r.data),
    onSuccess: invalidate,
  })
}

export function useUpdatePrototype() {
  const invalidate = useInvalidate()
  return useMutation<Product, Error, { id: string; data: Partial<PrototypeInput> }>({
    mutationFn: ({ id, data }) => api.patch<Product>(`${PROTOTYPES_PATH}/${id}`, data).then((r) => r.data),
    onSuccess: invalidate,
  })
}

export function useDeletePrototype() {
  const invalidate = useInvalidate()
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.delete(`${PROTOTYPES_PATH}/${id}`).then(() => undefined),
    onSuccess: invalidate,
  })
}

/** Grupos de opcionais que existem só dentro de um protótipo. */
export function usePrototypeOptionalGroups(prototypeId: string | undefined) {
  return useQuery<PrototypeOptionalGroup[]>({
    queryKey: [KEY, 'groups', prototypeId],
    queryFn: () =>
      api.get<PrototypeOptionalGroup[]>(`${PROTOTYPES_PATH}/${prototypeId}/optional-groups`).then((r) => r.data),
    enabled: Boolean(prototypeId),
  })
}

export function useSavePrototypeOptionalGroup() {
  const invalidate = useInvalidate()
  return useMutation<PrototypeOptionalGroup, Error, { prototypeId: string; groupId?: string; data: PrototypeGroupInput }>({
    mutationFn: ({ prototypeId, groupId, data }) =>
      (groupId
        ? api.put<PrototypeOptionalGroup>(`${PROTOTYPES_PATH}/${prototypeId}/optional-groups/${groupId}`, data)
        : api.post<PrototypeOptionalGroup>(`${PROTOTYPES_PATH}/${prototypeId}/optional-groups`, data)
      ).then((r) => r.data),
    onSuccess: invalidate,
  })
}

export function useDeletePrototypeOptionalGroup() {
  const invalidate = useInvalidate()
  return useMutation<void, Error, { prototypeId: string; groupId: string }>({
    mutationFn: ({ prototypeId, groupId }) =>
      api.delete(`${PROTOTYPES_PATH}/${prototypeId}/optional-groups/${groupId}`).then(() => undefined),
    onSuccess: invalidate,
  })
}
