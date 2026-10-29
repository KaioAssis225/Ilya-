// Pasta de destino dos PDFs de orçamento.
//
// O navegador só grava numa pasta escolhida pelo usuário através da File System
// Access API (Chrome/Edge no computador). O handle da pasta não serializa em
// localStorage, então fica em IndexedDB, por navegador e por usuário logado.
// Em qualquer outro caso (sem pasta, sem API, sem permissão, falha ao gravar)
// o PDF cai em Downloads, como sempre foi.

// Tipos mínimos: o lib.dom do TS não traz showDirectoryPicker nem as permissões.
export interface PdfWritable {
  write(data: Blob): Promise<void>
  close(): Promise<void>
  abort?(): Promise<void>
}
export interface PdfFileHandle {
  createWritable(): Promise<PdfWritable>
}
export type FsPermissionState = 'granted' | 'denied' | 'prompt'
export interface PdfDirectoryHandle {
  readonly name: string
  getFileHandle(name: string, options?: { create?: boolean }): Promise<PdfFileHandle>
  queryPermission?(descriptor: { mode: 'readwrite' }): Promise<FsPermissionState>
  requestPermission?(descriptor: { mode: 'readwrite' }): Promise<FsPermissionState>
}

// O que o jsPDF precisa expor.
export interface PdfDocumentLike {
  save(filename: string): unknown
  output(type: 'blob'): Blob
}

export type PdfFallbackReason = 'permission-denied' | 'write-failed'

// Destino resolvido no clique: requestPermission exige gesto recente do usuário,
// por isso resolvemos antes dos fetches que montam o PDF.
export interface PdfDestination {
  /** null = Downloads. */
  handle: PdfDirectoryHandle | null
  /** Nome da pasta escolhida, mesmo quando caiu em Downloads. */
  folderName: string | null
  /** Por que a pasta não será usada (só quando havia uma pasta escolhida). */
  fallbackReason: PdfFallbackReason | null
}

export type PdfSaveResult =
  | { kind: 'folder'; folderName: string; filename: string }
  // reason null = nenhuma pasta escolhida: download normal, sem aviso.
  | { kind: 'downloads'; folderName: string | null; reason: PdfFallbackReason | null }

export interface DestinationStore {
  get(key: string): Promise<PdfDirectoryHandle | null>
  set(key: string, handle: PdfDirectoryHandle): Promise<boolean>
  delete(key: string): Promise<boolean>
}

type DirectoryPicker = (options: { mode: 'readwrite'; id: string }) => Promise<PdfDirectoryHandle>

export interface PdfDestinationDeps {
  store?: DestinationStore
  /** Ausente quando o navegador não tem a File System Access API. */
  picker?: DirectoryPicker
}

export type PickResult =
  | { status: 'chosen'; folderName: string }
  | { status: 'cancelled' }
  | { status: 'unsupported' }
  | { status: 'error' }

const DB_NAME = 'ilya-preferences'
const DB_VERSION = 1
const STORE_NAME = 'pdf-destination'
const PICKER_ID = 'ilya-orcamentos'

function promisifyRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'))
  })
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Failed to open IndexedDB'))
    request.onblocked = () => reject(new Error('IndexedDB blocked'))
  })
}

// Abre, executa e fecha. Qualquer falha (IndexedDB ausente, modo privado,
// bloqueado) devolve null: sem armazenamento = sem pasta lembrada.
async function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<{ value: T } | null> {
  try {
    const db = await openDb()
    try {
      return { value: await promisifyRequest(run(db.transaction(STORE_NAME, mode).objectStore(STORE_NAME))) }
    } finally {
      db.close()
    }
  } catch {
    return null
  }
}

export function createIndexedDbStore(): DestinationStore {
  return {
    async get(key) {
      const outcome = await withStore<PdfDirectoryHandle | undefined>('readonly', store => store.get(key))
      return outcome?.value ?? null
    },
    async set(key, handle) {
      return (await withStore('readwrite', store => store.put(handle, key))) !== null
    },
    async delete(key) {
      return (await withStore('readwrite', store => store.delete(key))) !== null
    },
  }
}

export function isFolderPickerSupported(
  env: { showDirectoryPicker?: unknown } = typeof window === 'undefined' ? {} : (window as unknown as { showDirectoryPicker?: unknown }),
): boolean {
  return typeof env.showDirectoryPicker === 'function'
}

function defaultPicker(): DirectoryPicker | undefined {
  if (typeof window === 'undefined' || !isFolderPickerSupported()) return undefined
  const win = window as unknown as { showDirectoryPicker: DirectoryPicker }
  // bind: chamada solta de showDirectoryPicker lança "Illegal invocation".
  return win.showDirectoryPicker.bind(window)
}

function isAbortError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { name?: unknown }).name === 'AbortError'
}

export async function pickDestinationFolder(userKey: string, deps: PdfDestinationDeps = {}): Promise<PickResult> {
  const picker = deps.picker ?? defaultPicker()
  if (!picker) return { status: 'unsupported' }
  const store = deps.store ?? createIndexedDbStore()
  try {
    const handle = await picker({ mode: 'readwrite', id: PICKER_ID })
    // Sem gravar, a escolha se perderia ao recarregar: melhor avisar que falhou.
    if (!(await store.set(userKey, handle))) return { status: 'error' }
    return { status: 'chosen', folderName: handle.name }
  } catch (error) {
    return { status: isAbortError(error) ? 'cancelled' : 'error' }
  }
}

export async function clearDestinationFolder(userKey: string, deps: PdfDestinationDeps = {}): Promise<boolean> {
  try {
    return await (deps.store ?? createIndexedDbStore()).delete(userKey)
  } catch {
    return false
  }
}

async function loadHandle(userKey: string, deps: PdfDestinationDeps): Promise<PdfDirectoryHandle | null> {
  try {
    return await (deps.store ?? createIndexedDbStore()).get(userKey)
  } catch {
    return null
  }
}

export async function loadDestinationFolderName(userKey: string, deps: PdfDestinationDeps = {}): Promise<string | null> {
  return (await loadHandle(userKey, deps))?.name ?? null
}

/**
 * Resolve para onde o PDF vai. Chamar no início do clique, antes de qualquer
 * fetch: requestPermission só funciona com gesto recente do usuário.
 */
export async function resolvePdfDestination(userKey: string, deps: PdfDestinationDeps = {}): Promise<PdfDestination> {
  const handle = await loadHandle(userKey, deps)
  if (!handle) return { handle: null, folderName: null, fallbackReason: null }

  try {
    // Handle sem métodos de permissão: tenta gravar e deixa savePdf cair em Downloads se falhar.
    let state: FsPermissionState = (await handle.queryPermission?.({ mode: 'readwrite' })) ?? 'granted'
    if (state !== 'granted') state = (await handle.requestPermission?.({ mode: 'readwrite' })) ?? 'denied'
    if (state === 'granted') return { handle, folderName: handle.name, fallbackReason: null }
  } catch {
    // Sem gesto do usuário (ou handle inválido): trata como permissão negada.
  }
  return { handle: null, folderName: handle.name, fallbackReason: 'permission-denied' }
}

export interface PdfSaveNotice {
  tone: 'success' | 'warning'
  text: string
}

/** Aviso para o usuário. Download comum sem pasta escolhida não precisa de aviso. */
export function describePdfSave(result: PdfSaveResult, isEnglish: boolean): PdfSaveNotice | null {
  if (result.kind === 'folder') {
    const text = isEnglish
      ? `Saved to ${result.folderName}/${result.filename}`
      : `Salvo em ${result.folderName}/${result.filename}`
    return { tone: 'success', text }
  }
  if (!result.reason) return null
  const folder = result.folderName ?? ''
  const text = result.reason === 'permission-denied'
    ? (isEnglish
        ? `No access to folder "${folder}". The PDF was saved to Downloads.`
        : `Sem acesso à pasta "${folder}". O PDF foi salvo em Downloads.`)
    : (isEnglish
        ? `Could not write to folder "${folder}". The PDF was saved to Downloads.`
        : `Não foi possível gravar na pasta "${folder}". O PDF foi salvo em Downloads.`)
  return { tone: 'warning', text }
}

// getFileHandle lança TypeError para nomes com separadores ou caracteres reservados.
export function safeFileName(name: string): string {
  return Array.from(name, ch => (ch.charCodeAt(0) < 32 || '\\/:*?"<>|'.includes(ch) ? '_' : ch)).join('')
}

/**
 * Grava o PDF na pasta escolhida; em qualquer outro caso, em Downloads.
 * Um arquivo existente com o mesmo nome é sobrescrito de propósito: o nome
 * já carrega o código do orçamento, então regenerar substitui a versão anterior.
 */
export async function savePdf(
  doc: PdfDocumentLike,
  filename: string,
  destination?: PdfDestination | null,
): Promise<PdfSaveResult> {
  const handle = destination?.handle
  if (!handle) {
    doc.save(filename)
    return {
      kind: 'downloads',
      folderName: destination?.folderName ?? null,
      reason: destination?.fallbackReason ?? null,
    }
  }

  const folderFilename = safeFileName(filename)
  let writable: PdfWritable | undefined
  try {
    const fileHandle = await handle.getFileHandle(folderFilename, { create: true })
    writable = await fileHandle.createWritable()
    await writable.write(doc.output('blob'))
    await writable.close()
    return { kind: 'folder', folderName: handle.name, filename: folderFilename }
  } catch {
    // Descarta o arquivo temporário da gravação interrompida.
    try { await writable?.abort?.() } catch { /* já falhou: o fallback abaixo é o que importa */ }
    doc.save(filename)
    return { kind: 'downloads', folderName: handle.name, reason: 'write-failed' }
  }
}
