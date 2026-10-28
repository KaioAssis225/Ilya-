import { optionalName, optionalCategoryLabel } from './optionalLabels'
import jsPDF from 'jspdf'
import type { Order, Client, Representative, Product } from '../types'
import { formatDimensions } from './measurements'
import { resolveOrderDocument } from './orderPresentation'
import { isConjuntoType } from './productType'
import { orderOptionalSlots } from './optionalApplications'
import { formatArea } from './areaProduct'

// ── Colors (idênticos ao protótipo) ──────────────────────────────────────────
const GOLD: [number, number, number] = [139, 105, 20]
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

// A Helvetica embutida do jsPDF só cobre WinAnsi: o "″" das polegadas (EU)
// forçava a linha inteira para UTF-16 e as dimensões saíam ilegíveis.
function pdfSafe(text: string): string {
  return text.replace(/″/g, '"')
}

function formatMoney(value: number, currency: string, locale: string): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value)
}

type AddressParty = Pick<Client, 'address' | 'numero' | 'city' | 'state' | 'country' | 'region' | 'cep'>

function formatAddress(person: AddressParty, market: 'BR' | 'EU'): string {
  const street = `${person.address}${person.numero ? `, ${person.numero}` : ''}`
  if (market === 'BR') {
    const cityState = [person.city, person.state].filter(Boolean).join('/')
    return [street, cityState, person.cep].filter(Boolean).join(' — ')
  }
  const locality = [person.cep, person.city].filter(Boolean).join(' ')
  const regionCountry = [person.region, person.country].filter(Boolean).join(', ')
  return [street, locality, regionCountry].filter(Boolean).join(' — ')
}

// ── Gerador principal ─────────────────────────────────────────────────────────
export async function generateOrderPDF(
  order: Order,
  client: Client,
  rep: Representative | null,
  products: Product[],
  catLabel: (code: string) => string = (c) => c,
  documentLocale?: 'pt-PT' | 'en-GB',
): Promise<void> {
  const doc = new jsPDF('p', 'mm', 'a4')
  // Moeda, locale e rótulo saem do snapshot do pedido (ver orderPresentation):
  // um pedido antigo precisa imprimir o tributo com que foi contratado, não o
  // do mercado em que o usuário está agora.
  const orderDocument = resolveOrderDocument(documentLocale ? { ...order, locale: documentLocale } : order)
  const { currency, locale, taxLabel, brand, brandSuffix, brandDescriptor, labels: L, seller } = orderDocument
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

  // ── Linha dourada superior ──────────────────────────────────────────────────
  doc.setDrawColor(...GOLD)
  doc.setLineWidth(0.5)
  doc.line(20, y, w - 20, y)
  y += 8

  // ── Logo ILYA / IBTW ───────────────────────────────────────────────────────
  doc.setTextColor(...GOLD)
  if (brandSuffix && brandDescriptor) {
    // Portugal: assinatura visual em duas linhas, seguindo o logo oficial.
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(32)
    doc.text(brand, 20, y)

    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8.5)
    doc.text(`${brandDescriptor} ${brandSuffix.replace(/\.$/, '')}`, 20, y + 10, {
      charSpace: 1.6,
    })
  } else {
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(28)
    doc.text(brand, 20, y)
  }

  doc.setDrawColor(...GOLD)
  doc.setLineWidth(0.3)
  const logoRuleY = brandSuffix && brandDescriptor ? y + 15 : y + 5
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
  doc.setTextColor(...GOLD)
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

  y = brandSuffix && brandDescriptor ? 60 : 55

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

  const drawTableHeader = (top: number): number => {
    doc.setDrawColor(...LINE)
    doc.setLineWidth(0.3)
    doc.line(20, top, w - 20, top)
    const labelY = top + 8
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'bold')
    doc.text(L.product, 22, labelY)
    doc.text(L.qty, 125, labelY, { align: 'right' })
    doc.text(L.unitPrice, 150, labelY, { align: 'right' })
    doc.text(taxLabel, 167, labelY, { align: 'right' })
    doc.text(L.total, 186, labelY, { align: 'right' })
    doc.setDrawColor(...LINE)
    doc.line(20, labelY + 4, w - 20, labelY + 4)
    return labelY + 11
  }

  const drawContinuationHeader = (): number => {
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(13)
    doc.setTextColor(...GOLD)
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

  const measurementLocale = locale === 'en-GB' ? 'en-GB' : order.market_code === 'EU' ? 'pt-PT' : 'pt-BR'
  // Respiro após a régua separadora. Sem este avanço, a próxima foto começava
  // apenas 1 mm abaixo da linha e o topo do texto ficava visualmente cortado.
  const ROW_SEPARATOR_GAP = 4

  for (const item of order.items) {
    // Bloco 79: localiza o produto pelo SKU para extrair os componentes do conjunto
    // (se houver) e calcula a altura da linha dinamicamente, evitando sobreposição
    // entre dimensões, observação, opcionais e a lista de componentes.
    const product = products.find((p) => p.product_code === item.product_code)
    const components = product?.components ?? []
    const isSetProduct = !!product && (product.is_set || isConjuntoType(product.type) || components.length > 0)
    // O conjunto é apenas o agregador. Suas dimensões pertencem aos componentes,
    // portanto nunca imprime a medida do item-pai, nem mesmo se houver valores legados.
    const hasDims = !item.sold_by_area && !isSetProduct && (item.largura !== 0 || item.altura !== 0)
    const optSlots = orderOptionalSlots(item, locale === 'en-GB', catLabel)
    // Bloco 82: quebra de linha (80mm) para textos longos de opcionais, observação
    // e componentes — o rowH soma as linhas físicas reais para não colidir com a
    // próxima linha da tabela nem com as colunas numéricas (QTD/VALOR/IPI/TOTAL).
    const WRAP_WIDTH = 80
    const dimText = hasDims
      ? `${L.dimensions}: ${pdfSafe(formatDimensions(item, order.market_code, measurementLocale))}`
      : null
    const obsText = item.observacao ? `${L.itemNote}: ${item.observacao}` : null
    const commentText = item.comment ? `${L.itemComment}: ${item.comment}` : null
    const optText = optSlots.length > 0 ? L.options + ': ' + optSlots.map((s) => `${s.label}: ${s.value}`).join(', ') : null

    const dimLines: string[] = dimText ? doc.splitTextToSize(dimText, WRAP_WIDTH) : []
    const obsLines: string[] = obsText ? doc.splitTextToSize(obsText, WRAP_WIDTH) : []
    const commentLines: string[] = commentText ? doc.splitTextToSize(commentText, WRAP_WIDTH) : []
    const optLines: string[] = optText ? doc.splitTextToSize(optText, WRAP_WIDTH) : []
    const compLineGroups: string[][] = components.map((comp) => {
      const compDim = pdfSafe(formatDimensions(comp, order.market_code, measurementLocale))
      // Acabamentos do componente ("Alumínio: Taupe, Teka: Polywood") — mesma
      // informação exibida no carrinho; sem ela o PDF omitia os acabamentos
      // dos itens internos de um conjunto.
      const compCats = Array.from(new Set(comp.optionals.map((o) => o.category)))
      const finishes = compCats
        .map((cat) => `${optionalCategoryLabel(catLabel(cat), locale === 'en-GB')}: ${optionalName(comp.optionals.find((o) => o.category === cat)!.color_name, locale === 'en-GB')}`)
        .join(', ')
      const suffix = finishes ? ` — ${finishes}` : ''
      return doc.splitTextToSize(`• ${comp.qty}x ${comp.description} (${compDim})${suffix}`, WRAP_WIDTH)
    })
    const compLinesTotal = compLineGroups.reduce((sum, lines) => sum + lines.length, 0)

    // Nome do produto: também quebrado em WRAP_WIDTH (o espaço real até a coluna
    // QTD é ~85mm a partir de x=40) — antes usava 95mm e a 1ª linha invadia o
    // valor unitário em nomes longos. Agora todas as linhas são impressas.
    const descLines: string[] = doc.splitTextToSize(item.description, WRAP_WIDTH)
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

    // Colunas numéricas
    const unitPrice = Number(item.unit_price)
    const discount = Number(item.discount || 0)
    const ipiRate = Number(item.ipi_rate || 0)
    const effectivePrice = unitPrice * (1 - discount / 100)
    const subtotalWithIpi = effectivePrice * item.qty * (1 + ipiRate / 100)

    doc.setTextColor(...DARK)
    doc.setFontSize(8)
    doc.setFont('helvetica', 'normal')
    doc.text(item.sold_by_area ? formatArea(item.qty, locale) : String(item.qty), 125, y, { align: 'right' })

    // Valor unitário (com desconto se houver)
    if (discount > 0) {
      doc.setFontSize(6)
      doc.setTextColor(...MUTED)
      doc.text(formatMoney(unitPrice, currency, locale), 150, y - 2, { align: 'right' })
      doc.setFontSize(7.5)
      doc.setTextColor(...DARK)
      doc.text(formatMoney(effectivePrice, currency, locale), 150, y + 2.5, { align: 'right' })
      doc.setFontSize(5.5)
      doc.setTextColor(...MUTED)
      doc.text(`-${discount}%`, 150, y + 6.5, { align: 'right' })
    } else {
      doc.text(formatMoney(unitPrice, currency, locale), 150, y, { align: 'right' })
    }

    // IPI %
    if (ipiRate > 0) {
      doc.setFontSize(7.5)
      doc.setTextColor(...GOLD)
      doc.setFont('helvetica', 'bold')
      doc.text(`${ipiRate}%`, 167, y, { align: 'right' })
    } else {
      doc.setFontSize(7.5)
      doc.setTextColor(...MUTED)
      doc.setFont('helvetica', 'normal')
      doc.text('—', 167, y, { align: 'right' })
    }

    // Total com IPI
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(8)
    doc.setTextColor(...DARK)
    doc.text(formatMoney(subtotalWithIpi, currency, locale), 186, y, { align: 'right' })

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
  const totalArea = order.items.reduce((sum, item) => sum + (item.sold_by_area ? item.qty : 0), 0)
  // Reserva o bloco de totais + assinaturas. Com área há uma linha extra de
  // 8 mm; a assinatura compacta abaixo mantém pedidos curtos numa só página.
  if (y + (totalArea > 0 ? 67 : 59) > 278) {
    doc.addPage()
    y = drawContinuationHeader()
  }
  y += 4
  doc.setDrawColor(...GOLD)
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

  if (totalArea > 0) {
    doc.setFont('helvetica', 'normal')
    doc.text(L.totalArea, 148, y, { align: 'right' })
    doc.setFont('helvetica', 'bold')
    doc.text(formatArea(totalArea, locale), 186, y, { align: 'right' })
    y += 8
  }

  const finalTotal = Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)

  doc.setFontSize(12)
  doc.setTextColor(...GOLD)
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
    doc.setDrawColor(...GOLD)
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

  // ── Salva ──────────────────────────────────────────────────────────────────
  const filename = `${order.code}_${client.name.replace(/\s+/g, '_')}.pdf`
  doc.save(filename)
}
