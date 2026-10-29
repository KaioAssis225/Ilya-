import type { UserRole } from '../contexts/AuthContext'

export const EU_PVP_MAX_DISCOUNT = 30
export const EU_PVP_ADMIN_MAX_DISCOUNT = 70

export function orderMaxDiscount(
  market: 'BR' | 'EU',
  priceProfile: string,
  role: UserRole | undefined,
  configuredUserLimit: number,
  isClientAccount = false,
): number {
  if (market === 'BR') return configuredUserLimit
  if (priceProfile !== 'pvp' || isClientAccount) return 0
  if (role === 'admin') return EU_PVP_ADMIN_MAX_DISCOUNT
  if (role === 'representante' || role === 'vendedor') return EU_PVP_MAX_DISCOUNT
  return 0
}

export function lineMaxDiscount(orderMax: number, grandfatheredDiscount?: number | null): number {
  return Math.max(orderMax, grandfatheredDiscount ?? 0)
}
