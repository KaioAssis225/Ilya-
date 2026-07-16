import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LayoutDashboard, X } from 'lucide-react'

const RETURN_KEY = 'dashboard_return_to'
const FALLBACK_RETURN = '/produtos'
const ILYA_TRANSITION_MS = 850

export default function DashboardFab({
  mode,
  currentPath,
}: {
  mode: 'enter' | 'exit'
  currentPath?: string
}) {
  const navigate = useNavigate()
  const [switching, setSwitching] = useState(false)
  const [ilyaTransition, setIlyaTransition] = useState(false)

  // O componente permanece montado ao trocar de rota (mesmo lugar na árvore),
  // então o estado da transição anterior precisa ser limpo quando o modo muda,
  // senão o clique seguinte fica travado pelo guard abaixo.
  useEffect(() => {
    setSwitching(false)
    setIlyaTransition(false)
  }, [mode])

  function handleClick() {
    if (switching) return
    setSwitching(true)
    if (mode === 'enter') {
      // Wipe de troca de módulo ao entrar no Dashboard.
      if (currentPath) sessionStorage.setItem(RETURN_KEY, currentPath)
      setTimeout(() => navigate('/dashboard'), 220)
      return
    }
    const back = sessionStorage.getItem(RETURN_KEY) || FALLBACK_RETURN
    // Voltar para Pedidos reaproveita a assinatura visual ILYA (mesmo
    // overlay do login e da assinatura de pedidos), como se o módulo de
    // Pedidos estivesse "carregando de volta" — os demais destinos usam
    // o wipe padrão.
    if (back.startsWith('/pedidos')) {
      setIlyaTransition(true)
      setTimeout(() => navigate(back), ILYA_TRANSITION_MS)
    } else {
      setTimeout(() => navigate(back), 220)
    }
  }

  return (
    <>
      <button
        onClick={handleClick}
        aria-label={mode === 'enter' ? 'Abrir Dashboard BI' : 'Fechar Dashboard BI'}
        title={mode === 'enter' ? 'Dashboard BI' : 'Voltar'}
        className="group fixed bottom-20 md:bottom-6 right-4 md:right-6 z-40 w-14 h-14 rounded-full flex items-center justify-center text-white shadow-lg transition-transform duration-200 active:scale-90 hover:scale-105"
        style={{ background: 'linear-gradient(135deg, #c8952e 0%, #8b6914 100%)' }}
      >
        <span className="absolute inset-0 rounded-full border-2 border-gold pointer-events-none opacity-0 group-hover:opacity-100 group-hover:[animation:fabRing_1.1s_ease-out_infinite]" />
        {mode === 'enter' ? (
          <LayoutDashboard className="w-6 h-6 relative transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-110" />
        ) : (
          <X className="w-6 h-6 relative transition-transform duration-300 group-hover:rotate-90" />
        )}
      </button>

      {switching && !ilyaTransition && (
        <div
          className="fixed inset-0 z-[110] pointer-events-none origin-left"
          style={{
            background: 'linear-gradient(90deg, #5a4508 0%, #8b6914 50%, #c8952e 100%)',
            animation: 'moduleWipe 0.5s cubic-bezier(0.65, 0, 0.35, 1) forwards',
          }}
        />
      )}

      {ilyaTransition && (
        <div className="fixed inset-0 z-[110] flex flex-col items-center justify-center bg-bg/95 backdrop-blur-sm">
          <div
            className="absolute w-[520px] h-[520px] rounded-full pointer-events-none"
            style={{ background: 'radial-gradient(circle, rgba(139,105,20,0.18) 0%, transparent 68%)', animation: 'pulseRadial 2.2s ease-in-out infinite' }}
          />
          <p
            className="relative text-[50px] sm:text-[80px] leading-none tracking-[0.35em] font-light select-none"
            style={{
              fontFamily: "'Cormorant Garamond', Georgia, serif",
              backgroundImage: 'linear-gradient(90deg, #5a4508 0%, #8b6914 25%, #c8952e 50%, #8b6914 75%, #5a4508 100%)',
              backgroundSize: '200% auto',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              animation: 'lightSweep 2.4s linear infinite',
            }}
          >
            ILYA
          </p>
          <p className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-gold" style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}>
            Voltando aos Pedidos
          </p>
          <div className="mt-9 w-52 h-[1px] bg-gold/25 overflow-hidden rounded-full">
            <div className="h-full rounded-full" style={{ background: 'linear-gradient(90deg, #5a4508, #c8952e, #5a4508)', animation: 'progressLine 3s linear forwards' }} />
          </div>
        </div>
      )}
    </>
  )
}
