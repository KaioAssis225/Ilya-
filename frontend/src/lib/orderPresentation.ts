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
