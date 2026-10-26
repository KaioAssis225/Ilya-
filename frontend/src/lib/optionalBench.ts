export const OPTIONAL_BENCH_PREFIX = 'ilya-optional-bench:'
export const OPTIONAL_BENCH_LIMIT = 4

export type BenchAddResult = 'added' | 'duplicate' | 'full'

export function optionalBenchStorageKey(userId: string, market: 'BR' | 'EU') {
  return `${OPTIONAL_BENCH_PREFIX}${userId}:${market}`
}

export function normalizeBenchIds(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const unique: string[] = []
  for (const valueId of value) {
    if (typeof valueId !== 'string' || !valueId || unique.includes(valueId)) continue
    unique.push(valueId)
    if (unique.length === OPTIONAL_BENCH_LIMIT) break
  }
  return unique
}

export function addBenchId(ids: string[], id: string): { ids: string[]; result: BenchAddResult } {
  const normalized = normalizeBenchIds(ids)
  if (normalized.includes(id)) return { ids: normalized, result: 'duplicate' }
  if (normalized.length >= OPTIONAL_BENCH_LIMIT) return { ids: normalized, result: 'full' }
  return { ids: [...normalized, id], result: 'added' }
}

export function replaceBenchId(ids: string[], outgoingId: string, incomingId: string) {
  const normalized = normalizeBenchIds(ids)
  if (normalized.includes(incomingId)) return normalized
  const index = normalized.indexOf(outgoingId)
  if (index < 0) return normalized
  return normalized.map((id, currentIndex) => currentIndex === index ? incomingId : id)
}

export function removeBenchId(ids: string[], id: string) {
  return normalizeBenchIds(ids).filter(current => current !== id)
}

export function moveBenchId(ids: string[], id: string, direction: -1 | 1) {
  const next = normalizeBenchIds(ids)
  const from = next.indexOf(id)
  const to = from + direction
  if (from < 0 || to < 0 || to >= next.length) return next
  ;[next[from], next[to]] = [next[to], next[from]]
  return next
}

export function readOptionalBench(storage: Storage, key: string) {
  try {
    return normalizeBenchIds(JSON.parse(storage.getItem(key) ?? '[]'))
  } catch {
    return []
  }
}

export function writeOptionalBench(storage: Storage, key: string, ids: string[]) {
  try {
    storage.setItem(key, JSON.stringify(normalizeBenchIds(ids)))
  } catch {
    // Storage can be blocked by privacy settings or quota; the in-memory bench remains usable.
  }
}

export function clearOtherOptionalBenchScopes(storage: Storage, activeKey: string) {
  try {
    const stale: string[] = []
    for (let index = 0; index < storage.length; index++) {
      const key = storage.key(index)
      if (key?.startsWith(OPTIONAL_BENCH_PREFIX) && key !== activeKey) stale.push(key)
    }
    stale.forEach(key => storage.removeItem(key))
  } catch {
    // See writeOptionalBench: storage failures must not break the catalogue.
  }
}

export function clearAllOptionalBenches(storage: Storage) {
  try {
    const keys: string[] = []
    for (let index = 0; index < storage.length; index++) {
      const key = storage.key(index)
      if (key?.startsWith(OPTIONAL_BENCH_PREFIX)) keys.push(key)
    }
    keys.forEach(key => storage.removeItem(key))
  } catch {
    // Logout must continue even when storage is unavailable.
  }
}
