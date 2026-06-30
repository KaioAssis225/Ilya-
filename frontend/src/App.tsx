import { BrowserRouter, Routes, Route, Navigate, NavLink, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LayoutGrid, ShoppingCart, ClipboardList, Users, ShieldCheck, LogOut } from 'lucide-react'
import { AuthProvider } from './contexts/AuthContext'
import { useAuth } from './hooks/useAuth'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import CadastroPage from './pages/CadastroPage'
import OrcamentoPage from './pages/OrcamentoPage'
import PedidosPage from './pages/PedidosPage'
import ProdutosPage from './pages/ProdutosPage'
import AdminPage from './pages/AdminPage'
import TrocarSenhaPage from './pages/TrocarSenhaPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

function BottomNav() {
  const { user, logout } = useAuth()
  const location = useLocation()
  if (!user || user.must_change_password) return null

  const active = (path: string) => location.pathname.startsWith(path)

  const itemClass = (path: string) =>
    `flex flex-col items-center gap-0.5 min-w-[44px] min-h-[44px] justify-center px-3 transition-colors ${
      active(path) ? 'text-[#8b6914]' : 'text-[#a89a8e]'
    }`

  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white/90 backdrop-blur-md border-t border-[#e8e0d6] flex items-center justify-around px-2 pb-safe">
      <NavLink to="/produtos" className={itemClass('/produtos')}>
        <LayoutGrid className="w-5 h-5" />
        <span className="text-[9px] font-semibold uppercase tracking-wider">Produtos</span>
      </NavLink>
      <NavLink to="/orcamentos" className={itemClass('/orcamentos')}>
        <ShoppingCart className="w-5 h-5" />
        <span className="text-[9px] font-semibold uppercase tracking-wider">Orçamento</span>
      </NavLink>
      <NavLink to="/pedidos" className={itemClass('/pedidos')}>
        <ClipboardList className="w-5 h-5" />
        <span className="text-[9px] font-semibold uppercase tracking-wider">Pedidos</span>
      </NavLink>
      {user.role !== 'cliente' && (
        <NavLink to="/cadastros" className={itemClass('/cadastros')}>
          <Users className="w-5 h-5" />
          <span className="text-[9px] font-semibold uppercase tracking-wider">Cadastros</span>
        </NavLink>
      )}
      {user.role === 'admin' && (
        <NavLink to="/admin" className={itemClass('/admin')}>
          <ShieldCheck className="w-5 h-5" />
          <span className="text-[9px] font-semibold uppercase tracking-wider">Admin</span>
        </NavLink>
      )}
      <button
        onClick={logout}
        className="flex flex-col items-center gap-0.5 min-w-[44px] min-h-[44px] justify-center px-3 text-[#a89a8e] active:text-[#2c2420] transition-colors"
      >
        <LogOut className="w-5 h-5" />
        <span className="text-[9px] font-semibold uppercase tracking-wider">Sair</span>
      </button>
    </nav>
  )
}

function Nav() {
  const { user, logout } = useAuth()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `nav-link ${isActive ? 'nav-link-active' : ''}`

  if (!user) return null

  return (
    <nav className="bg-white/80 backdrop-blur-md border-b border-[#e8e0d6] px-4 md:px-6 py-3 flex items-center justify-between sticky top-0 z-40">
      <div className="flex items-center gap-1">
        <h1
          className="text-base font-semibold tracking-widest mr-5 text-[#2c2420]"
          style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}
        >
          ILYA <span className="text-[#8b6914] text-sm font-normal tracking-normal hidden sm:inline">— Sistema</span>
        </h1>
        {!user.must_change_password && (
          <div className="hidden md:flex items-center gap-1">
            <NavLink to="/cadastros" className={linkClass}>Cadastros</NavLink>
            <NavLink to="/produtos" className={linkClass}>Produtos</NavLink>
            <NavLink to="/orcamentos" className={linkClass}>Novo Orçamento</NavLink>
            <NavLink to="/pedidos" className={linkClass}>Pedidos</NavLink>
            {user.role === 'admin' && (
              <NavLink to="/admin" className={linkClass}>Admin</NavLink>
            )}
          </div>
        )}
      </div>
      <div className="flex items-center gap-3 md:gap-4 text-xs">
        <div className="text-[#8a7a6e] text-right">
          <span className="block font-medium text-[#2c2420] max-w-[120px] md:max-w-none truncate">{user.full_name}</span>
          <span className="hidden sm:block text-[10px] uppercase tracking-wider text-[#8b6914]/80">{user.role}</span>
        </div>
        <button
          onClick={logout}
          className="hidden md:block text-[#8a7a6e] hover:text-[#2c2420] border border-[#e8e0d6] hover:border-[#2c2420] px-3 py-1 rounded transition text-xs font-medium uppercase tracking-wider"
        >
          Sair
        </button>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Nav />
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/trocar-senha" element={<TrocarSenhaPage />} />
              <Route path="/" element={<Navigate to="/cadastros" replace />} />
              <Route path="/cadastros" element={<CadastroPage />} />
              <Route path="/produtos" element={<ProdutosPage />} />
              <Route path="/orcamentos" element={<OrcamentoPage />} />
              <Route path="/pedidos" element={<PedidosPage />} />
              <Route path="/admin" element={<AdminPage />} />
            </Route>
          </Routes>
          <BottomNav />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
