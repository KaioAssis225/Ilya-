import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

export interface DashboardMetrics {
  revenue_total: number
  revenue_finalized: number
  revenue_open: number
  revenue_cancelled: number
  orders_total: number
  orders_finalized: number
  orders_open: number
  orders_cancelled: number
}

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
}

export function useDashboardOverview(filters: DashboardFilters) {
  return useQuery<DashboardOverview>({
    queryKey: ['dashboard-overview', filters],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (filters.start_date) params.start_date = filters.start_date
      if (filters.end_date) params.end_date = filters.end_date
      if (filters.rep_id) params.rep_id = filters.rep_id
      if (filters.region) params.region = filters.region
      const res = await api.get('/dashboard/overview', { params })
      return res.data
    },
  })
}
