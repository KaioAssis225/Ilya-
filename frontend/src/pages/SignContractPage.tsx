import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

interface OrderInfo {
  order_code: string
  total_value: number
  is_signed: boolean
}

type Stage = 'loading' | 'ready' | 'signing' | 'success' | 'error' | 'already_signed'

function fmt(n: number) {
  return 'R$ ' + Number(n).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export default function SignContractPage() {
  const [token] = useState<string>(() => {
    // Token vem via fragment (#) para não vazar em logs de servidor nem Referer (V-04)
    const t = window.location.hash.slice(1)
    if (t) {
      window.history.replaceState(null, '', window.location.pathname)
    }
    return t
  })

  const [stage, setStage] = useState<Stage>('loading')
  const [orderInfo, setOrderInfo] = useState<OrderInfo | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const isDrawingRef = useRef(false)

  useEffect(() => {
    if (!token) {
      setErrorMsg('Token não fornecido.')
      setStage('error')
      return
    }
    axios
      .get<OrderInfo>(`/api/v1/orders/verify-sign-token?token=${encodeURIComponent(token)}`)
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
    const canvas = canvasRef.current!
    const signature = canvas.toDataURL('image/png')
    setStage('signing')
    try {
      await axios.post('/api/v1/orders/sign-with-token', { token, signature })
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
    <div className="min-h-screen bg-[#f8f6f2] flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <p
            className="text-5xl tracking-[0.35em] font-light text-[#8b6914]"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
          >
            ILYA
          </p>
          <div className="w-16 h-px bg-[#c8a84b] mx-auto mt-2" />
        </div>

        {stage === 'loading' && (
          <div className="text-center text-[#9d8d81] text-sm">Verificando contrato...</div>
        )}

        {stage === 'error' && (
          <div className="bg-white rounded-2xl border border-[#e8e0d6] shadow-sm p-6 text-center">
            <p className="text-red-700 text-sm font-medium mb-1">Erro</p>
            <p className="text-[#4a3f38] text-sm">{errorMsg}</p>
          </div>
        )}

        {stage === 'already_signed' && (
          <div className="bg-white rounded-2xl border border-[#e8e0d6] shadow-sm p-6 text-center">
            <p className="text-[#8b6914] text-base font-semibold mb-1">Contrato já assinado</p>
            <p className="text-[#4a3f38] text-sm">
              O pedido <span className="font-mono font-semibold text-[#8b6914]">{orderInfo?.order_code}</span> já possui assinatura registrada.
            </p>
          </div>
        )}

        {stage === 'ready' && orderInfo && (
          <div className="bg-white rounded-2xl border border-[#e8e0d6] shadow-sm p-6 space-y-5">
            <div>
              <p className="text-xs text-[#9d8d81] uppercase tracking-wider mb-1">Pedido</p>
              <p className="text-[#8b6914] font-mono font-semibold text-lg">{orderInfo.order_code}</p>
            </div>
            <div>
              <p className="text-xs text-[#9d8d81] uppercase tracking-wider mb-1">Valor Total</p>
              <p className="text-[#2c2420] font-bold text-xl">{fmt(orderInfo.total_value)}</p>
            </div>

            <div>
              <p className="text-xs text-[#9d8d81] uppercase tracking-wider mb-2">Sua Assinatura</p>
              <canvas
                ref={canvasRef}
                width={600}
                height={200}
                className="w-full border border-[#e8e0d6] rounded-xl bg-[#fafaf9] cursor-crosshair touch-none"
              />
              <button
                onClick={clearCanvas}
                className="mt-1 text-xs text-[#9d8d81] hover:text-[#8b6914] underline transition-colors"
              >
                Limpar
              </button>
            </div>

            <button
              onClick={handleSubmit}
              className="w-full py-3 bg-[#8b6914] text-white rounded-xl font-semibold text-sm hover:bg-[#7a5c10] transition-colors shadow-sm"
            >
              Assinar Contrato
            </button>

            <p className="text-[10px] text-[#a89a8e] text-center">
              Ao assinar você confirma o aceite dos termos e valores do pedido acima.
            </p>
          </div>
        )}

        {stage === 'signing' && (
          <div className="fixed inset-0 z-[400] flex flex-col items-center justify-center bg-[#1a1410]/88 backdrop-blur-sm">
            <div
              className="absolute w-[520px] h-[520px] rounded-full pointer-events-none"
              style={{
                background: 'radial-gradient(circle, rgba(139,105,20,0.28) 0%, transparent 68%)',
                animation: 'pulseRadial 2.2s ease-in-out infinite',
              }}
            />
            <p
              className="relative text-[80px] leading-none tracking-[0.35em] font-light select-none"
              style={{
                fontFamily: "'Cormorant Garamond', Georgia, serif",
                backgroundImage: 'linear-gradient(90deg, #7a5a10 0%, #c8952e 25%, #f5d78e 50%, #c8952e 75%, #7a5a10 100%)',
                backgroundSize: '200% auto',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                animation: 'lightSweep 2.4s linear infinite',
              }}
            >
              ILYA
            </p>
            <p
              className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-[#c8952e]"
              style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}
            >
              GERANDO ASSINATURA
            </p>
            <div className="mt-9 w-52 h-[1px] bg-[#8b6914]/25 overflow-hidden rounded-full">
              <div
                className="h-full rounded-full"
                style={{
                  background: 'linear-gradient(90deg, #7a5a10, #f5d78e, #7a5a10)',
                  animation: 'progressLine 3s linear forwards',
                }}
              />
            </div>
          </div>
        )}

        {stage === 'success' && (
          <div className="bg-white rounded-2xl border border-[#e8e0d6] shadow-sm p-8 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-[#f0ece6] flex items-center justify-center mx-auto">
              <span className="text-[#8b6914] text-2xl">✓</span>
            </div>
            <p className="text-[#2c2420] font-semibold text-base">Contrato assinado com sucesso!</p>
            <p className="text-[#8a7a6e] text-sm">
              Seu pedido <span className="font-mono font-semibold text-[#8b6914]">{orderInfo?.order_code}</span> foi confirmado.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
