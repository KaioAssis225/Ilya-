import assert from 'node:assert/strict'
import { test, vi } from 'vitest'

import {
  clearDestinationFolder,
  createIndexedDbStore,
  describePdfSave,
  isFolderPickerSupported,
  loadDestinationFolderName,
  pickDestinationFolder,
  resolvePdfDestination,
  safeFileName,
  savePdf,
} from './pdfDestination.ts'
import type {
  DestinationStore,
  FsPermissionState,
  PdfDestination,
  PdfDirectoryHandle,
  PdfDocumentLike,
} from './pdfDestination.ts'

function createMapStore(): DestinationStore & { entries: Map<string, PdfDirectoryHandle> } {
  const entries = new Map<string, PdfDirectoryHandle>()
  return {
    entries,
    async get(key) { return entries.get(key) ?? null },
    async set(key, handle) { entries.set(key, handle); return true },
    async delete(key) { return entries.delete(key) },
  }
}

interface FakeFolder {
  handle: PdfDirectoryHandle
  getFileHandle: ReturnType<typeof vi.fn>
  queryPermission: ReturnType<typeof vi.fn>
  requestPermission: ReturnType<typeof vi.fn>
  write: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
  abort: ReturnType<typeof vi.fn>
}

function createFolder(
  name: string,
  { query = 'granted', request = 'granted' }: { query?: FsPermissionState; request?: FsPermissionState } = {},
): FakeFolder {
  const write = vi.fn(async () => {})
  const close = vi.fn(async () => {})
  const abort = vi.fn(async () => {})
  const getFileHandle = vi.fn(async () => ({ createWritable: async () => ({ write, close, abort }) }))
  const queryPermission = vi.fn(async () => query)
  const requestPermission = vi.fn(async () => request)
  const handle: PdfDirectoryHandle = { name, getFileHandle, queryPermission, requestPermission }
  return { handle, getFileHandle, queryPermission, requestPermission, write, close, abort }
}

function createDoc(blob = new Blob(['pdf'])) {
  const save = vi.fn()
  const output = vi.fn(() => blob)
  const doc: PdfDocumentLike = { save, output }
  return { doc, save, output, blob }
}

function destinationOf(folder: FakeFolder): PdfDestination {
  return { handle: folder.handle, folderName: folder.handle.name, fallbackReason: null }
}

test('sem pasta escolhida: baixa em Downloads e não tenta gravar', async () => {
  const { doc, save, output } = createDoc()
  const result = await savePdf(doc, 'ORC-1_Cliente.pdf', null)

  assert.deepEqual(save.mock.calls, [['ORC-1_Cliente.pdf']])
  assert.equal(output.mock.calls.length, 0)
  assert.deepEqual(result, { kind: 'downloads', folderName: null, reason: null })
})

test('pasta com permissão concedida: grava o blob e não chama doc.save', async () => {
  const folder = createFolder('Orçamentos')
  const { doc, save, blob } = createDoc()
  const result = await savePdf(doc, 'ORC-1_Cliente.pdf', destinationOf(folder))

  assert.equal(save.mock.calls.length, 0)
  assert.deepEqual(result, { kind: 'folder', folderName: 'Orçamentos', filename: 'ORC-1_Cliente.pdf' })
  assert.deepEqual(folder.getFileHandle.mock.calls, [['ORC-1_Cliente.pdf', { create: true }]])
  assert.deepEqual(folder.write.mock.calls, [[blob]])
  assert.equal(folder.close.mock.calls.length, 1)
})

test('permissão em "prompt" e concedida ao pedir: resolve para a pasta', async () => {
  const folder = createFolder('Pasta', { query: 'prompt', request: 'granted' })
  const store = createMapStore()
  await store.set('user-1', folder.handle)

  const destination = await resolvePdfDestination('user-1', { store })

  assert.equal(destination.handle, folder.handle)
  assert.equal(destination.folderName, 'Pasta')
  assert.equal(destination.fallbackReason, null)
  assert.equal(folder.requestPermission.mock.calls.length, 1)
})

test('permissão já concedida não pede de novo', async () => {
  const folder = createFolder('Pasta')
  const store = createMapStore()
  await store.set('user-1', folder.handle)

  await resolvePdfDestination('user-1', { store })

  assert.equal(folder.requestPermission.mock.calls.length, 0)
})

test('permissão negada: cai em Downloads com motivo permission-denied', async () => {
  const folder = createFolder('Pasta', { query: 'prompt', request: 'denied' })
  const store = createMapStore()
  await store.set('user-1', folder.handle)

  const destination = await resolvePdfDestination('user-1', { store })
  assert.deepEqual(destination, { handle: null, folderName: 'Pasta', fallbackReason: 'permission-denied' })

  const { doc, save } = createDoc()
  const result = await savePdf(doc, 'a.pdf', destination)
  assert.deepEqual(save.mock.calls, [['a.pdf']])
  assert.deepEqual(result, { kind: 'downloads', folderName: 'Pasta', reason: 'permission-denied' })
})

test('requestPermission lançando (sem gesto do usuário) vale como negada', async () => {
  const folder = createFolder('Pasta', { query: 'prompt' })
  folder.requestPermission.mockRejectedValue(new DOMException('needs user activation', 'SecurityError'))
  const store = createMapStore()
  await store.set('user-1', folder.handle)

  const destination = await resolvePdfDestination('user-1', { store })

  assert.deepEqual(destination, { handle: null, folderName: 'Pasta', fallbackReason: 'permission-denied' })
})

test('API ausente: não há seletor e o PDF segue para Downloads', async () => {
  assert.equal(isFolderPickerSupported({}), false)
  assert.equal(isFolderPickerSupported({ showDirectoryPicker: () => {} }), true)
  // jsdom não tem showDirectoryPicker: é o caso de Firefox/Safari/celular.
  assert.equal(isFolderPickerSupported(), false)

  assert.deepEqual(await pickDestinationFolder('user-1'), { status: 'unsupported' })

  const destination = await resolvePdfDestination('user-1', { store: createMapStore() })
  assert.deepEqual(destination, { handle: null, folderName: null, fallbackReason: null })
})

test('falha ao abrir o arquivo: cai em Downloads com write-failed', async () => {
  const folder = createFolder('Pasta')
  folder.getFileHandle.mockRejectedValue(new TypeError('Name is not allowed'))
  const { doc, save } = createDoc()

  const result = await savePdf(doc, 'a.pdf', destinationOf(folder))

  assert.deepEqual(save.mock.calls, [['a.pdf']])
  assert.deepEqual(result, { kind: 'downloads', folderName: 'Pasta', reason: 'write-failed' })
})

test('falha no meio da gravação: aborta a escrita e cai em Downloads', async () => {
  const folder = createFolder('Pasta')
  folder.write.mockRejectedValue(new Error('disk full'))
  const { doc, save } = createDoc()

  const result = await savePdf(doc, 'a.pdf', destinationOf(folder))

  assert.equal(folder.abort.mock.calls.length, 1)
  assert.equal(folder.close.mock.calls.length, 0)
  assert.deepEqual(save.mock.calls, [['a.pdf']])
  assert.deepEqual(result, { kind: 'downloads', folderName: 'Pasta', reason: 'write-failed' })
})

test('escolher pasta: guarda o handle na chave do usuário', async () => {
  const store = createMapStore()
  const folder = createFolder('Nova Pasta')
  const picker = vi.fn(async () => folder.handle)

  const result = await pickDestinationFolder('user-1', { store, picker })

  assert.deepEqual(result, { status: 'chosen', folderName: 'Nova Pasta' })
  assert.deepEqual(picker.mock.calls, [[{ mode: 'readwrite', id: 'ilya-orcamentos' }]])
  assert.equal(store.entries.get('user-1'), folder.handle)
})

test('escolher pasta: cancelar mantém a pasta anterior', async () => {
  const store = createMapStore()
  const previous = createFolder('Anterior')
  await store.set('user-1', previous.handle)
  const picker = vi.fn(async () => { throw new DOMException('The user aborted a request.', 'AbortError') })

  const result = await pickDestinationFolder('user-1', { store, picker })

  assert.deepEqual(result, { status: 'cancelled' })
  assert.equal(store.entries.get('user-1'), previous.handle)
})

test('escolher pasta: erro do seletor ou do armazenamento vira error', async () => {
  const store = createMapStore()
  const failing = vi.fn(async () => { throw new Error('boom') })
  assert.deepEqual(await pickDestinationFolder('user-1', { store, picker: failing }), { status: 'error' })

  const unwritableStore: DestinationStore = { ...createMapStore(), set: async () => false }
  const picker = vi.fn(async () => createFolder('Pasta').handle)
  assert.deepEqual(await pickDestinationFolder('user-1', { store: unwritableStore, picker }), { status: 'error' })
})

test('usar Downloads limpa a pasta guardada', async () => {
  const store = createMapStore()
  await store.set('user-1', createFolder('Pasta').handle)

  assert.equal(await clearDestinationFolder('user-1', { store }), true)
  assert.equal(await loadDestinationFolderName('user-1', { store }), null)
})

test('nome do arquivo na pasta é sanitizado; o download mantém o original', async () => {
  assert.equal(safeFileName('a/b\\c:d*e?f"g<h>i|j\tk'), 'a_b_c_d_e_f_g_h_i_j_k')
  assert.equal(safeFileName('ORC-1_João_Silva.pdf'), 'ORC-1_João_Silva.pdf')

  const original = 'ORC/1: teste?.pdf'
  const folder = createFolder('Pasta')
  const { doc } = createDoc()
  const result = await savePdf(doc, original, destinationOf(folder))
  assert.deepEqual(result, { kind: 'folder', folderName: 'Pasta', filename: 'ORC_1_ teste_.pdf' })
  assert.equal(folder.getFileHandle.mock.calls[0][0], 'ORC_1_ teste_.pdf')

  const denied: PdfDestination = { handle: null, folderName: 'Pasta', fallbackReason: 'permission-denied' }
  const fallback = createDoc()
  await savePdf(fallback.doc, original, denied)
  assert.deepEqual(fallback.save.mock.calls, [[original]])
})

test('avisos: pasta confirma o caminho; fallback explica por que foi para Downloads', () => {
  assert.deepEqual(describePdfSave({ kind: 'folder', folderName: 'Pasta', filename: 'a.pdf' }, false), {
    tone: 'success',
    text: 'Salvo em Pasta/a.pdf',
  })
  assert.equal(describePdfSave({ kind: 'folder', folderName: 'Pasta', filename: 'a.pdf' }, true)?.text, 'Saved to Pasta/a.pdf')
  assert.equal(describePdfSave({ kind: 'downloads', folderName: null, reason: null }, false), null)
  assert.match(describePdfSave({ kind: 'downloads', folderName: 'Pasta', reason: 'permission-denied' }, false)?.text ?? '', /Sem acesso.*"Pasta".*Downloads/)
  assert.match(describePdfSave({ kind: 'downloads', folderName: 'Pasta', reason: 'write-failed' }, true)?.text ?? '', /Could not write.*"Pasta".*Downloads/)
  assert.equal(describePdfSave({ kind: 'downloads', folderName: 'Pasta', reason: 'write-failed' }, false)?.tone, 'warning')
})

test('a pasta de um usuário não vaza para outro', async () => {
  const store = createMapStore()
  await store.set('user-1', createFolder('Pasta do usuário 1').handle)

  assert.deepEqual(await resolvePdfDestination('user-2', { store }), { handle: null, folderName: null, fallbackReason: null })
  assert.equal(await loadDestinationFolderName('user-2', { store }), null)
  assert.equal(await loadDestinationFolderName('user-1', { store }), 'Pasta do usuário 1')
})

test('sem IndexedDB (modo privado, jsdom): lembrar pasta falha sem lançar', async () => {
  const store = createIndexedDbStore()

  assert.equal(await store.get('user-1'), null)
  assert.equal(await store.set('user-1', createFolder('Pasta').handle), false)
  assert.equal(await store.delete('user-1'), false)
  assert.equal(await resolvePdfDestination('user-1').then(destination => destination.handle), null)
})
