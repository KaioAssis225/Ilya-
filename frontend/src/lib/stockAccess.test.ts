import { describe, expect, it } from 'vitest'
import { canGrantStockAccess, canGrantStockAccessToAccesses } from './stockAccess'

describe('canGrantStockAccess', () => {
  it('só com Brasil entre os mercados', () => {
    expect(canGrantStockAccess(['BR'], 'vendedor')).toBe(true)
    expect(canGrantStockAccess(['BR', 'EU'], 'admin')).toBe(true)
    expect(canGrantStockAccess(['EU'], 'vendedor')).toBe(false)
    expect(canGrantStockAccess([], 'vendedor')).toBe(false)
    expect(canGrantStockAccess(undefined, 'vendedor')).toBe(false)
  })

  it('nunca para cliente nem identidade técnica', () => {
    expect(canGrantStockAccess(['BR'], 'cliente')).toBe(false)
    expect(canGrantStockAccess(['BR'], 'benchmark_readonly')).toBe(false)
  })
})

describe('canGrantStockAccessToAccesses', () => {
  const br = { market_code: 'BR' as const, role: 'vendedor', status: 'active' }
  const eu = { market_code: 'EU' as const, role: 'vendedor', status: 'active' }

  it('exige vínculo BR ativo', () => {
    expect(canGrantStockAccessToAccesses([br])).toBe(true)
    expect(canGrantStockAccessToAccesses([br, eu])).toBe(true)
    expect(canGrantStockAccessToAccesses([eu])).toBe(false)
    expect(canGrantStockAccessToAccesses([{ ...br, status: 'pending' }])).toBe(false)
    expect(canGrantStockAccessToAccesses([{ ...br, status: 'suspended' }])).toBe(false)
    expect(canGrantStockAccessToAccesses([])).toBe(false)
    expect(canGrantStockAccessToAccesses(undefined)).toBe(false)
  })

  it('papel bloqueado em qualquer vínculo derruba a elegibilidade', () => {
    expect(canGrantStockAccessToAccesses([{ ...br, role: 'cliente' }])).toBe(false)
    expect(canGrantStockAccessToAccesses([br, { ...eu, role: 'benchmark_readonly' }])).toBe(false)
  })
})
