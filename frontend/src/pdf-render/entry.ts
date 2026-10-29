import { buildOrderPdf } from '../lib/generatePDF'
import { snapshotToBuildInput, type OrderPdfSnapshot } from '../lib/orderPdfSnapshot'

declare global {
  interface Window {
    ilyaRenderOrderPdf?: (snapshot: OrderPdfSnapshot) => Promise<string>
  }
}

// Converte o ArrayBuffer do PDF em base64 por blocos para não estourar a pilha
// de argumentos de `String.fromCharCode` em documentos maiores.
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  const chunkSize = 0x8000
  const chunks: string[] = []
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const slice = bytes.subarray(offset, offset + chunkSize)
    chunks.push(String.fromCharCode(...slice))
  }
  return btoa(chunks.join(''))
}

async function renderOrderPdf(snapshot: OrderPdfSnapshot): Promise<string> {
  if (snapshot?.schema_version !== 2) {
    throw new Error('unsupported_snapshot_version')
  }
  const doc = await buildOrderPdf(snapshotToBuildInput(snapshot))
  const buffer = doc.output('arraybuffer')
  return arrayBufferToBase64(buffer)
}

window.ilyaRenderOrderPdf = renderOrderPdf
