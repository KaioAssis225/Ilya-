import type { UserRole } from '../contexts/AuthContext'

const EU_PRICE_PROFILE_DISCOUNTS: Record<string, number> = {
  lojista: 50,
  arquiteto: 35,
  corporativo: 25,
  pvp: 10,
}

export function orderMaxDiscount(
  market: 'BR' | 'EU',
  priceProfile: string,
  role: UserRole | undefined,
  configuredUserLimit: number,
): number {
  if (market === 'BR') return configuredUserLimit
  if (priceProfile === 'pvp' && role !== 'admin') return 0
  return EU_PRICE_PROFILE_DISCOUNTS[priceProfile] ?? 0
}
