import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { authApi } from '../lib/api'
import { BrandLoadingOverlay } from '../components/BrandLoadingOverlay'

interface OrderInfo {
  order_code: string
  is_signed: boolean
  document_hash: string
  document: {
    document_version: number
    currency: string
    locale: string
    notes: string | null
    total_with_ipi: string
    items: Array<{
      product_code: string
      description: string
      altura: string
      largura: string
      profundidade: string
      observacao: string | null
      qty: number
      unit_price: string
      discount: string
      ipi_rate: string
      tax_label: string
      optionals: Record<string, string>
    }>
  }
}

type Stage = 'loading' | 'ready' | 'signing' | 'success' | 'error' | 'already_signed'

export default function SignContractPage() {
  const [token] = useState<string>(() => {
    // Token vem via fragment (#) para não vazar em logs de servidor nem Referer (V-04)
    return window.location.hash.slice(1)
  })

  const [stage, setStage] = useState<Stage>('loading')
  const [orderInfo, setOrderInfo] = useState<OrderInfo | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [acceptedTerms, setAcceptedTerms] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const isDrawingRef = useRef(false)

  useEffect(() => {
    window.history.replaceState(window.history.state, '', window.location.pathname)
  }, [])

  useEffect(() => {
    if (!token) {
      setErrorMsg('Token não fornecido.')
      setStage('error')
      return
    }
    // POST com token no body: querystring vazaria o token nos access logs (V-04b)
    authApi
      .post<OrderInfo>('/orders/verify-sign-token', { token })
      .then(r => {
        if (r.data.is_signed) {
          setOrderInfo(r.data)
          setStage('already_signed')
        } else {
          setOrderInfo(r.data)
          setStage('ready')
        }
      })
      .catch(() => {
        setErrorMsg('Token inválido ou expirado. Solicite um novo link ao seu representante.')
        setStage('error')
      })
  }, [token])

  useEffect(() => {
    if (stage !== 'ready' || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')!
    ctx.strokeStyle = '#2c2420'
    ctx.lineWidth = 2.5
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    function getXY(e: TouchEvent | MouseEvent) {
      const rect = canvas.getBoundingClientRect()
      const scaleX = canvas.width / rect.width
      const scaleY = canvas.height / rect.height
      if ('touches' in e) {
        return {
          x: (e.touches[0].clientX - rect.left) * scaleX,
          y: (e.touches[0].clientY - rect.top) * scaleY,
        }
      }
      return {
        x: ((e as MouseEvent).clientX - rect.left) * scaleX,
        y: ((e as MouseEvent).clientY - rect.top) * scaleY,
      }
    }

    function onStart(e: TouchEvent | MouseEvent) {
      e.preventDefault()
      isDrawingRef.current = true
      const { x, y } = getXY(e)
      ctx.beginPath()
      ctx.moveTo(x, y)
    }
    function onMove(e: TouchEvent | MouseEvent) {
      e.preventDefault()
      if (!isDrawingRef.current) return
      const { x, y } = getXY(e)
      ctx.lineTo(x, y)
      ctx.stroke()
    }
    function onEnd() { isDrawingRef.current = false }

    canvas.addEventListener('mousedown', onStart)
    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mouseup', onEnd)
    canvas.addEventListener('mouseleave', onEnd)
    canvas.addEventListener('touchstart', onStart, { passive: false })
    canvas.addEventListener('touchmove', onMove, { passive: false })
    canvas.addEventListener('touchend', onEnd)

    return () => {
      canvas.removeEventListener('mousedown', onStart)
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mouseup', onEnd)
      canvas.removeEventListener('mouseleave', onEnd)
      canvas.removeEventListener('touchstart', onStart)
      canvas.removeEventListener('touchmove', onMove)
      canvas.removeEventListener('touchend', onEnd)
    }
  }, [stage])

  function clearCanvas() {
    const canvas = canvasRef.current!
    canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
  }

  async function handleSubmit() {
    if (!acceptedTerms || !orderInfo) return
    const canvas = canvasRef.current!
    const signature = canvas.toDataURL('image/png')
    setStage('signing')
    try {
      await authApi.post('/orders/sign-with-token', { token, signature, document_hash: orderInfo.document_hash })
      setTimeout(() => setStage('success'), 2000)
    } catch (err: unknown) {
      const msg =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Erro ao enviar assinatura. Tente novamente.'
      setErrorMsg(msg)
      setStage('error')
    }
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="font-display text-5xl tracking-[0.35em] font-light text-gold">ILYA</h1>
          <div className="w-16 h-px bg-gold-soft mx-auto mt-2" />
        </div>

        {stage === 'loading' && (
          <div className="text-center text-muted text-sm">Verificando contrato...</div>
        )}

        {stage === 'error' && (
          <div className="bg-white rounded-2xl border border-line shadow-sm p-6 text-center">
            <p className="text-danger text-sm font-medium mb-1" role="alert">Erro</p>
            <p className="text-ink-2 text-sm">{errorMsg}</p>
          </div>
        )}

        {stage === 'already_signed' && (
          <div className="bg-white rounded-2xl border border-line shadow-sm p-6 text-center">
            <p className="text-gold text-base font-semibold mb-1">Contrato já assinado</p>
            <p className="text-ink-2 text-sm">
              O pedido <span className="font-mono font-semibold text-gold">{orderInfo?.order_code}</span> já possui assinatura registrada.
            </p>
          </div>
        )}

        {stage === 'ready' && orderInfo && (
          <div className="bg-white rounded-2xl border border-line shadow-sm p-6 space-y-5 max-h-[85vh] overflow-y-auto">
            <div>
              <p className="text-xs text-muted uppercase tracking-wider mb-1">Pedido</p>
              <p className="text-gold font-mono font-semibold text-lg">{orderInfo.order_code}</p>
            </div>

            <div className="space-y-3 border-y border-line py-4 text-sm text-ink-2">
              <p className="font-semibold">Termos do pedido — versão {orderInfo.document.document_version}</p>
              {orderInfo.document.items.map((item, index) => (
                <div key={`${item.product_code}-${index}`} className="border-b border-line pb-2 last:border-0">
                  <p className="font-medium">{item.qty} × {item.description} ({item.product_code})</p>
                  <p>Preço unitário: {item.unit_price} {orderInfo.document.currency}; desconto: {item.discount}%; {item.tax_label}: {item.ipi_rate}%</p>
                  <p>Dimensões: {item.altura} × {item.largura} × {item.profundidade}</p>
                  {item.observacao && <p>Observação do item: {item.observacao}</p>}
                  {Object.entries(item.optionals).length > 0 && <p>Opcionais: {Object.entries(item.optionals).map(([key, value]) => `${key}: ${value}`).join(', ')}</p>}
                </div>
              ))}
              {orderInfo.document.notes && <p>Observações: {orderInfo.document.notes}</p>}
              <p className="font-semibold">Total: {orderInfo.document.total_with_ipi} {orderInfo.document.currency}</p>
              <p className="text-xs text-muted break-all">Identificador dos termos: {orderInfo.document_hash}</p>
            </div>

            <label className="flex gap-2 text-sm text-ink-2">
              <input type="checkbox" checked={acceptedTerms} onChange={event => setAcceptedTerms(event.target.checked)} />
              Li os termos do pedido acima e concordo em assiná-los.
            </label>

            <div>
              <p id="signature-label" className="text-xs text-muted uppercase tracking-wider mb-2">Sua Assinatura</p>
              <canvas
                ref={canvasRef}
                width={600}
                height={200}
                role="img"
                aria-labelledby="signature-label"
                aria-describedby="signature-hint"
                className="w-full border border-line rounded-xl bg-surface-quiet cursor-crosshair touch-none"
              />
              <p id="signature-hint" className="sr-only">
                Área de desenho da assinatura: desenhe com o dedo, caneta ou mouse.
              </p>
              <button
                type="button"
                onClick={clearCanvas}
                className="mt-1 min-h-11 lg:min-h-0 text-xs text-muted hover:text-gold underline transition-colors"
              >
                Limpar
              </button>
            </div>

            <button
              type="button"
              onClick={handleSubmit}
              disabled={!acceptedTerms}
              className="btn-primary w-full py-3"
            >
              Assinar Contrato
            </button>

            <p className="text-[10px] text-muted-3 text-center">
              Ao assinar você confirma o aceite dos termos e valores do pedido acima.
            </p>
          </div>
        )}

        {stage === 'signing' && <BrandLoadingOverlay label="Gerando assinatura" />}

        {stage === 'success' && (
          <div className="bg-white rounded-2xl border border-line shadow-sm p-8 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-bg-2 flex items-center justify-center mx-auto">
              <span className="text-gold text-2xl">✓</span>
            </div>
            <p className="text-ink font-semibold text-base">Contrato assinado com sucesso!</p>
            <p className="text-muted-2 text-sm">
              Seu pedido <span className="font-mono font-semibold text-gold">{orderInfo?.order_code}</span> foi confirmado.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
