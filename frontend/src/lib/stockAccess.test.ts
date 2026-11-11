import { describe, expect, it } from 'vitest'
import { canGrantStockAccess } from './stockAccess'

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
