import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

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
  return useQuery<ShowroomBox[]>({
    queryKey: KEY,
    queryFn: () => api.get<ShowroomBox[]>('/showroom-boxes').then(response => response.data),
  })
}

export function useShowroomProducts(priceList: ShowroomPriceList | undefined, q: string) {
  return useQuery<ShowroomProduct[]>({
    queryKey: [...KEY, 'products', priceList, q],
    queryFn: () => api.get<ShowroomProduct[]>('/showroom-boxes/products', {
      params: { price_list_code: priceList, q: q.trim(), limit: 30 },
    }).then(response => response.data),
    enabled: Boolean(priceList),
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
  return useShowroomMutation<{ name: string; price_list_code: ShowroomPriceList }>(
    body => api.post('/showroom-boxes', body),
  )
}

export function useUpdateShowroomBox() {
  return useShowroomMutation<{ id: string; name: string; price_list_code: ShowroomPriceList }>(
    ({ id, ...body }) => api.patch(`/showroom-boxes/${id}`, body),
  )
}

export function useDeleteShowroomBox() {
  return useShowroomMutation<string>(id => api.delete(`/showroom-boxes/${id}`))
}

export function useAddShowroomItem() {
  return useShowroomMutation<{ boxId: string; productId: string; quantity?: number }>(
    ({ boxId, productId, quantity = 1 }) => api.post(`/showroom-boxes/${boxId}/items`, {
      product_id: productId,
      quantity,
    }),
  )
}

export function useUpdateShowroomItem() {
  return useShowroomMutation<{ boxId: string; itemId: string; quantity: number }>(
    ({ boxId, itemId, quantity }) => api.patch(`/showroom-boxes/${boxId}/items/${itemId}`, { quantity }),
  )
}

export function useRemoveShowroomItem() {
  return useShowroomMutation<{ boxId: string; itemId: string }>(
    ({ boxId, itemId }) => api.delete(`/showroom-boxes/${boxId}/items/${itemId}`),
  )
}
