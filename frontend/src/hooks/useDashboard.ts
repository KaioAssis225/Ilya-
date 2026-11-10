import { keepPreviousData, useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from './useAuth'

export interface DashboardMetrics {
  revenue_total: number
  revenue_finalized: number
  revenue_open: number
  revenue_cancelled: number
  orders_total: number
  orders_finalized: number
  orders_open: number
  orders_cancelled: number
  // Etapas dos pedidos confirmados (aba "Pedidos"); 0 na aba de orçamentos.
  revenue_production: number
  revenue_delivered: number
  orders_production: number
  orders_delivered: number
}

/** Aba do dashboard: orçamentos (não confirmados) ou pedidos (confirmados). */
export type DashboardKind = 'quotes' | 'orders'

// Região não é um campo próprio do cliente — é derivada do UF (client.state)
// pelo backend (app/core/regions.py), então o filtro aqui é só uma lista fixa.
export const DASHBOARD_REGIONS = ['Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul'] as const

export interface DashboardChartPoint {
  key: string
  revenue: number
  orders: number
}

export interface DashboardRepRanking {
  name: string
  orders: number
  revenue: number
}

export interface DashboardProductRanking {
  product_code: string
  description: string
  quantity: number
  revenue: number
}

export interface DashboardOverview {
  kind: DashboardKind | null
  start_date: string
  end_date: string
  granularity: 'day' | 'week' | 'month'
  metrics: DashboardMetrics
  chart: DashboardChartPoint[]
  representatives: DashboardRepRanking[]
  products: DashboardProductRanking[]
}

export interface DashboardFilters {
  start_date?: string
  end_date?: string
  rep_id?: string
  region?: string
  kind?: DashboardKind
}

export function useDashboardOverview(filters: DashboardFilters, enabled = true) {
  return useQuery<DashboardOverview>({
    queryKey: ['dashboard-overview', filters],
    enabled,
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (filters.kind) params.kind = filters.kind
      if (filters.start_date) params.start_date = filters.start_date
      if (filters.end_date) params.end_date = filters.end_date
      if (filters.rep_id) params.rep_id = filters.rep_id
      if (filters.region) params.region = filters.region
      const res = await api.get('/dashboard/overview', { params })
      return res.data
    },
  })
}

export type ClientContactFilter = 'all' | 'yes' | 'no'

export interface ClientContactRow {
  id: string
  name: string
  contact_name: string | null
  phone: string
  email: string | null
  city: string
  country: string
  rep_id: string | null
  rep_name: string | null
  contacted: boolean
}

export interface ClientsDashboard {
  total: number
  contacted: number
  not_contacted: number
  contacted_pct: number
  filtered_total: number
  items: ClientContactRow[]
}

export interface ClientsDashboardParams {
  contacted: ClientContactFilter
  q?: string
  skip?: number
  limit?: number
}

/** Contadores e lista vêm do servidor, já limitados à carteira do usuário. */
export function useClientsDashboard(params: ClientsDashboardParams, enabled = true) {
  const { user } = useAuth()
  return useQuery<ClientsDashboard>({
    queryKey: ['dashboard-clients', user?.id, user?.active_market, params],
    queryFn: async () => {
      const query: Record<string, string | number> = { contacted: params.contacted }
      if (params.q) query.q = params.q
      if (params.skip) query.skip = params.skip
      if (params.limit) query.limit = params.limit
      return (await api.get('/dashboard/clients', { params: query })).data
    },
    enabled,
    placeholderData: keepPreviousData,
  })
}
