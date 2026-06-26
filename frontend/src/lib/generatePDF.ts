import jsPDF from 'jspdf'
import type { Order, Client, Representative, Product } from '../types'

// ── Colors (idênticos ao protótipo) ──────────────────────────────────────────
const GOLD: [number, number, number] = [139, 105, 20]
const DARK: [number, number, number] = [44, 36, 32]
const MUTED: [number, number, number] = [138, 126, 114]
const LIGHT: [number, number, number] = [245, 240, 235]
const LINE: [number, number, number] = [232, 224, 214]

// ── Swatch colors para opcionais ──────────────────────────────────────────────
const SWATCH: Record<string, [number, number, number]> = {
  camomila:      [232, 213, 160],
  canela:        [196, 120, 60],
  areia:         [200, 170, 130],
  taupe:         [158, 141, 126],
  natural:       [220, 210, 195],
  grafite:       [100, 100, 100],
  escovado:      [180, 180, 175],
  preto:         [30, 30, 30],
  'pátina':      [168, 148, 118],
  'óleo natural': [195, 165, 120],
  'carvão':      [60, 50, 40],
  caramelo:      [185, 120, 65],
  palha:         [228, 205, 150],
  'arara azul':  [50, 100, 175],
  cidreira:      [190, 195, 90],
}

// ── Carrega imagem de URL para base64 via canvas ──────────────────────────────
async function urlToBase64(url: string): Promise<string | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = img.naturalWidth
        canvas.height = img.naturalHeight
        const ctx = canvas.getContext('2d')!
        ctx.drawImage(img, 0, 0)
        resolve(canvas.toDataURL('image/jpeg', 0.85))
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

// ── Desenha swatch + label de opcional ───────────────────────────────────────
function drawSwatch(
  doc: jsPDF,
  label: string,
  x: number,
  y: number,
): number {
  const key = label.toLowerCase()
  const color = SWATCH[key]
  if (color) {
    doc.setFillColor(...color)
    doc.rect(x, y - 2.5, 3, 3, 'F')
    doc.setDrawColor(...LINE)
    doc.setLineWidth(0.1)
    doc.rect(x, y - 2.5, 3, 3)
    doc.setTextColor(...DARK)
    doc.setFontSize(6.5)
    doc.text(label, x + 4, y)
    return 4 + doc.getTextWidth(label) + 3
  } else {
    doc.setTextColor(...MUTED)
    doc.setFontSize(6.5)
    doc.text(label, x, y)
    return doc.getTextWidth(label) + 2
  }
}

// ── Gerador principal ─────────────────────────────────────────────────────────
export async function generateOrderPDF(
  order: Order,
  client: Client,
  rep: Representative | null,
  products: Product[],
): Promise<void> {
  const doc = new jsPDF('p', 'mm', 'a4')
  const w = doc.internal.pageSize.getWidth()

  // Pré-carrega fotos de todos os itens (paralelo)
  const photoMap: Record<string, string> = {}
  await Promise.all(
    order.items.map(async (item) => {
      const product = products.find((p) => p.product_code === item.product_code)
      if (product?.photo_url) {
        const b64 = await urlToBase64(product.photo_url)
        if (b64) photoMap[item.product_code] = b64
      }
    }),
  )

  let y = 20

  // ── Linha dourada superior ──────────────────────────────────────────────────
  doc.setDrawColor(...GOLD)
  doc.setLineWidth(0.5)
  doc.line(20, y, w - 20, y)
  y += 8

  // ── Logo ILYA ──────────────────────────────────────────────────────────────
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(28)
  doc.setTextColor(...GOLD)
  doc.text('ILYA', 20, y)
  y += 5

  doc.setFontSize(8)
  doc.setTextColor(...MUTED)
  doc.text('Ilya — Móveis & Estofados', 20, y)
  y += 3

  doc.setDrawColor(...GOLD)
  doc.setLineWidth(0.3)
  doc.line(20, y, 60, y)

  // ── Número do pedido (canto direito) ───────────────────────────────────────
  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.setFont('helvetica', 'bold')
  doc.text('PEDIDO', w - 20, 28, { align: 'right' })

  doc.setFont('helvetica', 'normal')
  doc.setFontSize(14)
  doc.setTextColor(...GOLD)
  doc.text(order.code, w - 20, 35, { align: 'right' })

  doc.setFontSize(8)
  doc.setTextColor(...MUTED)
  doc.text(
    'Data: ' + new Date(order.created_at).toLocaleDateString('pt-BR'),
    w - 20,
    42,
    { align: 'right' },
  )
  doc.text('Orçamento: ' + order.orc_id, w - 20, 47, { align: 'right' })

  y = 55

  // ── Boxes cliente + representante ──────────────────────────────────────────
  const boxW = (w - 50) / 2
  doc.setFillColor(...LIGHT)
  doc.roundedRect(20, y, boxW, 32, 2, 2, 'F')
  doc.roundedRect(20 + boxW + 10, y, boxW, 32, 2, 2, 'F')

  const bx = 24
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text('CLIENTE', bx, y + 6)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.text(client.name, bx, y + 12)
  doc.setFontSize(8)
  doc.setTextColor(...MUTED)
  doc.text(client.phone, bx, y + 17)
  doc.text(client.email, bx, y + 22)
  const clientAddr = `${client.address}${client.numero ? ', ' + client.numero : ''} — ${client.city}/${client.state}`
  doc.text(doc.splitTextToSize(clientAddr, boxW - 8)[0], bx, y + 27)

  const rx = 20 + boxW + 14
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text('REPRESENTANTE', rx, y + 6)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.text(rep ? rep.name : 'Nenhum', rx, y + 12)
  if (rep) {
    doc.setFontSize(8)
    doc.setTextColor(...MUTED)
    doc.text(rep.phone, rx, y + 17)
    doc.text(rep.email, rx, y + 22)
    const repAddr = `${rep.address}${rep.numero ? ', ' + rep.numero : ''} — ${rep.city}/${rep.state}`
    doc.text(doc.splitTextToSize(repAddr, boxW - 8)[0], rx, y + 27)
  }

  y += 42

  // ── Cabeçalho da tabela de itens ───────────────────────────────────────────
  doc.setDrawColor(...LINE)
  doc.setLineWidth(0.3)
  doc.line(20, y, w - 20, y)
  y += 8

  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text('PRODUTO', 24, y)
  doc.text('FOTO', 82, y)
  doc.text('DIM. (cm)', 96, y)
  doc.text('OPCIONAIS', 127, y)
  doc.text('QTD', 158, y)
  doc.text('VALOR UN.', 166, y)
  doc.text('TOTAL', w - 24, y, { align: 'right' })

  y += 4
  doc.setDrawColor(...LINE)
  doc.line(20, y, w - 20, y)
  y += 7

  // ── Linhas de itens ────────────────────────────────────────────────────────
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(8)

  for (const item of order.items) {
    const optCount = [item.opt_aluminio, item.opt_madeira, item.opt_tecido, item.opt_couro, item.opt_corda].filter(Boolean).length
    const rowH = Math.max(14, 6 + optCount * 3.5)
    if (y + rowH > 265) {
      doc.addPage()
      y = 20
    }

    // Descrição + código
    doc.setTextColor(...DARK)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(8)
    const descLines = doc.splitTextToSize(item.description, 54)
    doc.text(descLines[0], 24, y)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(6.5)
    doc.setTextColor(...MUTED)
    doc.text(item.product_code, 24, y + 4)

    // Foto do produto
    const b64 = photoMap[item.product_code]
    if (b64) {
      try {
        doc.addImage(b64, 'JPEG', 82, y - 3, 11, 11)
      } catch { /* foto inválida — ignora */ }
    } else {
      doc.setDrawColor(...LINE)
      doc.setLineWidth(0.2)
      doc.rect(82, y - 3, 11, 11)
      doc.setFontSize(5)
      doc.setTextColor(...MUTED)
      doc.text('sem foto', 83, y + 3)
    }

    // Dimensões
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    const dimText = item.is_circular
      ? `Ø ${item.largura} × A ${item.altura}`
      : `L ${item.largura} × P ${item.profundidade} × A ${item.altura}`
    doc.text(dimText, 96, y)

    // Opcionais com swatches
    const optSlots: { prefix: string; value: string }[] = []
    if (item.opt_aluminio) optSlots.push({ prefix: 'Al', value: item.opt_aluminio })
    if (item.opt_madeira) {
      const slash = item.opt_madeira.indexOf('/')
      const color = slash !== -1 ? item.opt_madeira.slice(slash + 1) : item.opt_madeira
      const prefix = item.opt_madeira.startsWith('madeira_teka') ? 'Tk' : 'Fr'
      optSlots.push({ prefix, value: color })
    }
    if (item.opt_tecido) {
      const slash = item.opt_tecido.indexOf('/')
      const color = slash !== -1 ? item.opt_tecido.slice(slash + 1) : item.opt_tecido
      const prefix = item.opt_tecido.startsWith('tecido_faixa_1') ? 'F1' : item.opt_tecido.startsWith('tecido_faixa_2') ? 'F2' : 'Tc'
      optSlots.push({ prefix, value: color })
    }
    if (item.opt_couro) {
      const slash = item.opt_couro.indexOf('/')
      const color = slash !== -1 ? item.opt_couro.slice(slash + 1) : item.opt_couro
      const prefix = item.opt_couro.startsWith('couro_pele') ? 'Cp' : 'Cs'
      optSlots.push({ prefix, value: color })
    }
    if (item.opt_corda) optSlots.push({ prefix: 'Co', value: item.opt_corda })

    optSlots.forEach((slot, idx) => {
      const sy = y + idx * 3.5
      let sx = 127
      doc.setFontSize(6.5)
      doc.setTextColor(...MUTED)
      doc.text(`${slot.prefix}:`, sx, sy)
      sx += doc.getTextWidth(`${slot.prefix}:`) + 1
      drawSwatch(doc, slot.value, sx, sy)
    })

    // Qtd + valores
    doc.setTextColor(...DARK)
    doc.setFontSize(8)
    doc.setFont('helvetica', 'normal')
    doc.text(String(item.qty), 161, y)

    const unitPrice = Number(item.unit_price)
    const subtotal = unitPrice * item.qty
    doc.text('R$ ' + unitPrice.toFixed(2).replace('.', ','), 166, y)

    doc.setFont('helvetica', 'bold')
    doc.text('R$ ' + subtotal.toFixed(2).replace('.', ','), w - 24, y, { align: 'right' })

    // Linha separadora leve
    doc.setFont('helvetica', 'normal')
    y += rowH
    doc.setDrawColor(...LINE)
    doc.setLineWidth(0.1)
    doc.line(20, y - 2, w - 20, y - 2)
  }

  // ── Rodapé de totais ───────────────────────────────────────────────────────
  y += 4
  doc.setDrawColor(...GOLD)
  doc.setLineWidth(0.5)
  doc.line(20, y, w - 20, y)
  y += 8

  const totalItems = order.items.reduce((s, i) => s + i.qty, 0)

  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.setFont('helvetica', 'normal')
  doc.text('Total de Itens:', w - 70, y)
  doc.setFont('helvetica', 'bold')
  doc.text(String(totalItems), w - 24, y, { align: 'right' })
  y += 8

  doc.setFontSize(12)
  doc.setTextColor(...GOLD)
  doc.setFont('helvetica', 'normal')
  doc.text('VALOR TOTAL:', w - 70, y)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(14)
  doc.text(
    'R$ ' + Number(order.total_value).toLocaleString('pt-BR', { minimumFractionDigits: 2 }),
    w - 24,
    y,
    { align: 'right' },
  )
  y += 12

  // ── Observações ────────────────────────────────────────────────────────────
  if (order.notes) {
    doc.setDrawColor(...LINE)
    doc.setLineWidth(0.3)
    doc.line(20, y, w - 20, y)
    y += 6
    doc.setFontSize(7)
    doc.setTextColor(...MUTED)
    doc.setFont('helvetica', 'bold')
    doc.text('OBSERVAÇÕES', 24, y)
    y += 5
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8)
    doc.setTextColor(...DARK)
    const obsLines = doc.splitTextToSize(order.notes, w - 48)
    doc.text(obsLines, 24, y)
  }

  // ── Rodapé da página ───────────────────────────────────────────────────────
  y = 285
  doc.setDrawColor(...GOLD)
  doc.setLineWidth(0.3)
  doc.line(20, y, w - 20, y)
  y += 5
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'normal')
  doc.text('Ilya — Documento gerado automaticamente', w / 2, y, { align: 'center' })

  // ── Salva ──────────────────────────────────────────────────────────────────
  const filename = `${order.code}_${client.name.replace(/\s+/g, '_')}.pdf`
  doc.save(filename)
}
