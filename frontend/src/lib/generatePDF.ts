import { optionalName, optionalCategoryLabel } from './optionalLabels'
import jsPDF from 'jspdf'
import type { Order, Client, Representative, Product } from '../types'
import { formatDimensions } from './measurements'
import { resolveOrderDocument } from './orderPresentation'
import { isConjuntoType } from './productType'
import { orderOptionalSlots } from './optionalApplications'
import { formatArea, formatRugPieces, formatRugSize } from './areaProduct'
import { calculateLinePricing, lineTax, roundMoney } from './linePricing'
import { IBTW_LOGO_LDA, IBTW_LOGO_LTD } from './ibtwLogoAssets'
import { savePdf, type PdfDestination, type PdfSaveResult } from './pdfDestination'

// ── Colors (idênticos ao protótipo) ──────────────────────────────────────────
const ILYA_GOLD: [number, number, number] = [198, 157, 48]
const IBTW_GREEN: [number, number, number] = [69, 88, 66]
const DARK: [number, number, number] = [44, 36, 32]
const MUTED: [number, number, number] = [117, 107, 97]
const LIGHT: [number, number, number] = [245, 240, 235]
const LINE: [number, number, number] = [232, 224, 214]

// ── Carrega imagem de URL para base64 via canvas ──────────────────────────────
interface LoadedImage {
  b64: string
  width: number
  height: number
  format: 'JPEG'
}

const PDF_IMAGE_MAX_EDGE = 640
const PDF_IMAGE_QUALITY = 0.84
const PDF_IMAGE_CONCURRENCY = 3

async function urlToBase64(url: string): Promise<LoadedImage | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        const scale = Math.min(1, PDF_IMAGE_MAX_EDGE / Math.max(img.naturalWidth, img.naturalHeight))
        const w = Math.max(1, Math.round(img.naturalWidth * scale))
        const h = Math.max(1, Math.round(img.naturalHeight * scale))
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d')!
        // JPEG não preserva transparência. As fotos do catálogo usam fundo de
        // estúdio branco, então preencher explicitamente mantém o resultado
        // previsível mesmo se algum arquivo de origem tiver canal alpha.
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, w, h)
        const r = w * 0.08
        ctx.beginPath()
        ctx.moveTo(r, 0)
        ctx.lineTo(w - r, 0)
        ctx.quadraticCurveTo(w, 0, w, r)
        ctx.lineTo(w, h - r)
        ctx.quadraticCurveTo(w, h, w - r, h)
        ctx.lineTo(r, h)
        ctx.quadraticCurveTo(0, h, 0, h - r)
        ctx.lineTo(0, r)
        ctx.quadraticCurveTo(0, 0, r, 0)
        ctx.closePath()
        ctx.clip()
        ctx.drawImage(img, 0, 0, w, h)
        resolve({
          b64: canvas.toDataURL('image/jpeg', PDF_IMAGE_QUALITY),
          width: w,
          height: h,
          format: 'JPEG',
        })
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

async function mapWithConcurrency<T>(
  items: T[],
  concurrency: number,
  task: (item: T) => Promise<void>,
): Promise<void> {
  let cursor = 0
  const workers = Array.from(
    { length: Math.min(concurrency, items.length) },
    async () => {
      while (cursor < items.length) {
        const item = items[cursor]
        cursor += 1
        await task(item)
      }
    },
  )
  await Promise.all(workers)
}

// ── Calcula o retângulo proporcional (efeito object-contain) dentro de um box quadrado ──
function containBox(width: number, height: number, box: number): { w: number; h: number; dx: number; dy: number } {
  const ratio = width / height
  const w = ratio >= 1 ? box : box * ratio
  const h = ratio >= 1 ? box / ratio : box
  return { w, h, dx: (box - w) / 2, dy: (box - h) / 2 }
}

// Recortes exatos das artes oficiais LDA/LTD, sem redesenhar letras ou cores.
function drawIbtwLogo(doc: jsPDF, dataUrl: string, x: number, y: number): void {
  const outputWidth = 45
  const outputHeight = outputWidth * 249 / 497
  doc.addImage(dataUrl, 'JPEG', x, y, outputWidth, outputHeight, undefined, 'FAST')
}

function formatMoney(value: number, currency: string, locale: string): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value)
}

type AddressParty = Pick<Client, 'address' | 'numero' | 'city' | 'state' | 'country' | 'region' | 'cep'>

function formatAddress(person: AddressParty, market: 'BR' | 'EU'): string {
  const street = `${person.address}${person.numero ? `, ${person.numero}` : ''}`
  if (market === 'BR') {
    const cityState = [person.city, person.state].filter(Boolean).join('/')
    return [street, cityState, person.cep].filter(Boolean).join(' - ')
  }
  const locality = [person.cep, person.city].filter(Boolean).join(' ')
  const regionCountry = [person.region, person.country].filter(Boolean).join(', ')
  return [street, locality, regionCountry].filter(Boolean).join(' - ')
}

export interface BuildOrderPdfInput {
  order: Order
  client: Client
  rep: Representative | null
  products: Product[]
  catLabel?: (code: string) => string
  documentLocale?: 'pt-PT' | 'en-GB'
}

// ── Gerador principal ─────────────────────────────────────────────────────────
export async function buildOrderPdf(input: BuildOrderPdfInput): Promise<jsPDF> {
  const {
    order,
    client,
    rep,
    products,
    catLabel = (c) => c,
    documentLocale,
  } = input
  const doc = new jsPDF('p', 'mm', 'a4')
  // Moeda, locale e rótulo saem do snapshot do pedido (ver orderPresentation):
  // um pedido antigo precisa imprimir o tributo com que foi contratado, não o
  // do mercado em que o usuário está agora.
  const orderDocument = resolveOrderDocument(documentLocale ? { ...order, locale: documentLocale } : order)
  const { currency, locale, taxLabel, brand, brandSuffix, labels: L, seller } = orderDocument
  // IVA (Portugal) vai no fecho do documento; IPI (Brasil) segue embutido na linha.
  const taxOnTotal = order.market_code === 'EU'
  const accentColor = taxOnTotal ? IBTW_GREEN : ILYA_GOLD
  const w = doc.internal.pageSize.getWidth()

  // Cada produto é rasterizado uma vez. Thumbnails já têm resolução suficiente
  // para o box de 14 mm e evitam baixar a foto original quando disponíveis.
  const photoMap: Record<string, LoadedImage> = {}
  const productByCode = new Map(products.map(product => [product.product_code, product]))
  const uniqueCodes = Array.from(new Set(order.items.map(item => item.product_code)))
  await mapWithConcurrency(uniqueCodes, PDF_IMAGE_CONCURRENCY, async (productCode) => {
    const product = productByCode.get(productCode)
    const source = product?.thumbnail_url ?? product?.photo_url
    if (!source) return
    const photo = await urlToBase64(source)
    if (photo) photoMap[productCode] = photo
  })

  let y = 20

  // ── Linha de marca superior ─────────────────────────────────────────────────
  doc.setDrawColor(...accentColor)
  doc.setLineWidth(0.5)
  doc.line(20, y, w - 20, y)
  y += 8

  // ── Logo ILYA / IBTW ───────────────────────────────────────────────────────
  doc.setTextColor(...accentColor)
  if (brandSuffix) {
    drawIbtwLogo(doc, brandSuffix === 'LTD.' ? IBTW_LOGO_LTD : IBTW_LOGO_LDA, 20, 22)
  } else {
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(28)
    doc.text(brand, 20, y)
  }

  doc.setDrawColor(...accentColor)
  doc.setLineWidth(0.3)
  const logoRuleY = brandSuffix ? 47 : y + 5
  doc.line(20, logoRuleY, 60, logoRuleY)
  doc.setFontSize(6.5)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text(L.documentTitle, 20, logoRuleY + 7)

  // ── Número do pedido (canto direito) ───────────────────────────────────────
  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.setFont('helvetica', 'bold')
  doc.text(L.order, w - 20, 28, { align: 'right' })

  doc.setFont('helvetica', 'normal')
  doc.setFontSize(14)
  doc.setTextColor(...accentColor)
  doc.text(order.code, w - 20, 35, { align: 'right' })

  doc.setFontSize(8)
  doc.setTextColor(...MUTED)
  doc.text(
    L.date + ': ' + new Date(order.created_at).toLocaleDateString(locale),
    w - 20,
    42,
    { align: 'right' },
  )
  doc.text(L.quote + ': ' + order.orc_id, w - 20, 47, { align: 'right' })

  y = brandSuffix ? 60 : 55

  // ── Partes do pedido ────────────────────────────────────────────────────────
  const boxW = (w - 50) / 2
  doc.setFillColor(...LIGHT)
  const partyBoxH = seller ? 44 : 35
  doc.roundedRect(20, y, boxW, partyBoxH, 2, 2, 'F')
  doc.roundedRect(20 + boxW + 10, y, boxW, partyBoxH, 2, 2, 'F')

  const bx = 24
  const rx = 20 + boxW + 14

  if (seller) {
    // Entidade legal vendedora: denominação, NIF e sede do comprovativo da AT.
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'bold')
    doc.text(L.seller, bx, y + 6)
    doc.setFontSize(10)
    doc.setTextColor(...DARK)
    doc.text(seller.legalName, bx, y + 13)
    doc.setFontSize(8)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(...MUTED)
    doc.text(`${seller.taxIdLabel}: ${seller.taxId}`, bx, y + 20)
    seller.addressLines.forEach((line, index) => doc.text(line, bx, y + 27 + index * 5))
  } else {
    // No mercado BR ainda não há uma entidade legal configurada; preserva o
    // bloco original do representante, sem inventar dados fiscais.
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'bold')
    doc.text(L.representative, bx, y + 6)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(9)
    doc.setTextColor(...DARK)
    doc.text(rep ? rep.name : L.none, bx, y + 12)
    if (rep) {
      doc.setFontSize(8)
      doc.setTextColor(...MUTED)
      doc.text(rep.phone, bx, y + 17)
      doc.text(rep.email || L.noEmail, bx, y + 22)
      const repAddr = formatAddress(rep, order.market_code)
      doc.text(doc.splitTextToSize(repAddr, boxW - 8).slice(0, 2), bx, y + 27)
    }
  }

  // Cliente / adquirente, incluindo a identificação fiscal disponível.
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text(L.client, rx, y + 6)
  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.text(client.name, rx, y + 12)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(7.5)
  doc.setTextColor(...MUTED)
  const clientTaxId = order.market_code === 'EU' ? client.tax_id : client.cpf_cnpj
  doc.text(`${L.taxId}: ${clientTaxId || L.taxIdMissing}`, rx, y + 18)
  doc.text(client.phone, rx, y + 23)
  doc.text(client.email || L.noEmail, rx, y + 28)
  const clientAddr = formatAddress(client, order.market_code)
  doc.text(doc.splitTextToSize(clientAddr, boxW - 8).slice(0, 2), rx, y + 34)

  y += partyBoxH + 7

  // O vendedor continua identificado como contacto comercial, separado da
  // entidade legal que efetivamente celebra o pedido.
  if (seller) {
    doc.setFillColor(...LIGHT)
    doc.roundedRect(20, y, w - 40, 17, 2, 2, 'F')
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'bold')
    doc.text(L.representative, 24, y + 6)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8.5)
    doc.setTextColor(...DARK)
    doc.text(rep ? rep.name : L.none, 24, y + 12)
    if (rep) {
      doc.setFontSize(7.5)
      doc.setTextColor(...MUTED)
      doc.text([rep.phone, rep.email || L.noEmail].filter(Boolean).join('  ·  '), w - 24, y + 12, { align: 'right' })
    }
    y += 24
  } else {
    y += 7
  }

  // ── Colunas numéricas, na mesma ordem da tela ──────────────────────────────
  // Qtd · Preço-base · Desconto (%) · Valor c/ desc. · (IPI no Brasil) · Subtotal.
  // O subtotal é o oficial (linha arredondada uma vez, como no servidor); o valor
  // unitário com desconto é só informativo (ver lib/linePricing). As larguras são
  // medidas com o texto real de todos os itens e o bloco do produto usa o espaço
  // que sobra, então nenhum valor invade a coluna vizinha nem o nome do produto.
  const COL_GAP = 3
  const TABLE_RIGHT = 186
  const PRODUCT_X = 40
  const measure = (text: string, size: number, style: 'normal' | 'bold'): number => {
    doc.setFont('helvetica', style)
    doc.setFontSize(size)
    return doc.getTextWidth(text)
  }
  const unitDiscountText = (value: number) => `- ${formatMoney(value, currency, locale)}`
  const measurementLocale = locale === 'en-GB' ? 'en-GB' : order.market_code === 'EU' ? 'pt-PT' : 'pt-BR'
  const itemRows = order.items.map((item) => {
    const discount = Number(item.discount || 0)
    const ipiRate = Number(item.ipi_rate || 0)
    const pricing = calculateLinePricing(Number(item.unit_price), discount, Number(item.qty))
    // Brasil: IPI entra na linha. Portugal: IVA só no fecho (Subtotal → IVA → Total).
    const lineTotal = taxOnTotal
      ? pricing.subtotal
      : roundMoney(pricing.subtotal + lineTax(pricing.subtotal, ipiRate))
    return {
      discount,
      ipiRate,
      pricing,
      lineTotal,
      piecesText: item.sold_by_area && (item.area_pieces ?? 1) > 1
        ? formatRugPieces(item.area_pieces ?? 1, measurementLocale)
        : null,
      qtyText: item.sold_by_area ? formatArea(item.qty, locale) : String(item.qty),
      baseText: formatMoney(pricing.basePrice, currency, locale),
      discountText: `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(discount)}%`,
      netText: formatMoney(pricing.netUnitPrice, currency, locale),
      subtotalText: formatMoney(lineTotal, currency, locale),
    }
  })
  type ColumnKey = 'qty' | 'base' | 'discount' | 'net' | 'ipi' | 'subtotal'
  interface NumericColumn { key: ColumnKey; label: string; minWidth: number; right: number; width: number }
  const columnDefs: Array<{ key: ColumnKey; label: string; minWidth: number }> = [
    { key: 'qty', label: L.qty, minWidth: 10 },
    { key: 'base', label: L.basePrice, minWidth: 17 },
    { key: 'discount', label: L.discount, minWidth: 13 },
    { key: 'net', label: L.netUnitPrice, minWidth: 17 },
    ...(taxOnTotal ? [] : [{ key: 'ipi' as const, label: taxLabel, minWidth: 8 }]),
    { key: 'subtotal', label: L.subtotal, minWidth: 19 },
  ]
  const columns: NumericColumn[] = columnDefs.map((column) => ({ ...column, right: 0, width: column.minWidth }))
  const columnByKey = (key: ColumnKey) => columns.find((column) => column.key === key)
  for (const column of columns) {
    const widest = (texts: Array<[string, number, 'normal' | 'bold']>) => Math.max(0, ...texts.map(([text, size, style]) => measure(text, size, style)))
    // O cabeçalho quebra em até 2 linhas, mas nenhuma palavra pode ser cortada.
    const longestWord = Math.max(...column.label.split(' ').map((word) => measure(word, 7, 'bold')))
    const contents = itemRows.flatMap((row): Array<[string, number, 'normal' | 'bold']> => {
      switch (column.key) {
        case 'qty': return row.piecesText ? [[row.qtyText, 8, 'normal'], [row.piecesText, 6, 'normal']] : [[row.qtyText, 8, 'normal']]
        case 'base': return [[row.baseText, 7.5, 'normal']]
        case 'discount': return row.discount > 0
          ? [[row.discountText, 7.5, 'bold'], [unitDiscountText(row.pricing.unitDiscount), 6, 'normal']]
          : [[row.discountText, 7.5, 'bold']]
        case 'net': return [[row.netText, 7.5, 'normal']]
        case 'ipi': return [[`${row.ipiRate}%`, 7.5, 'bold']]
        default: return [[row.subtotalText, 8, 'bold']]
      }
    })
    column.width = Math.max(column.minWidth, longestWord, widest(contents))
  }
  let columnRight = TABLE_RIGHT
  for (const column of [...columns].reverse()) {
    column.right = columnRight
    columnRight -= column.width + COL_GAP
  }
  const firstColumnLeft = columns[0].right - columns[0].width
  // Texto do produto limitado ao espaço real até a primeira coluna numérica.
  const PRODUCT_TEXT_WIDTH = Math.max(20, firstColumnLeft - COL_GAP - PRODUCT_X)

  const drawTableHeader = (top: number): number => {
    doc.setDrawColor(...LINE)
    doc.setLineWidth(0.3)
    doc.line(20, top, w - 20, top)
    const labelY = top + 8
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'bold')
    doc.text(L.product, 22, labelY)
    for (const column of columns) {
      const labelLines: string[] = doc.splitTextToSize(column.label, column.width + COL_GAP - 1)
      labelLines.forEach((line, index) => {
        doc.text(line, column.right, labelY - (labelLines.length - 1 - index) * 3, { align: 'right' })
      })
    }
    doc.setDrawColor(...LINE)
    doc.line(20, labelY + 4, w - 20, labelY + 4)
    return labelY + 11
  }

  const drawContinuationHeader = (): number => {
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(13)
    doc.setTextColor(...accentColor)
    doc.text(brand, 20, 23)
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.text(`${order.code} · ${L.continued}`, w - 20, 23, { align: 'right' })
    return 30
  }

  // ── Cabeçalho da tabela de itens ───────────────────────────────────────────
  y = drawTableHeader(y)

  // ── Linhas de itens ────────────────────────────────────────────────────────
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(8)

  // Respiro após a régua separadora. Sem este avanço, a próxima foto começava
  // apenas 1 mm abaixo da linha e o topo do texto ficava visualmente cortado.
  const ROW_SEPARATOR_GAP = 4

  for (const [itemIndex, item] of order.items.entries()) {
    const row = itemRows[itemIndex]
    // Bloco 79: localiza o produto pelo SKU para extrair os componentes do conjunto
    // (se houver) e calcula a altura da linha dinamicamente, evitando sobreposição
    // entre dimensões, observação, opcionais e a lista de componentes.
    const product = products.find((p) => p.product_code === item.product_code)
    const components = product?.components ?? []
    const isSetProduct = !!product && (product.is_set || isConjuntoType(product.type) || components.length > 0)
    // O conjunto é apenas o agregador. Suas dimensões pertencem aos componentes,
    // portanto nunca imprime a medida do item-pai, nem mesmo se houver valores legados.
    // Tapetes com medidas vendidas por área também ganham uma linha de dimensões,
    // pois o servidor informa a largura/profundidade em metros do item.
    const pieces = item.area_pieces ?? 1
    const hasRugDims = item.sold_by_area
      && (
        (item.area_width_m != null
          && item.area_depth_m != null
          && Number(item.area_width_m) > 0
          && Number(item.area_depth_m) > 0)
        || pieces > 1
      )
    const hasDims = !isSetProduct && (
      (!item.sold_by_area && (item.largura !== 0 || item.altura !== 0))
      || hasRugDims
    )
    const optSlots = orderOptionalSlots(item, locale === 'en-GB', catLabel)
    // O bloco textual vai de x=40 até a primeira coluna numérica (PRODUCT_TEXT_WIDTH,
    // medido acima). O rowH soma as linhas físicas reais para não colidir com
    // o próximo item.
    const dimText = hasDims
      ? item.sold_by_area
        ? `${L.dimensions}: ${formatRugSize(item.area_width_m, item.area_depth_m, item.qty, measurementLocale, pieces)}`
        : `${L.dimensions}: ${formatDimensions(item, order.market_code, measurementLocale)}`
      : null
    const obsText = item.observacao ? `${L.itemNote}: ${item.observacao}` : null
    const commentText = item.comment ? `${L.itemComment}: ${item.comment}` : null
    const optText = optSlots.length > 0 ? L.options + ': ' + optSlots.map((s) => `${s.label}: ${s.value}`).join(', ') : null

    const dimLines: string[] = dimText ? doc.splitTextToSize(dimText, PRODUCT_TEXT_WIDTH) : []
    const obsLines: string[] = obsText ? doc.splitTextToSize(obsText, PRODUCT_TEXT_WIDTH) : []
    const commentLines: string[] = commentText ? doc.splitTextToSize(commentText, PRODUCT_TEXT_WIDTH) : []
    const optLines: string[] = optText ? doc.splitTextToSize(optText, PRODUCT_TEXT_WIDTH) : []
    const compLineGroups: string[][] = components.map((comp) => {
      const compDim = formatDimensions(comp, order.market_code, measurementLocale)
      // Acabamentos do componente ("Alumínio: Taupe, Teka: Polywood") — mesma
      // informação exibida no carrinho; sem ela o PDF omitia os acabamentos
      // dos itens internos de um conjunto.
      const compCats = Array.from(new Set(comp.optionals.map((o) => o.category)))
      const finishes = compCats
        .map((cat) => `${optionalCategoryLabel(catLabel(cat), locale === 'en-GB')}: ${optionalName(comp.optionals.find((o) => o.category === cat)!.color_name, locale === 'en-GB')}`)
        .join(', ')
      const suffix = finishes ? ` - ${finishes}` : ''
      return doc.splitTextToSize(`• ${comp.qty}x ${comp.description} (${compDim})${suffix}`, PRODUCT_TEXT_WIDTH)
    })
    const compLinesTotal = compLineGroups.reduce((sum, lines) => sum + lines.length, 0)

    // O nome usa o mesmo limite e quebra antes da zona de segurança da QTD.
    const descLines: string[] = doc.splitTextToSize(item.description, PRODUCT_TEXT_WIDTH)
    const titleExtraLines = Math.max(0, descLines.length - 1)

    const extraLines = titleExtraLines + dimLines.length + obsLines.length + commentLines.length + optLines.length + compLinesTotal
    // Base 18 (antes 13) e mínimo 26 (antes 20): respiro vertical maior entre
    // os itens da tabela, a pedido do usuário — a foto tem 14mm, então o
    // conteúdo não colide com a régua separadora.
    const rowH = Math.max(26, 18 + extraLines * 4)
    if (y + rowH > 265) {
      doc.addPage()
      y = drawTableHeader(drawContinuationHeader())
    }

    // Foto (box 14×14mm, x=22 — imagem proporcional e centralizada dentro do box, sem distorcer)
    const photo = photoMap[item.product_code]
    if (photo) {
      try {
        const box = containBox(photo.width, photo.height, 14)
        doc.addImage(photo.b64, photo.format, 22 + box.dx, y - 1 + box.dy, box.w, box.h, undefined, 'FAST')
      } catch { /* foto inválida — ignora */ }
    } else {
      doc.setDrawColor(...LINE)
      doc.setLineWidth(0.2)
      doc.rect(22, y - 1, 14, 14)
      doc.setFontSize(5)
      doc.setTextColor(...MUTED)
      doc.text(L.noPhoto, 29, y + 5, { align: 'center' })
    }

    // Nome do produto — todas as linhas quebradas são impressas (não só a 1ª)
    doc.setTextColor(...DARK)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(8.5)
    let nameY = y
    for (const line of descLines) { doc.text(line, 40, nameY); nameY += 4 }

    // Código
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(6.5)
    doc.setTextColor(...MUTED)
    doc.text(item.product_code, 40, nameY + 0.5)

    // Linhas empilhadas abaixo do código: dimensões, observação, opcionais e
    // componentes do conjunto — cada uma quebrada em até 80mm (Bloco 82) e
    // reservando seu próprio espaço vertical linha a linha.
    let lineY = nameY + 4.5

    if (dimLines.length > 0) {
      doc.setFontSize(7)
      doc.setTextColor(...MUTED)
      for (const line of dimLines) { doc.text(line, 40, lineY); lineY += 4 }
    }

    if (obsLines.length > 0) {
      doc.setFontSize(6)
      doc.setTextColor(...MUTED)
      for (const line of obsLines) { doc.text(line, 40, lineY); lineY += 4 }
    }

    if (commentLines.length > 0) {
      doc.setFontSize(6.5)
      doc.setTextColor(...MUTED)
      for (const line of commentLines) { doc.text(line, 40, lineY); lineY += 4 }
    }

    if (optLines.length > 0) {
      doc.setFontSize(6.5)
      doc.setTextColor(...MUTED)
      for (const line of optLines) { doc.text(line, 40, lineY); lineY += 4 }
    }

    if (compLineGroups.length > 0) {
      doc.setFontSize(6.5)
      doc.setTextColor(...MUTED)
      for (const lines of compLineGroups) {
        for (const line of lines) { doc.text(line, 40, lineY); lineY += 4 }
      }
    }

    // Colunas numéricas (posições e larguras medidas em `columns`)
    const rightOf = (key: ColumnKey) => columnByKey(key)!.right
    // Linha miúda abaixo do valor: "/m²" no tapete, peças, desconto por unidade.
    const SUB_LINE_OFFSET = 3.5
    const drawSub = (text: string, x: number) => {
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(6)
      doc.setTextColor(...MUTED)
      doc.text(text, x, y + SUB_LINE_OFFSET, { align: 'right' })
    }
    const drawMain = (text: string, x: number, size: number, style: 'normal' | 'bold', color: [number, number, number] = DARK) => {
      doc.setFont('helvetica', style)
      doc.setFontSize(size)
      doc.setTextColor(...color)
      doc.text(text, x, y, { align: 'right' })
    }

    drawMain(row.qtyText, rightOf('qty'), 8, 'normal')
    if (row.piecesText) drawSub(row.piecesText, rightOf('qty'))

    drawMain(row.baseText, rightOf('base'), 7.5, 'normal')
    if (item.sold_by_area) drawSub('/m²', rightOf('base'))

    drawMain(row.discountText, rightOf('discount'), 7.5, row.discount > 0 ? 'bold' : 'normal', row.discount > 0 ? accentColor : MUTED)
    if (row.discount > 0) drawSub(unitDiscountText(row.pricing.unitDiscount), rightOf('discount'))

    drawMain(row.netText, rightOf('net'), 7.5, 'normal')
    if (item.sold_by_area) drawSub('/m²', rightOf('net'))

    // Brasil mantém a coluna histórica de IPI; Portugal leva o IVA só no fecho.
    if (!taxOnTotal) {
      if (row.ipiRate > 0) drawMain(`${row.ipiRate}%`, rightOf('ipi'), 7.5, 'bold', accentColor)
      else drawMain('-', rightOf('ipi'), 7.5, 'normal', MUTED)
    }

    // Subtotal da linha (com IPI no Brasil, sem IVA em Portugal)
    drawMain(row.subtotalText, rightOf('subtotal'), 8, 'bold')

    // Linha separadora leve
    doc.setFont('helvetica', 'normal')
    y += rowH
    doc.setDrawColor(...LINE)
    doc.setLineWidth(0.1)
    doc.line(20, y - 2, w - 20, y - 2)
    y += ROW_SEPARATOR_GAP
  }

  // ── Rodapé de totais ───────────────────────────────────────────────────────
  const totalItems = order.items.reduce((sum, item) => sum + (item.sold_by_area ? 0 : item.qty), 0)
  // Reserva o bloco de totais + assinaturas. A área do tapete permanece apenas
  // na linha do produto e não gera um total separado no resumo. Em Portugal
  // entram mais duas linhas (Subtotal e IVA) antes do total.
  const showTaxBreakdown = taxOnTotal && Number(order.total_ipi) > 0
  if (y + 59 + (showTaxBreakdown ? 16 : 0) > 278) {
    doc.addPage()
    y = drawContinuationHeader()
  }
  y += 4
  doc.setDrawColor(...accentColor)
  doc.setLineWidth(0.5)
  doc.line(20, y, w - 20, y)
  y += 8

  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.setFont('helvetica', 'normal')
  doc.text(L.totalItems, 148, y, { align: 'right' })
  doc.setFont('helvetica', 'bold')
  doc.text(String(totalItems), 186, y, { align: 'right' })
  y += 8

  if (showTaxBreakdown) {
    doc.setFont('helvetica', 'normal')
    doc.text('Subtotal:', 148, y, { align: 'right' })
    doc.setFont('helvetica', 'bold')
    doc.text(formatMoney(Number(order.total_value), currency, locale), 186, y, { align: 'right' })
    y += 8
    doc.setFont('helvetica', 'normal')
    doc.text(`${taxLabel}:`, 148, y, { align: 'right' })
    doc.setFont('helvetica', 'bold')
    doc.text(formatMoney(Number(order.total_ipi), currency, locale), 186, y, { align: 'right' })
    y += 8
  }

  const finalTotal = Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)

  doc.setFontSize(12)
  doc.setTextColor(...accentColor)
  doc.setFont('helvetica', 'normal')
  doc.text(L.grandTotal, 148, y, { align: 'right' })
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(14)
  doc.text(formatMoney(finalTotal, currency, locale), 186, y, { align: 'right' })
  y += 10

  // ── Observações ────────────────────────────────────────────────────────────
  if (order.notes) {
    doc.setDrawColor(...LINE)
    doc.setLineWidth(0.3)
    doc.line(20, y, w - 20, y)
    y += 6
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'bold')
    doc.text(L.notes, 24, y)
    y += 5
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8)
    doc.setTextColor(...DARK)
    const obsLines = doc.splitTextToSize(order.notes, w - 48)
    doc.text(obsLines, 24, y)
    y += obsLines.length * 4 + 3
  }

  // ── Bloco de assinaturas dupla (representante + cliente) ──────────────────
  // O PDF mantém apenas as linhas em branco para assinatura manual.

  // O bloco ocupa 29 mm até ao fim das legendas e o rodapé começa em 282 mm.
  // Usa a área útil inteira para não isolar assinaturas numa página em branco.
  if (y + 31 > 278) { doc.addPage(); y = 20 }
  y += 4
  doc.setDrawColor(...LINE)
  doc.setLineWidth(0.3)
  doc.line(20, y, w - 20, y)
  y += 6

  const colW = (w - 50) / 2

  // Coluna esquerda: assinatura do representante
  doc.setDrawColor(...DARK)
  doc.setLineWidth(0.3)
  doc.line(20, y + 14, 20 + colW, y + 14)
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'normal')
  doc.text(L.repSignature, 20 + colW / 2, y + 19, { align: 'center' })

  // Coluna direita: assinatura do cliente
  const sx = 20 + colW + 10
  doc.setDrawColor(...DARK)
  doc.setLineWidth(0.3)
  doc.line(sx, y + 14, sx + colW, y + 14)
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.text(L.clientSignature, sx + colW / 2, y + 19, { align: 'center' })

  y += 24

  // ── Rodapé em todas as páginas ─────────────────────────────────────────────
  const totalPages = doc.getNumberOfPages()
  for (let page = 1; page <= totalPages; page += 1) {
    doc.setPage(page)
    doc.setDrawColor(...accentColor)
    doc.setLineWidth(0.3)
    doc.line(20, 282, w - 20, 282)
    doc.setFontSize(6.5)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'normal')
    const legalFooter = seller
      ? `${seller.legalName} · ${seller.taxIdLabel} ${seller.taxId} · ${seller.addressLines[1]}`
      : L.footer
    doc.text(legalFooter, 20, 287)
    doc.text(`${L.page} ${page}/${totalPages}`, w - 20, 287, { align: 'right' })
    doc.setFontSize(6)
    doc.text(L.commercialNotice, 20, 291)
  }

  return doc
}

export async function generateOrderPDF(
  order: Order,
  client: Client,
  rep: Representative | null,
  products: Product[],
  catLabel: (code: string) => string = (c) => c,
  documentLocale?: 'pt-PT' | 'en-GB',
  // Pasta escolhida pelo usuário (resolvida no clique). Sem ela, vai para Downloads.
  destination?: PdfDestination | null,
): Promise<PdfSaveResult> {
  const doc = await buildOrderPdf({
    order,
    client,
    rep,
    products,
    catLabel,
    documentLocale,
  })

  // ── Salva ──────────────────────────────────────────────────────────────────
  const filename = `${order.code}_${client.name.replace(/\s+/g, '_')}.pdf`
  return savePdf(doc, filename, destination)
}
