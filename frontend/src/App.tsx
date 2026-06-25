import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './contexts/AuthContext'
import { useAuth } from './hooks/useAuth'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import CadastroPage from './pages/CadastroPage'
import OrcamentoPage from './pages/OrcamentoPage'
import PedidosPage from './pages/PedidosPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

function Nav() {
  const { user, logout } = useAuth()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `nav-link ${isActive ? 'nav-link-active' : ''}`

  if (!user) return null

  return (
    <nav className="bg-stone-900/95 backdrop-blur border-b border-stone-800 px-6 py-3 flex items-center justify-between sticky top-0 z-40">
      <div className="flex items-center gap-1">
        <h1
          className="text-base font-semibold tracking-widest mr-5 text-stone-100"
          style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}
        >
          ILYA <span className="text-yellow-400 text-sm font-normal tracking-normal">— Sistema</span>
        </h1>
        <NavLink to="/cadastros" className={linkClass}>Cadastros</NavLink>
        <NavLink to="/orcamentos" className={linkClass}>Novo Orçamento</NavLink>
        <NavLink to="/pedidos" className={linkClass}>Pedidos</NavLink>
      </div>
      <div className="flex items-center gap-4 text-xs">
        <div className="text-stone-400 text-right">
          <span className="block font-medium text-stone-200">{user.full_name}</span>
          <span className="block text-[10px] uppercase tracking-wider text-yellow-500/80">{user.role}</span>
        </div>
        <button
          onClick={logout}
          className="text-stone-400 hover:text-white border border-stone-700 hover:border-stone-500 px-3 py-1 rounded transition text-xs font-medium uppercase tracking-wider"
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
              <Route path="/" element={<Navigate to="/cadastros" replace />} />
              <Route path="/cadastros" element={<CadastroPage />} />
              <Route path="/orcamentos" element={<OrcamentoPage />} />
              <Route path="/pedidos" element={<PedidosPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
