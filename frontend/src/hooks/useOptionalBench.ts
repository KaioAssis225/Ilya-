import { useCallback, useEffect, useMemo, useState } from 'react'
import type { OptionalColor } from '../types'
import { hasOptionalPhoto } from '../lib/optionalMedia'
import {
  addBenchId,
  clearOtherOptionalBenchScopes,
  moveBenchId,
  optionalBenchStorageKey,
  readOptionalBench,
  removeBenchId,
  replaceBenchId,
  writeOptionalBench,
  type BenchAddResult,
} from '../lib/optionalBench'

export function useOptionalBench(
  userId: string,
  market: 'BR' | 'EU',
  optionals: OptionalColor[] | undefined,
) {
  const storageKey = optionalBenchStorageKey(userId, market)
  const [storedIds, setStoredIds] = useState<string[]>(() => readOptionalBench(sessionStorage, storageKey))

  useEffect(() => {
    clearOtherOptionalBenchScopes(sessionStorage, storageKey)
  }, [storageKey])

  const availableIds = useMemo(() => optionals
    ? new Set(optionals.filter(hasOptionalPhoto).map(optional => optional.id))
    : null, [optionals])
  const ids = useMemo(
    () => availableIds ? storedIds.filter(id => availableIds.has(id)) : storedIds,
    [availableIds, storedIds],
  )

  useEffect(() => {
    writeOptionalBench(sessionStorage, storageKey, ids)
  }, [ids, storageKey])

  const items = useMemo(() => {
    if (!optionals) return []
    const byId = new Map(optionals.map(optional => [optional.id, optional]))
    return ids.flatMap(id => {
      const optional = byId.get(id)
      return optional && hasOptionalPhoto(optional) ? [optional] : []
    })
  }, [ids, optionals])

  const add = useCallback((id: string): BenchAddResult => {
    const next = addBenchId(ids, id)
    setStoredIds(next.ids)
    return next.result
  }, [ids])

  const replace = useCallback((outgoingId: string, incomingId: string) => {
    setStoredIds(replaceBenchId(ids, outgoingId, incomingId))
  }, [ids])

  const remove = useCallback((id: string) => setStoredIds(removeBenchId(ids, id)), [ids])
  const move = useCallback((id: string, direction: -1 | 1) => setStoredIds(moveBenchId(ids, id, direction)), [ids])
  const clear = useCallback(() => setStoredIds([]), [])

  return { ids, items, add, replace, remove, move, clear }
}
