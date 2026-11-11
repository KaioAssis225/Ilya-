import type { UserRole } from '../contexts/AuthContext'

export function orderMaxDiscount(
  market: 'BR' | 'EU',
  priceProfile: string,
  role: UserRole | undefined,
  configuredUserLimit: number,
  isClientAccount = false,
): number {
  if (market === 'BR') return configuredUserLimit
  if (priceProfile !== 'pvp' || isClientAccount) return 0
  // Só o cadastro do representante limita (0–100); o servidor decide.
  // Admin sem representante vinculado: o chamador passa 100.
  if (role === 'admin' || role === 'representante' || role === 'vendedor') {
    return Math.min(100, Math.max(0, configuredUserLimit))
  }
  return 0
}

export function lineMaxDiscount(orderMax: number, grandfatheredDiscount?: number | null): number {
  return Math.max(orderMax, grandfatheredDiscount ?? 0)
}
