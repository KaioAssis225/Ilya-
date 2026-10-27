/**
 * Moeda, locale e rótulo fiscal de um pedido, para exibição.
 *
 * Isolado de `generatePDF` por dois motivos: a geração do PDF depende de jsPDF e
 * do DOM, e esta é a regra que precisa de teste — o documento tem de refletir o
 * **snapshot** do pedido, não a configuração do mercado em que o usuário está
 * agora. Um pedido BR aberto por quem está em PT continua imprimindo BRL/IPI.
 */

export type MarketCode = 'BR' | 'EU'
export type TaxLabel = 'IPI' | 'IVA'
export type CurrencyCode = 'BRL' | 'EUR'

/** Só o que a apresentação precisa; o pedido real tem muito mais campos. */
export interface PresentableOrder {
  market_code?: MarketCode
  currency?: CurrencyCode
  locale?: string
  items?: Array<{ tax_label?: TaxLabel }>
}

export interface OrderPresentation {
  currency: CurrencyCode
  locale: string
  taxLabel: TaxLabel
}

/**
 * Defaults por mercado, usados só quando o pedido não traz o campo — caso de
 * registro anterior às colunas de moeda, locale e rótulo.
 */
const MARKET_DEFAULTS: Record<MarketCode, OrderPresentation> = {
  BR: { currency: 'BRL', locale: 'pt-BR', taxLabel: 'IPI' },
  EU: { currency: 'EUR', locale: 'pt-PT', taxLabel: 'IVA' },
}

export function resolveOrderPresentation(order: PresentableOrder): OrderPresentation {
  const fallback = MARKET_DEFAULTS[order.market_code ?? 'BR']
  return {
    currency: order.currency ?? fallback.currency,
    locale: order.locale ?? fallback.locale,
    // O rótulo é por item no banco; na prática todos os itens de um pedido
    // compartilham o mesmo, então o primeiro preenchido representa o documento.
    taxLabel: order.items?.find(item => item.tax_label)?.tax_label ?? fallback.taxLabel,
  }
}

export function formatOrderMoney(
  value: number,
  { currency, locale }: Pick<OrderPresentation, 'currency' | 'locale'>,
): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value)
}

// ── Documento (PDF) ───────────────────────────────────────────────────────────
// Portugal opera com a marca IBTW e envia o pedido ao cliente em inglês; o
// Brasil segue ILYA em português. A tela interna "Visualizar" continua em
// português — este idioma vale só para o documento entregue ao cliente.

export interface OrderDocumentLabels {
  documentTitle: string; order: string; date: string; quote: string; continued: string
  seller: string; representative: string; client: string; none: string; noEmail: string
  taxId: string; taxIdMissing: string; commercialNotice: string; page: string
  product: string; qty: string; unitPrice: string; total: string
  dimensions: string; itemNote: string; itemComment: string; options: string; noPhoto: string
  totalItems: string; totalArea: string; grandTotal: string; notes: string
  repSignature: string; clientSignature: string; footer: string
}

export interface OrderDocumentSeller {
  legalName: string
  taxIdLabel: string
  taxId: string
  addressLines: string[]
}

export interface OrderDocument {
  brand: 'ILYA' | 'IBTW'
  locale: string
  currency: CurrencyCode
  taxLabel: string
  labels: OrderDocumentLabels
  seller?: OrderDocumentSeller
}

const PT_LABELS: OrderDocumentLabels = {
  documentTitle: 'CONFIRMAÇÃO DE PEDIDO', order: 'PEDIDO', date: 'Data', quote: 'Orçamento', continued: 'CONTINUAÇÃO',
  seller: 'EMPRESA VENDEDORA', representative: 'REPRESENTANTE', client: 'CLIENTE', none: 'Nenhum', noEmail: 'E-mail não informado',
  taxId: 'CPF/CNPJ', taxIdMissing: 'não informado', commercialNotice: 'Pedido comercial. Este documento não substitui a nota fiscal.', page: 'Página',
  product: 'PRODUTO', qty: 'QTD', unitPrice: 'VALOR UN.', total: 'TOTAL',
  dimensions: 'Dimensões', itemNote: 'Obs.', itemComment: 'Comentário', options: 'Opcionais', noPhoto: 'sem\nfoto',
  totalItems: 'Total de Itens:', totalArea: 'Área total:', grandTotal: 'VALOR TOTAL:', notes: 'OBSERVAÇÕES',
  repSignature: 'Representante / Ilya', clientSignature: 'Cliente / Contratado',
  footer: 'Ilya — Documento gerado automaticamente',
}

const EN_LABELS: OrderDocumentLabels = {
  documentTitle: 'ORDER CONFIRMATION', order: 'ORDER', date: 'Date', quote: 'Quote', continued: 'CONTINUED',
  seller: 'SELLER / LEGAL ENTITY', representative: 'SALES CONTACT', client: 'BILL TO', none: 'None', noEmail: 'No email provided',
  taxId: 'VAT / TAX ID', taxIdMissing: 'not provided', commercialNotice: 'Commercial order confirmation. This document is not an invoice.', page: 'Page',
  product: 'PRODUCT', qty: 'QTY', unitPrice: 'UNIT PRICE', total: 'TOTAL',
  dimensions: 'Dimensions', itemNote: 'Note', itemComment: 'Comment', options: 'Options', noPhoto: 'no\nphoto',
  totalItems: 'Total items:', totalArea: 'Total area:', grandTotal: 'GRAND TOTAL:', notes: 'NOTES',
  repSignature: 'Representative / IBTW', clientSignature: 'Client',
  footer: 'IBTW — Automatically generated document',
}

export function resolveOrderDocument(order: PresentableOrder): OrderDocument {
  const presentation = resolveOrderPresentation(order)
  if ((order.market_code ?? 'BR') === 'EU') {
    return {
      brand: 'IBTW',
      locale: 'en-GB',
      currency: presentation.currency,
      taxLabel: presentation.taxLabel === 'IVA' ? 'VAT' : presentation.taxLabel,
      labels: EN_LABELS,
      seller: {
        legalName: 'IBTW LIVING LDA',
        taxIdLabel: 'NIF',
        taxId: '519635698',
        addressLines: [
          'Rua do Multipark I, n.º 43, fração D',
          '4595-542 Seroa, Paços de Ferreira, Portugal',
        ],
      },
    }
  }
  return {
    brand: 'ILYA',
    locale: presentation.locale,
    currency: presentation.currency,
    taxLabel: presentation.taxLabel,
    labels: PT_LABELS,
  }
}
