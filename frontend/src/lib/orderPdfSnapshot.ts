import type { Client, Order, Product, Representative } from '../types'
import type { BuildOrderPdfInput } from './generatePDF'

// Campos de `Product` efetivamente lidos por `buildOrderPdf` em `generatePDF.ts`:
// - `product_code`: chave do mapa de fotos (`productByCode`) e busca por item (`products.find`)
// - `thumbnail_url` e `photo_url`: origem da imagem (`product?.thumbnail_url ?? product?.photo_url`)
// - `components`: componentes do conjunto (`qty`, `description`, `is_circular`, `largura`,
//   `profundidade`, `altura` e `optionals[{ category, color_name }]`)
// - `is_set` e `type`: identificação de conjunto (`product.is_set || isConjuntoType(product.type) || components.length > 0`)
export interface OrderPdfProductSnapshot {
  product_code: string
  type: string | null
  is_set: boolean
  components: Product['components'] // o que o gerador lê: qty, description, medidas, optionals[{category,color_name}]
  thumbnail_url: string | null // o servidor injeta aqui um data: URL (a foto congelada)
  photo_url: string | null
}

export interface OrderPdfSnapshot {
  schema_version: 2
  locale: 'pt-BR' | 'pt-PT' | 'en-GB'
  order: Order
  client: Client
  representative: Representative | null
  products: OrderPdfProductSnapshot[]
  category_labels: Record<string, string> // código da categoria de opcional -> nome (o que `catLabel` devolve no navegador)
}

export function snapshotToBuildInput(snapshot: OrderPdfSnapshot): BuildOrderPdfInput {
  const documentLocale =
    snapshot.locale === 'en-GB'
      ? 'en-GB'
      : snapshot.locale === 'pt-PT'
        ? 'pt-PT'
        : undefined

  return {
    order: snapshot.order,
    client: snapshot.client,
    rep: snapshot.representative,
    products: snapshot.products as unknown as Product[],
    catLabel: (code: string) => snapshot.category_labels[code] ?? code,
    documentLocale,
  }
}
