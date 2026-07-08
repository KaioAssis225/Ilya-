import jsPDF from 'jspdf'
import type { Order, Client, Representative, Product } from '../types'

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
}

async function urlToBase64(url: string): Promise<LoadedImage | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        const w = img.naturalWidth
        const h = img.naturalHeight
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d')!
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
        ctx.drawImage(img, 0, 0)
        resolve({ b64: canvas.toDataURL('image/png', 0.9), width: w, height: h })
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

// ── Calcula o retângulo proporcional (efeito object-contain) dentro de um box quadrado ──
function containBox(width: number, height: number, box: number): { w: number; h: number; dx: number; dy: number } {
  const ratio = width / height
  const w = ratio >= 1 ? box : box * ratio
  const h = ratio >= 1 ? box / ratio : box
  return { w, h, dx: (box - w) / 2, dy: (box - h) / 2 }
}

// ── Formatação monetária pt-BR ────────────────────────────────────────────────
function formatBRL(value: number): string {
  return 'R$ ' + value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ── Gerador principal ─────────────────────────────────────────────────────────
export async function generateOrderPDF(
  order: Order,
  client: Client,
  rep: Representative | null,
  products: Product[],
  catLabel: (code: string) => string = (c) => c,
): Promise<void> {
  const doc = new jsPDF('p', 'mm', 'a4')
  const w = doc.internal.pageSize.getWidth()

  // Pré-carrega fotos de todos os itens (paralelo)
  const photoMap: Record<string, LoadedImage> = {}
  await Promise.all(
    order.items.map(async (item) => {
      const product = products.find((p) => p.product_code === item.product_code)
      if (product?.photo_url) {
        const photo = await urlToBase64(product.photo_url)
        if (photo) photoMap[item.product_code] = photo
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
  doc.roundedRect(20, y, boxW, 35, 2, 2, 'F')
  doc.roundedRect(20 + boxW + 10, y, boxW, 35, 2, 2, 'F')

  // Esquerda: Representante
  const bx = 24
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text('REPRESENTANTE', bx, y + 6)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.text(rep ? rep.name : 'Nenhum', bx, y + 12)
  if (rep) {
    doc.setFontSize(8)
    doc.setTextColor(...MUTED)
    doc.text(rep.phone, bx, y + 17)
    doc.text(rep.email, bx, y + 22)
    const repAddr = `${rep.address}${rep.numero ? ', ' + rep.numero : ''} — ${rep.city}/${rep.state}`
    doc.text(doc.splitTextToSize(repAddr, boxW - 8).slice(0, 2), bx, y + 27)
  }

  // Direita: Cliente
  const rx = 20 + boxW + 14
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text('CLIENTE', rx, y + 6)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.setTextColor(...DARK)
  doc.text(client.name, rx, y + 12)
  doc.setFontSize(8)
  doc.setTextColor(...MUTED)
  doc.text(client.phone, rx, y + 17)
  doc.text(client.email, rx, y + 22)
  const clientAddr = `${client.address}${client.numero ? ', ' + client.numero : ''} — ${client.city}/${client.state}`
  doc.text(doc.splitTextToSize(clientAddr, boxW - 8).slice(0, 2), rx, y + 27)

  y += 42

  // ── Cabeçalho da tabela de itens ───────────────────────────────────────────
  doc.setDrawColor(...LINE)
  doc.setLineWidth(0.3)
  doc.line(20, y, w - 20, y)
  y += 8

  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'bold')
  doc.text('PRODUTO', 22, y)
  doc.text('QTD', 125, y, { align: 'right' })
  doc.text('VALOR UN.', 150, y, { align: 'right' })
  doc.text('IPI', 167, y, { align: 'right' })
  doc.text('TOTAL', 186, y, { align: 'right' })

  y += 4
  doc.setDrawColor(...LINE)
  doc.line(20, y, w - 20, y)
  y += 7

  // ── Linhas de itens ────────────────────────────────────────────────────────
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(8)

  const fmtM = (v: number) => Number(v).toFixed(2).replace('.', ',')

  for (const item of order.items) {
    // Bloco 79: localiza o produto pelo SKU para extrair os componentes do conjunto
    // (se houver) e calcula a altura da linha dinamicamente, evitando sobreposição
    // entre dimensões, observação, opcionais e a lista de componentes.
    const product = products.find((p) => p.product_code === item.product_code)
    const components = product?.components ?? []
    const hasDims = item.largura !== 0 || item.altura !== 0
    const optSlots = Object.entries(item.opt_categories ?? {}).map(([cat, value]) => ({
      label: catLabel(cat),
      value,
    }))
    const extraLines = (hasDims ? 1 : 0) + (item.observacao ? 1 : 0) + (optSlots.length > 0 ? 1 : 0) + components.length
    const rowH = Math.max(20, 13 + extraLines * 4)
    if (y + rowH > 265) {
      doc.addPage()
      y = 20
    }

    // Foto (box 14×14mm, x=22 — imagem proporcional e centralizada dentro do box, sem distorcer)
    const photo = photoMap[item.product_code]
    if (photo) {
      try {
        const box = containBox(photo.width, photo.height, 14)
        doc.addImage(photo.b64, 'PNG', 22 + box.dx, y - 1 + box.dy, box.w, box.h)
      } catch { /* foto inválida — ignora */ }
    } else {
      doc.setDrawColor(...LINE)
      doc.setLineWidth(0.2)
      doc.rect(22, y - 1, 14, 14)
      doc.setFontSize(5)
      doc.setTextColor(...MUTED)
      doc.text('sem\nfoto', 29, y + 5, { align: 'center' })
    }

    // Nome do produto
    doc.setTextColor(...DARK)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(8.5)
    const descLines = doc.splitTextToSize(item.description, 95)
    doc.text(descLines[0], 40, y)

    // Código
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(6.5)
    doc.setTextColor(...MUTED)
    doc.text(item.product_code, 40, y + 4.5)

    // Linhas empilhadas abaixo do código: dimensões, observação, opcionais e
    // componentes do conjunto — cada uma reserva seu próprio espaço vertical.
    let lineY = y + 8.5

    if (hasDims) {
      const dimRaw = item.is_circular
        ? `Ø ${fmtM(item.largura)} × A ${fmtM(item.altura)} m`
        : `L ${fmtM(item.largura)} × P ${fmtM(item.profundidade)} × A ${fmtM(item.altura)} m`
      doc.setFontSize(7)
      doc.setTextColor(...MUTED)
      doc.text(`Dimensões: ${dimRaw}`, 40, lineY)
      lineY += 4
    }

    // Observação técnica do produto
    if (item.observacao) {
      doc.setFontSize(6)
      doc.setTextColor(...MUTED)
      doc.text(`Obs.: ${item.observacao}`, 40, lineY)
      lineY += 4
    }

    // Opcionais — linha horizontal, uma entrada por categoria dinâmica do pedido
    if (optSlots.length > 0) {
      const optText = 'Opcionais: ' + optSlots.map((s) => `${s.label}: ${s.value}`).join(', ')
      doc.setFontSize(6.5)
      doc.setTextColor(...MUTED)
      doc.text(optText, 40, lineY)
      lineY += 4
    }

    // Componentes do conjunto — um marcador por item, com quantidade e dimensões
    if (components.length > 0) {
      doc.setFontSize(6.5)
      doc.setTextColor(...MUTED)
      for (const comp of components) {
        const compDim = comp.is_circular
          ? `Ø ${fmtM(comp.largura)} × A ${fmtM(comp.altura)} m`
          : `L ${fmtM(comp.largura)} × P ${fmtM(comp.profundidade)} × A ${fmtM(comp.altura)} m`
        doc.text(`• ${comp.qty}x ${comp.description} (${compDim})`, 40, lineY)
        lineY += 4
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
    doc.text(String(item.qty), 125, y, { align: 'right' })

    // Valor unitário (com desconto se houver)
    if (discount > 0) {
      doc.setFontSize(6)
      doc.setTextColor(...MUTED)
      doc.text(formatBRL(unitPrice), 150, y - 2, { align: 'right' })
      doc.setFontSize(7.5)
      doc.setTextColor(...DARK)
      doc.text(formatBRL(effectivePrice), 150, y + 2.5, { align: 'right' })
      doc.setFontSize(5.5)
      doc.setTextColor(...MUTED)
      doc.text(`-${discount}%`, 150, y + 6.5, { align: 'right' })
    } else {
      doc.text(formatBRL(unitPrice), 150, y, { align: 'right' })
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
    doc.text(formatBRL(subtotalWithIpi), 186, y, { align: 'right' })

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
  doc.text('Total de Itens:', 148, y, { align: 'right' })
  doc.setFont('helvetica', 'bold')
  doc.text(String(totalItems), 186, y, { align: 'right' })
  y += 8

  const finalTotal = Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)

  doc.setFontSize(12)
  doc.setTextColor(...GOLD)
  doc.setFont('helvetica', 'normal')
  doc.text('VALOR TOTAL:', 148, y, { align: 'right' })
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(14)
  doc.text(formatBRL(finalTotal), 186, y, { align: 'right' })
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
    doc.text('OBSERVAÇÕES', 24, y)
    y += 5
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8)
    doc.setTextColor(...DARK)
    const obsLines = doc.splitTextToSize(order.notes, w - 48)
    doc.text(obsLines, 24, y)
  }

  // ── Bloco de assinaturas dupla (representante + cliente) ──────────────────
  // Isolamento rígido: repSig nunca vaza para clientSig e vice-versa.
  const repSig = order.rep_signature
    || localStorage.getItem(`signature_rep_${order.code}`)

  const clientSig = order.client_signature
    || localStorage.getItem(`signature_cli_${order.code}`)

  if (y + 40 > 265) { doc.addPage(); y = 20 }
  y += 6
  doc.setDrawColor(...LINE)
  doc.setLineWidth(0.3)
  doc.line(20, y, w - 20, y)
  y += 8

  const colW = (w - 50) / 2

  // Coluna esquerda: assinatura do representante
  if (repSig) {
    try {
      doc.addImage(repSig, 'PNG', 20, y, colW, 20, undefined, 'FAST')
    } catch { /* assinatura inválida — ignora */ }
  }
  doc.setDrawColor(...DARK)
  doc.setLineWidth(0.3)
  doc.line(20, y + 20, 20 + colW, y + 20)
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.setFont('helvetica', 'normal')
  doc.text('Representante / Ilya', 20 + colW / 2, y + 25, { align: 'center' })

  // Coluna direita: assinatura do cliente
  const sx = 20 + colW + 10
  if (clientSig) {
    try {
      doc.addImage(clientSig, 'PNG', sx, y, colW, 20, undefined, 'FAST')
    } catch { /* assinatura inválida — ignora */ }
  }
  doc.setDrawColor(...DARK)
  doc.setLineWidth(0.3)
  doc.line(sx, y + 20, sx + colW, y + 20)
  doc.setFontSize(7)
  doc.setTextColor(...MUTED)
  doc.text('Cliente / Contratado', sx + colW / 2, y + 25, { align: 'center' })

  y += 30

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
