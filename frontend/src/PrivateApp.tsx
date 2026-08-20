import { useState, lazy, Suspense } from 'react'
import { Routes, Route, Navigate, NavLink, useLocation } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { LayoutGrid, ShoppingCart, ClipboardList, Users, ShieldCheck, LogOut, Bell } from 'lucide-react'
import type { AuthUser } from './contexts/AuthContext'
import { useAuth } from './hooks/useAuth'
import { useNotifications, useMarkNotificationRead } from './hooks/useNotifications'
import { useCartQuantities } from './hooks/useCart'
import { countCartUnits } from './lib/cart'
import ProfileModal from './components/ProfileModal'
import DashboardFab from './components/DashboardFab'
import { ErrorBoundary } from './components/ErrorBoundary'
import { MarketSwitcher } from './components/MarketSwitcher'
import { queryClient } from './lib/queryClient'
import { MarketTransition } from './components/MarketTransition'
// Rotas além do login são code-split — reduz o bundle inicial que o usuário
// não autenticado precisa baixar antes de ver a tela de entrada.
const CadastroPage = lazy(() => import('./pages/CadastroPage'))
const OrcamentoPage = lazy(() => import('./pages/OrcamentoPage'))
const PedidosPage = lazy(() => import('./pages/PedidosPage'))
const ProdutosPage = lazy(() => import('./pages/ProdutosPage'))
const AdminPage = lazy(() => import('./pages/AdminPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const TrocarSenhaPage = lazy(() => import('./pages/TrocarSenhaPage'))

// ── RBAC helpers ──────────────────────────────────────────────────────────────

function isCliente(user: AuthUser) {
  // SEC-01: role própria `cliente`; mantém o legado `vendedor`+linked_id até a migração propagar.
  return user.role === 'cliente' || (user.role === 'vendedor' && !!user.linked_id)
}

function canSeeOrcamentoPedidos(user: AuthUser) {
  return user.role !== 'cadastros' && user.role !== 'executivo'
}

function canSeeCadastros(user: AuthUser) {
  return !isCliente(user) && user.role !== 'executivo'
}

function canSeeAdmin(user: AuthUser) {
  return user.role === 'admin'
}

// Bloco 95: role executivo (ou qualquer role com a flag habilitada pelo admin)
// só acessa a aba Dashboard.
function canSeeDashboard(user: AuthUser) {
  return user.role === 'admin' || user.role === 'executivo' || user.can_view_dashboard
}

function defaultRoute(user: AuthUser) {
  if (user.role === 'executivo') return '/dashboard'
  if (user.role === 'representante') return '/orcamentos'
  if (canSeeCadastros(user)) return '/cadastros'
  return '/orcamentos'
}

// ── RoleGuard: redirect if user doesn't have access to this route ─────────────

function RoleGuard({ allowed, children }: { allowed: (user: AuthUser) => boolean; children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user) return null
  if (!allowed(user)) return <Navigate to={defaultRoute(user)} replace />
  return <>{children}</>
}

// ── DashboardFabGate: mostra o FAB do Dashboard em toda a aplicação para ──────
// quem tem acesso ao BI (Bloco 95) — mesmo botão entra e volta do módulo.

function DashboardFabGate() {
  const { user } = useAuth()
  const location = useLocation()
  if (!user || user.must_change_password) return null
  if (!canSeeDashboard(user)) return null
  if (location.pathname.startsWith('/dashboard')) return <DashboardFab mode="exit" />
  return <DashboardFab mode="enter" currentPath={location.pathname} />
}

// ── BottomNav ─────────────────────────────────────────────────────────────────

function BottomNav() {
  const { user, logout } = useAuth()
  const location = useLocation()
  // Antes dos `return null` abaixo: hook não pode ficar após saída condicional.
  const cartUnits = countCartUnits(useCartQuantities(user?.id, user?.active_market))
  if (!user || user.must_change_password) return null
  // Bloco 95: Dashboard é um módulo isolado, sem a navegação padrão do app.
  if (location.pathname.startsWith('/dashboard')) return null

  const active = (path: string) => location.pathname.startsWith(path)

  const itemClass = (path: string) =>
    `flex flex-col items-center gap-0.5 min-w-[44px] min-h-[44px] justify-center px-3 transition-colors ${
      active(path) ? 'text-gold' : 'text-muted-3'
    }`

  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white/90 backdrop-blur-md border-t border-line flex items-center justify-around px-2 pb-safe" aria-label="Navegação principal">
      <NavLink to="/produtos" className={itemClass('/produtos')} aria-label="Produtos">
        <LayoutGrid className="w-5 h-5" />
        <span className="text-[11px] font-semibold uppercase tracking-wider">Produtos</span>
      </NavLink>
      {canSeeOrcamentoPedidos(user) && (
        <NavLink
          to="/orcamentos"
          className={itemClass('/orcamentos')}
          aria-label={cartUnits > 0 ? `Novo Orçamento, ${cartUnits} itens` : 'Novo Orçamento'}
        >
          <span className="relative">
            <ShoppingCart className="w-5 h-5" />
            {/* Única confirmação de que o "+" do catálogo funcionou: sem ela o
                item entra no orçamento sem nenhum sinal na tela. */}
            {cartUnits > 0 && (
              <span className="absolute -top-1.5 -right-2 min-w-[16px] h-4 px-1 rounded-full bg-gold text-white text-[9px] font-bold flex items-center justify-center tabular-nums">
                {cartUnits > 99 ? '99+' : cartUnits}
              </span>
            )}
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-wider">Orçamento</span>
        </NavLink>
      )}
      {canSeeOrcamentoPedidos(user) && (
        <NavLink to="/pedidos" className={itemClass('/pedidos')} aria-label="Pedidos">
          <ClipboardList className="w-5 h-5" />
          <span className="text-[11px] font-semibold uppercase tracking-wider">Pedidos</span>
        </NavLink>
      )}
      {canSeeCadastros(user) && (
        <NavLink to="/cadastros" className={itemClass('/cadastros')} aria-label="Cadastros">
          <Users className="w-5 h-5" />
          <span className="text-[11px] font-semibold uppercase tracking-wider">Cadastros</span>
        </NavLink>
      )}
      {canSeeAdmin(user) && (
        <NavLink to="/admin" className={itemClass('/admin')} aria-label="Admin">
          <ShieldCheck className="w-5 h-5" />
          <span className="text-[11px] font-semibold uppercase tracking-wider">Admin</span>
        </NavLink>
      )}
      <button
        onClick={logout}
        aria-label="Sair"
        className="flex flex-col items-center gap-0.5 min-w-[44px] min-h-[44px] justify-center px-3 text-muted-3 active:text-ink transition-colors"
      >
        <LogOut className="w-5 h-5" />
        <span className="text-[11px] font-semibold uppercase tracking-wider">Sair</span>
      </button>
    </nav>
  )
}

// ── Desktop Nav ───────────────────────────────────────────────────────────────

function Nav() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [showProfile, setShowProfile] = useState(false)
  const [showNotifs, setShowNotifs] = useState(false)
  const { data: notifications = [] } = useNotifications(Boolean(user))
  const markRead = useMarkNotificationRead()
  const cartUnits = countCartUnits(useCartQuantities(user?.id, user?.active_market))
  // Bloco 95: Dashboard é um módulo isolado, sem o cabeçalho padrão do app.
  if (location.pathname.startsWith('/dashboard')) return null

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `nav-link ${isActive ? 'nav-link-active' : ''}`

  if (!user) return null

  const unreadCount = notifications.filter(n => !n.is_read).length
  const marketName = user.active_market === 'EU' ? 'PORTUGAL' : 'BRASIL'
  const marketNameColor = user.active_market === 'EU' ? '#C8102E' : '#08783f'

  return (
    <>
      <nav className="bg-white/80 backdrop-blur-md border-b border-line px-4 md:px-6 py-3 flex items-center justify-between sticky top-0 z-40" aria-label="Navegação principal">
        <div className="flex items-center gap-1">
          <div
            className="mr-3 whitespace-nowrap text-sm font-semibold tracking-widest text-ink sm:mr-5 sm:text-base"
            style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}
          >
            ILYA <span className="text-xs font-semibold tracking-[0.08em] sm:text-sm" style={{ color: marketNameColor }}>— {marketName}</span>
          </div>
          {!user.must_change_password && (
            <div className="hidden md:flex items-center gap-1">
              {canSeeCadastros(user) && <NavLink to="/cadastros" className={linkClass} aria-label="Cadastros">Cadastros</NavLink>}
              <NavLink to="/produtos" className={linkClass} aria-label="Produtos">Produtos</NavLink>
              {canSeeOrcamentoPedidos(user) && (
              <NavLink to="/orcamentos" className={linkClass} aria-label={cartUnits > 0 ? `Novo Orçamento, ${cartUnits} itens` : 'Novo Orçamento'}>
                Novo Orçamento
                {cartUnits > 0 && (
                  <span className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-gold text-white text-[10px] font-bold tabular-nums align-middle">
                    {cartUnits > 99 ? '99+' : cartUnits}
                  </span>
                )}
              </NavLink>
            )}
              {canSeeOrcamentoPedidos(user) && <NavLink to="/pedidos" className={linkClass} aria-label="Pedidos">Pedidos</NavLink>}
              {canSeeAdmin(user) && <NavLink to="/admin" className={linkClass} aria-label="Admin">Admin</NavLink>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 md:gap-4 text-xs">
          <MarketSwitcher />
          <div className="relative">
            <button
              onClick={() => setShowNotifs(v => !v)}
              className="relative min-w-11 min-h-11 inline-flex items-center justify-center text-muted-2 hover:text-gold transition-colors"
              title="Notificações"
              aria-label={unreadCount > 0 ? `Notificações, ${unreadCount} não lidas` : 'Notificações'}
            >
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-gold text-white text-[9px] font-bold flex items-center justify-center">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </button>
            {showNotifs && (
              <div className="absolute right-0 top-full mt-2 w-80 bg-white border border-line rounded-xl shadow-lg z-50 overflow-hidden">
                <div className="px-4 py-2.5 border-b border-line flex items-center justify-between">
                  <span className="text-xs font-semibold text-ink uppercase tracking-wider">Notificações</span>
                  <button onClick={() => setShowNotifs(false)} className="text-muted hover:text-ink text-lg leading-none">&times;</button>
                </div>
                {notifications.length === 0 ? (
                  <div className="px-4 py-6 text-center text-xs text-muted">Nenhuma notificação.</div>
                ) : (
                  <ul className="divide-y divide-bg-2 max-h-72 overflow-y-auto">
                    {notifications.map(n => (
                      <li
                        key={n.id}
                        className="px-4 py-3 hover:bg-gold-wash cursor-pointer transition-colors"
                        onClick={() => { markRead.mutate(n.id); setShowNotifs(false) }}
                      >
                        <p className="text-xs text-ink">{n.message}</p>
                        <p className="text-[10px] text-muted-3 mt-0.5">
                          {new Date(n.created_at).toLocaleString('pt-BR')}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
          <button
            onClick={() => setShowProfile(true)}
            className="min-h-11 px-1 text-right hover:opacity-70 transition-opacity cursor-pointer"
            aria-label={`Abrir perfil de ${user.full_name}`}
          >
            <span className="block font-medium text-ink max-w-[120px] md:max-w-none truncate">{user.full_name}</span>
            <span className="hidden sm:block text-[10px] uppercase tracking-wider text-gold/80">{user.role}</span>
          </button>
          <button
            onClick={logout}
            className="hidden md:block text-muted-2 hover:text-ink border border-line hover:border-ink px-3 py-1 rounded transition text-xs font-medium uppercase tracking-wider"
          >
            Sair
          </button>
        </div>
      </nav>
      {showProfile && <ProfileModal onClose={() => setShowProfile(false)} />}
    </>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

function RouteFallback() {
  const { user } = useAuth()
  return <MarketTransition market={user?.active_market ?? 'BR'} />
}

export default function PrivateApp() {
  const location = useLocation()
  const { user } = useAuth()
  return (
    <QueryClientProvider client={queryClient}>
      <div data-market={user?.active_market ?? 'BR'} className="min-h-screen">
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[200] focus:bg-white focus:text-ink focus:px-4 focus:py-2 focus:rounded-lg focus:shadow-lg focus:text-sm focus:font-medium"
          >
            Pular para o conteúdo
          </a>
          <Nav />
          <main id="main-content">
            <ErrorBoundary resetKey={location.pathname}>
            <Suspense fallback={<RouteFallback />}>
              <Routes>
                  <Route path="/trocar-senha" element={<TrocarSenhaPage />} />
                  <Route
                    path="/cadastros"
                    element={
                      <RoleGuard allowed={canSeeCadastros}>
                        <CadastroPage />
                      </RoleGuard>
                    }
                  />
                  <Route path="/produtos" element={<ProdutosPage />} />
                  <Route
                    path="/orcamentos"
                    element={
                      <RoleGuard allowed={canSeeOrcamentoPedidos}>
                        <OrcamentoPage />
                      </RoleGuard>
                    }
                  />
                  <Route
                    path="/pedidos"
                    element={
                      <RoleGuard allowed={canSeeOrcamentoPedidos}>
                        <PedidosPage />
                      </RoleGuard>
                    }
                  />
                  <Route
                    path="/admin"
                    element={
                      <RoleGuard allowed={canSeeAdmin}>
                        <AdminPage />
                      </RoleGuard>
                    }
                  />
                  <Route
                    path="/dashboard"
                    element={
                      <RoleGuard allowed={canSeeDashboard}>
                        <DashboardPage />
                      </RoleGuard>
                    }
                  />
              </Routes>
            </Suspense>
            </ErrorBoundary>
          </main>
          <BottomNav />
          <DashboardFabGate />
      </div>
    </QueryClientProvider>
  )
}
