import { useEffect, useRef, useState } from 'react'

const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const integer = new Intl.NumberFormat('pt-BR')

// Alturas relativas das barrinhas do mini-gráfico de entrada — assinatura
// visual do módulo BI, distinta do wordmark "ILYA" usado em Login/Orçamento.
const BAR_HEIGHTS = [0.35, 0.6, 0.42, 0.78, 0.55, 0.9, 0.68]

function useCountUp(target: number | null, durationMs: number) {
  const [value, setValue] = useState(0)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (target === null) return
    const finalValue = target
    let raf: number
    function tick(now: number) {
      if (startRef.current === null) startRef.current = now
      const elapsed = now - startRef.current
      const progress = Math.min(1, elapsed / durationMs)
      // Ease-out-quart: desacelera suave no fim, sem bounce.
      const eased = 1 - Math.pow(1 - progress, 4)
      setValue(finalValue * eased)
      if (progress < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, durationMs])

  return value
}

export default function DashboardIntro({
  revenueTotal,
  ordersTotal,
  onDone,
}: {
  revenueTotal: number | null
  ordersTotal: number | null
  onDone: () => void
}) {
  const [visible, setVisible] = useState(true)
  const revenue = useCountUp(revenueTotal, 900)
  const orders = useCountUp(ordersTotal, 900)

  useEffect(() => {
    // Espera pelo menos a entrada terminar (barras + contagem); se os dados
    // demorarem, sai de qualquer forma em 3s para nunca travar a tela.
    const minTimer = setTimeout(() => {
      if (revenueTotal !== null) setVisible(false)
    }, 1400)
    const maxTimer = setTimeout(() => setVisible(false), 3000)
    return () => { clearTimeout(minTimer); clearTimeout(maxTimer) }
  }, [revenueTotal])

  useEffect(() => {
    if (!visible) {
      const t = setTimeout(onDone, 280) // aguarda o fade-out
      return () => clearTimeout(t)
    }
  }, [visible, onDone])

  return (
    <div
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[#f8f6f2]/95 backdrop-blur-sm overflow-hidden transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
      aria-hidden="true"
    >
      {/* Grid sutil de fundo — motivo visual do BI */}
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage: 'linear-gradient(#8b6914 1px, transparent 1px), linear-gradient(90deg, #8b6914 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />
      {/* Sweep dourado cruzando a grid */}
      <div className="absolute inset-0 overflow-hidden">
        <div
          className="absolute top-0 bottom-0 w-40"
          style={{
            background: 'linear-gradient(90deg, transparent, rgba(139,105,20,0.16), transparent)',
            animation: 'gridSweep 2.2s ease-in-out infinite',
          }}
        />
      </div>

      <div className="relative flex flex-col items-center gap-6">
        {/* Mini-gráfico de barras subindo */}
        <div className="flex items-end gap-2 h-16" role="presentation">
          {BAR_HEIGHTS.map((h, i) => (
            <div
              key={i}
              className="w-3 rounded-t-sm origin-bottom"
              style={{
                height: `${h * 64}px`,
                background: 'linear-gradient(180deg, #c8952e 0%, #8b6914 100%)',
                animation: `barRise 0.5s cubic-bezier(0.22, 1, 0.36, 1) both`,
                animationDelay: `${i * 60}ms`,
              }}
            />
          ))}
        </div>

        <div className="text-center">
          <p
            className="text-2xl tracking-[0.2em] uppercase text-ink"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
          >
            Dashboard <span className="text-gold">BI</span>
          </p>
          <p className="mt-2 text-[11px] tracking-[0.5em] uppercase font-semibold text-gold" style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}>
            Carregando indicadores
          </p>
        </div>

        <div className="flex items-center gap-8 mt-1 tabular-nums">
          <div className="text-center">
            <span className="block text-xl font-semibold text-ink">{currency.format(revenue)}</span>
            <span className="block text-[10px] uppercase tracking-wider text-muted mt-0.5">Receita</span>
          </div>
          <div className="w-px h-8 bg-line" />
          <div className="text-center">
            <span className="block text-xl font-semibold text-ink">{integer.format(orders)}</span>
            <span className="block text-[10px] uppercase tracking-wider text-muted mt-0.5">Pedidos</span>
          </div>
        </div>
      </div>
    </div>
  )
}
