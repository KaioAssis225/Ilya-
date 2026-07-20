import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LayoutDashboard, X } from 'lucide-react'

const RETURN_KEY = 'dashboard_return_to'
const FALLBACK_RETURN = '/produtos'

// Entrar no Dashboard: véu creme curtíssimo só para cobrir o intervalo até a
// rota trocar. O próprio DashboardPage já abre com a assinatura de barras
// (DashboardIntro), também creme, então a passagem é contínua — sem o antigo
// "bloco dourado" que piscava por cima da tela.
const ENTER_VEIL_MS = 180

// Voltar para Pedidos: a assinatura ILYA fica sobre o Dashboard por um instante
// e SEGUE montada durante a navegação, desaparecendo só depois que Pedidos já
// está atrás dela. Isso transforma o antigo corte seco numa transição de
// carregamento de verdade.
const RETURN_HOLD_MS = 520
const RETURN_FADE_MS = 480

type ReturnPhase = 'idle' | 'hold' | 'out'

export default function DashboardFab({
  mode,
  currentPath,
}: {
  mode: 'enter' | 'exit'
  currentPath?: string
}) {
  const navigate = useNavigate()
  const [entering, setEntering] = useState(false)
  const [returnPhase, setReturnPhase] = useState<ReturnPhase>('idle')

  // O componente permanece montado ao trocar de rota (mesmo lugar na árvore),
  // então o véu de entrada precisa ser limpo quando o modo muda. O overlay de
  // volta (returnPhase) é gerido pelo próprio fluxo abaixo — de propósito não é
  // resetado aqui, senão sumiria no instante em que Pedidos monta.
  useEffect(() => {
    setEntering(false)
  }, [mode])

  function handleClick() {
    if (mode === 'enter') {
      if (entering) return
      setEntering(true)
      if (currentPath) sessionStorage.setItem(RETURN_KEY, currentPath)
      setTimeout(() => navigate('/dashboard'), ENTER_VEIL_MS)
      return
    }

    if (returnPhase !== 'idle' || entering) return
    const back = sessionStorage.getItem(RETURN_KEY) || FALLBACK_RETURN

    if (back.startsWith('/pedidos')) {
      // Fase 1 (hold): ILYA aparece sobre o Dashboard.
      setReturnPhase('hold')
      setTimeout(() => {
        // Navega e, no mesmo tick, inicia o fade — o overlay continua montado
        // (mesma instância do FAB) e agora desaparece revelando Pedidos.
        navigate(back)
        setReturnPhase('out')
        setTimeout(() => setReturnPhase('idle'), RETURN_FADE_MS)
      }, RETURN_HOLD_MS)
    } else {
      // Demais destinos usam o mesmo véu creme discreto da entrada.
      setEntering(true)
      setTimeout(() => navigate(back), ENTER_VEIL_MS)
    }
  }

  const returnVisible = returnPhase !== 'idle'

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

      {/* Véu creme de entrada — cobre o intervalo até a rota trocar e emenda no
          DashboardIntro (mesma cor), sem flash dourado. */}
      {entering && (
        <div
          className="fixed inset-0 z-[110] pointer-events-none bg-bg"
          style={{ animation: 'moduleVeil 0.18s ease-out forwards' }}
        />
      )}

      {/* Assinatura ILYA ao voltar para Pedidos — segue montada durante a
          navegação e some sobre a tela de Pedidos (bridge, não corte seco). */}
      {returnVisible && (
        <div
          className={`fixed inset-0 z-[110] flex flex-col items-center justify-center bg-bg backdrop-blur-sm transition-opacity ease-out ${
            returnPhase === 'out' ? 'opacity-0 pointer-events-none' : 'opacity-100'
          }`}
          style={{ transitionDuration: `${RETURN_FADE_MS}ms` }}
          aria-hidden="true"
        >
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
            <div className="h-full rounded-full" style={{ background: 'linear-gradient(90deg, #5a4508, #c8952e, #5a4508)', animation: 'progressLine 1s linear forwards' }} />
          </div>
        </div>
      )}
    </>
  )
}
