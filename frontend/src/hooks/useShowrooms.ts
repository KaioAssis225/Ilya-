import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useLocale } from './useLocale'

export type ShowroomPriceList = 'lojista' | 'arquiteto' | 'corporativo' | 'pvp'

export interface ShowroomProduct {
  id: string
  product_code: string
  description: string
  thumbnail_url: string | null
  unit_price: number | string
}

export interface ShowroomItem extends ShowroomProduct {
  item_id: string
  quantity: number
  line_total: number | string
  optional_choices: ShowroomOptionalChoice[]
}

export interface ShowroomOptionalChoiceInput {
  optional_id?: string
  application_id?: string
  category_code?: string
  /** "Customizado": vale só numa aplicação, sem opcional do cadastro. */
  custom?: boolean
}

export interface ShowroomOptionalChoice {
  application_id: string | null
  application_name: string | null
  application_name_en: string | null
  category_code: string
  category_name: string
  optional_id: string | null
  optional_name: string
  custom?: boolean
  component_name: string | null
  thumbnail_url: string | null
}

export interface ShowroomBox {
  id: string
  name: string
  market_code: 'EU'
  price_list_code: ShowroomPriceList
  currency: 'EUR'
  items: ShowroomItem[]
  item_count: number
  total_quantity: number
  total_value: number | string
  created_at: string
  updated_at: string
}

const KEY = ['showroom-boxes'] as const

export function useShowroomBoxes() {
  const { locale } = useLocale()
  return useQuery<ShowroomBox[]>({
    queryKey: [...KEY, locale],
    queryFn: () => api.get<ShowroomBox[]>('/showroom-boxes', {
      params: { language: locale },
    }).then(response => response.data),
  })
}

export function useShowroomProducts(priceList: ShowroomPriceList | undefined, q: string) {
  const { locale } = useLocale()
  return useQuery<ShowroomProduct[]>({
    queryKey: [...KEY, 'products', priceList, q, locale],
    queryFn: () => api.get<ShowroomProduct[]>('/showroom-boxes/products', {
      params: { price_list_code: priceList, q: q.trim(), limit: 12, language: locale },
    }).then(response => response.data),
    enabled: Boolean(priceList && q.trim()),
    staleTime: 30_000,
  })
}

function useShowroomMutation<TVariables>(request: (variables: TVariables) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}

export function useCreateShowroomBox() {
  const { locale } = useLocale()
  return useShowroomMutation<{ name: string; price_list_code: ShowroomPriceList }>(
    body => api.post('/showroom-boxes', body, { params: { language: locale } }),
  )
}

export function useUpdateShowroomBox() {
  const { locale } = useLocale()
  return useShowroomMutation<{ id: string; name: string; price_list_code: ShowroomPriceList }>(
    ({ id, ...body }) => api.patch(`/showroom-boxes/${id}`, body, { params: { language: locale } }),
  )
}

export function useDeleteShowroomBox() {
  return useShowroomMutation<string>(id => api.delete(`/showroom-boxes/${id}`))
}

export function useAddShowroomItem() {
  const { locale } = useLocale()
  return useShowroomMutation<{ boxId: string; productId: string; quantity?: number; optionalChoices?: ShowroomOptionalChoiceInput[] }>(
    ({ boxId, productId, quantity = 1, optionalChoices = [] }) => api.post(`/showroom-boxes/${boxId}/items`, {
      product_id: productId,
      quantity,
      optional_choices: optionalChoices,
    }, { params: { language: locale } }),
  )
}

export function useUpdateShowroomItem() {
  const { locale } = useLocale()
  return useShowroomMutation<{ boxId: string; itemId: string; quantity: number }>(
    ({ boxId, itemId, quantity }) => api.patch(`/showroom-boxes/${boxId}/items/${itemId}`, { quantity }, { params: { language: locale } }),
  )
}

export function useRemoveShowroomItem() {
  const { locale } = useLocale()
  return useShowroomMutation<{ boxId: string; itemId: string }>(
    ({ boxId, itemId }) => api.delete(`/showroom-boxes/${boxId}/items/${itemId}`, { params: { language: locale } }),
  )
}

export type ShowroomTransferDestination =
  | { type: 'box'; box_id: string }
  | { type: 'order'; order_id: string }
  | { type: 'new_order'; client_id: string }

export interface ShowroomTransfer {
  id: string
  created_at: string
  created_by_name: string
  source_box_id: string | null
  source_box_name: string
  destination_type: 'box' | 'order'
  destination_box_id: string | null
  destination_box_name: string | null
  destination_order_id: string | null
  destination_order_code: string | null
  product_code: string
  quantity: number
  optional_choices: ShowroomOptionalChoice[]
}

export interface ShowroomTransferResult {
  transfer: ShowroomTransfer
  box: ShowroomBox
}

export function useShowroomTransfers(boxId: string | undefined) {
  return useQuery<ShowroomTransfer[]>({
    queryKey: [...KEY, 'transfers', boxId],
    queryFn: () => api.get<ShowroomTransfer[]>(`/showroom-boxes/${boxId}/transfers`).then(response => response.data),
    enabled: Boolean(boxId),
  })
}

export function useTransferShowroomItem() {
  const { locale } = useLocale()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ boxId, itemId, quantity, destination }: {
      boxId: string
      itemId: string
      quantity: number
      destination: ShowroomTransferDestination
    }) => api.post<ShowroomTransferResult>(
      `/showroom-boxes/${boxId}/transfers`,
      { item_id: itemId, quantity, destination },
      { params: { language: locale } },
    ).then(response => response.data),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: KEY }),
      // A peça entrou num orçamento: as listas de orçamentos precisam recarregar.
      queryClient.invalidateQueries({ queryKey: ['orders'] }),
    ]),
  })
}
