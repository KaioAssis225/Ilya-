import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useNavigate } from 'react-router'
import { FlaskConical, LayoutDashboard, Warehouse, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { BrandLoadingOverlay } from './BrandLoadingOverlay'

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
// Com prefers-reduced-motion as transições encurtam: o usuário não espera
// coreografia que nem enxerga (a regra global de CSS já congela as animações).
const REDUCED = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
const RETURN_HOLD_MS = REDUCED ? 120 : 520
const RETURN_FADE_MS = REDUCED ? 80 : 480

type ReturnPhase = 'idle' | 'hold' | 'out'

// Atalhos do botão flutuante. A ordem daqui é a ordem do leque: Dashboard no
// topo, Armazém no meio, Protótipo embaixo. Quem decide quais aparecem é o
// PrivateApp (reaproveitando as mesmas checagens das abas); este componente só
// desenha o que recebe.
export type FabShortcut = 'dashboard' | 'armazem' | 'prototipo'

const SHORTCUTS: Record<FabShortcut, { label: string; openLabel: string; path: string; Icon: LucideIcon }> = {
  dashboard: { label: 'Dashboard', openLabel: 'Abrir Dashboard BI', path: '/dashboard', Icon: LayoutDashboard },
  armazem: { label: 'Armazém', openLabel: 'Abrir Armazém', path: '/showrooms', Icon: Warehouse },
  prototipo: { label: 'Protótipo', openLabel: 'Abrir Protótipos', path: '/prototipos', Icon: FlaskConical },
}
const SHORTCUT_ORDER: FabShortcut[] = ['dashboard', 'armazem', 'prototipo']

// Leque: os itens saem do botão para cima e para a esquerda, do topo (90°) até
// a esquerda (180°). Com este raio sobram 35px entre os itens vizinhos, e o
// rótulo de cada um fica à esquerda do seu círculo sem encostar no do lado.
const FAN_RADIUS = 120
const ITEM_SIZE = 44

function fanOffset(index: number, total: number) {
  const angle = total === 1 ? Math.PI / 2 : Math.PI / 2 + (index * (Math.PI / 2)) / (total - 1)
  return { x: Math.round(Math.cos(angle) * FAN_RADIUS), y: Math.round(-Math.sin(angle) * FAN_RADIUS) }
}

export default function DashboardFab({
  mode,
  currentPath,
  shortcuts = ['dashboard'],
  raised = false,
}: {
  mode: 'enter' | 'exit'
  currentPath?: string
  shortcuts?: FabShortcut[]
  // Ergue o botão acima da barra fixa do montador de orçamento (até lg).
  raised?: boolean
}) {
  const navigate = useNavigate()
  const menuId = useId()
  const wrapperRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const [menuOpen, setMenuOpen] = useState(false)
  const [enteringMode, setEnteringMode] = useState<'enter' | 'exit' | null>(null)
  const entering = enteringMode === mode
  const [returnPhase, setReturnPhase] = useState<ReturnPhase>('idle')

  const items = SHORTCUT_ORDER.filter(key => shortcuts.includes(key))
  const single = SHORTCUTS[items[0] ?? 'dashboard']
  // Só abre menu quando há mais de um destino; com um só o botão vai direto
  // (o Dashboard no BR, por exemplo).
  const hasMenu = mode === 'enter' && items.length > 1
  const open = hasMenu && menuOpen

  // O componente permanece montado ao trocar de rota (mesmo lugar na árvore),
  // então o véu de entrada precisa ser limpo quando o modo muda. O overlay de
  // volta (returnPhase) é gerido pelo próprio fluxo abaixo — de propósito não é
  // resetado aqui, senão sumiria no instante em que Pedidos monta.
  useEffect(() => {
    void mode
  }, [mode])

  // Menu aberto: fecha com clique fora e com Esc (devolvendo o foco ao botão).
  // O foco entra no primeiro item ao abrir.
  useEffect(() => {
    if (!open) return
    itemRefs.current[0]?.focus()
    function onDocumentClick(event: MouseEvent) {
      // composedPath() e não target.contains(): ao abrir, o ícone do botão troca
      // por um X e o <svg> clicado sai do DOM antes do clique chegar aqui — o
      // contains() o veria "fora" e fecharia o menu no mesmo toque.
      const wrapper = wrapperRef.current
      if (wrapper && !event.composedPath().includes(wrapper)) setMenuOpen(false)
    }
    function onDocumentKey(event: globalThis.KeyboardEvent) {
      if (event.key !== 'Escape') return
      setMenuOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('click', onDocumentClick)
    document.addEventListener('keydown', onDocumentKey)
    return () => {
      document.removeEventListener('click', onDocumentClick)
      document.removeEventListener('keydown', onDocumentKey)
    }
  }, [open])

  function goDashboard() {
    if (entering) return
    setEnteringMode(mode)
    if (currentPath) sessionStorage.setItem(RETURN_KEY, currentPath)
    setTimeout(() => navigate('/dashboard'), REDUCED ? 0 : ENTER_VEIL_MS)
  }

  function runShortcut(key: FabShortcut) {
    setMenuOpen(false)
    if (key === 'dashboard') goDashboard()
    else navigate(SHORTCUTS[key].path)
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const count = items.length
    const current = itemRefs.current.findIndex(node => node === document.activeElement)
    const move = (next: number) => {
      event.preventDefault()
      itemRefs.current[(next + count) % count]?.focus()
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') move(current + 1)
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') move(current - 1)
    else if (event.key === 'Home') move(0)
    else if (event.key === 'End') move(count - 1)
    else if (event.key === 'Tab') setMenuOpen(false)
  }

  function handleClick() {
    if (hasMenu) {
      setMenuOpen(value => !value)
      return
    }

    if (mode === 'enter') {
      runShortcut(items[0] ?? 'dashboard')
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
      setEnteringMode(mode)
      setTimeout(() => navigate(back), REDUCED ? 0 : ENTER_VEIL_MS)
    }
  }

  const returnVisible = returnPhase !== 'idle'
  const TriggerIcon = hasMenu ? LayoutDashboard : single.Icon

  return (
    <>
      {/* O invólucro fixo carrega o botão e o leque; os itens nascem do centro
          do botão e se afastam por transform. */}
      <div
        ref={wrapperRef}
        className={`fixed right-4 md:right-6 z-fab w-14 h-14 ${
          raised ? 'bottom-36 lg:bottom-6' : 'bottom-20 md:bottom-6'
        }`}
      >
        {/* Véu transparente: o toque fora do menu só fecha, não "vaza" para o
            que estiver embaixo. */}
        {open && <div data-testid="fab-scrim" aria-hidden="true" className="fixed inset-0 -z-10" />}

        {hasMenu && (
          <div id={menuId} role="menu" aria-label="Atalhos rápidos" onKeyDown={onMenuKeyDown}>
            {items.map((key, index) => {
              const { label, path, Icon } = SHORTCUTS[key]
              const offset = fanOffset(index, items.length)
              const active = currentPath === path || currentPath?.startsWith(`${path}/`)
              return (
                <button
                  key={key}
                  ref={node => { itemRefs.current[index] = node }}
                  type="button"
                  role="menuitem"
                  tabIndex={open ? 0 : -1}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => runShortcut(key)}
                  className="absolute left-1/2 top-1/2 rounded-full flex items-center justify-center bg-surface text-gold border border-gold/30 shadow-md transition-[transform,opacity,visibility] duration-200 ease-out hover:bg-gold-wash active:scale-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold"
                  style={{
                    width: ITEM_SIZE,
                    height: ITEM_SIZE,
                    marginLeft: -ITEM_SIZE / 2,
                    marginTop: -ITEM_SIZE / 2,
                    transform: open ? `translate(${offset.x}px, ${offset.y}px) scale(1)` : 'translate(0, 0) scale(0.4)',
                    opacity: open ? 1 : 0,
                    visibility: open ? 'visible' : 'hidden',
                    transitionDelay: open ? `${index * 40}ms` : '0ms',
                  }}
                >
                  <Icon className="w-5 h-5" />
                  <span className="absolute right-full mr-2 whitespace-nowrap rounded-full bg-surface border border-line px-3 py-1.5 text-xs font-semibold text-ink shadow-sm">
                    {label}
                  </span>
                </button>
              )
            })}
          </div>
        )}

        <button
          ref={triggerRef}
          type="button"
          onClick={handleClick}
          aria-label={mode === 'exit' ? 'Fechar Dashboard BI' : hasMenu ? 'Atalhos rápidos' : single.openLabel}
          aria-haspopup={hasMenu ? 'menu' : undefined}
          aria-expanded={hasMenu ? open : undefined}
          aria-controls={hasMenu ? menuId : undefined}
          title={mode === 'exit' ? 'Voltar' : hasMenu ? 'Atalhos' : single.label}
          className="group relative w-full h-full rounded-full flex items-center justify-center text-white shadow-lg transition-transform duration-200 active:scale-90 hover:scale-105"
          style={{ background: 'linear-gradient(135deg, var(--color-gold-highlight) 0%, var(--color-gold) 100%)' }}
        >
          <span className="absolute inset-0 rounded-full border-2 border-gold pointer-events-none opacity-0 group-hover:opacity-100 group-hover:[animation:fabRing_1.1s_ease-out_infinite]" />
          {mode === 'exit' || open ? (
            <X className="w-6 h-6 relative transition-transform duration-300 group-hover:rotate-90" />
          ) : (
            <TriggerIcon className="w-6 h-6 relative transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-110" />
          )}
        </button>
      </div>

      {/* Véu creme de entrada — cobre o intervalo até a rota trocar e emenda no
          DashboardIntro (mesma cor), sem flash dourado. */}
      {entering && (
        <div
          className="fixed inset-0 z-loading pointer-events-none bg-bg"
          style={{ animation: 'moduleVeil 0.18s ease-out forwards' }}
        />
      )}

      {/* Assinatura ILYA ao voltar para Pedidos — segue montada durante a
          navegação e some sobre a tela de Pedidos (bridge, não corte seco). */}
      {returnVisible && (
        <BrandLoadingOverlay
          label="Voltando aos Orçamentos"
          progressDuration={1}
          className={`bg-bg! transition-opacity ease-out ${
            returnPhase === 'out' ? 'opacity-0 pointer-events-none' : 'opacity-100'
          }`}
          style={{ transitionDuration: `${RETURN_FADE_MS}ms` }}
        />
      )}
    </>
  )
}
