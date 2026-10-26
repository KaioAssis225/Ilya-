import { describe, expect, it } from 'vitest'
import {
  addBenchId,
  clearOtherOptionalBenchScopes,
  moveBenchId,
  optionalBenchStorageKey,
  readOptionalBench,
  removeBenchId,
  replaceBenchId,
  writeOptionalBench,
} from './optionalBench'

describe('optionalBench', () => {
  it('limita a quatro IDs e não duplica', () => {
    expect(addBenchId(['a'], 'a')).toEqual({ ids: ['a'], result: 'duplicate' })
    expect(addBenchId(['a', 'b', 'c', 'd'], 'e')).toEqual({ ids: ['a', 'b', 'c', 'd'], result: 'full' })
  })

  it('substitui explicitamente sem alterar a posição escolhida', () => {
    expect(replaceBenchId(['a', 'b', 'c', 'd'], 'b', 'e')).toEqual(['a', 'e', 'c', 'd'])
    expect(replaceBenchId(['a', 'b'], 'a', 'b')).toEqual(['a', 'b'])
  })

  it('remove e move preservando a ordem', () => {
    expect(removeBenchId(['a', 'b', 'c'], 'b')).toEqual(['a', 'c'])
    expect(moveBenchId(['a', 'b', 'c'], 'b', -1)).toEqual(['b', 'a', 'c'])
    expect(moveBenchId(['a', 'b', 'c'], 'c', 1)).toEqual(['a', 'b', 'c'])
  })

  it('persiste só IDs e limpa bancadas de outros escopos', () => {
    const active = optionalBenchStorageKey('u1', 'BR')
    const staleMarket = optionalBenchStorageKey('u1', 'EU')
    const staleUser = optionalBenchStorageKey('u2', 'BR')
    writeOptionalBench(sessionStorage, active, ['a', 'a', 'b'])
    sessionStorage.setItem(staleMarket, '["c"]')
    sessionStorage.setItem(staleUser, '["d"]')
    sessionStorage.setItem('unrelated', 'kept')

    clearOtherOptionalBenchScopes(sessionStorage, active)

    expect(readOptionalBench(sessionStorage, active)).toEqual(['a', 'b'])
    expect(sessionStorage.getItem(staleMarket)).toBeNull()
    expect(sessionStorage.getItem(staleUser)).toBeNull()
    expect(sessionStorage.getItem('unrelated')).toBe('kept')
  })
})
