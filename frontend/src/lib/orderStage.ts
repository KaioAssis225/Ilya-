import type { OrderStage } from '../types'

export function resolveOrderStage(order: {
  is_finalized: boolean
  is_cancelled: boolean
  order_stage?: OrderStage | null
}): OrderStage | null {
  if (!order.is_finalized || order.is_cancelled) return null
  return order.order_stage ?? 'production'
}

export function stageLabel(stage: OrderStage, english: boolean): string {
  if (english) {
    return stage === 'production' ? 'In production' : 'Delivered'
  }
  return stage === 'production' ? 'Produção' : 'Entregue'
}

export function describeStageChange(
  details: string | null | undefined,
  english: boolean,
): string | null {
  if (!details) return null
  const match = details.match(/^production -> delivered$|^delivered -> production$/)
  if (!match) return null
  const [from, to] = details.split(' -> ') as [OrderStage, OrderStage]
  return `${stageLabel(from, english)} → ${stageLabel(to, english)}`
}

export const STAGE_BADGE_CLASS: Record<OrderStage, string> = {
  production: 'bg-info-soft text-info',
  delivered: 'bg-success-soft text-success',
}
