import { BrowserRouter, Routes, Route, Navigate, NavLink, useNavigate, Outlet } from 'react-router-dom'
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

function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `nav-link ${isActive ? 'nav-link-active' : ''}`

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <nav className="bg-stone-900/95 backdrop-blur border-b border-stone-800 px-6 py-3 flex items-center gap-1 sticky top-0 z-40">
        <h1
          className="text-base font-semibold tracking-widest mr-5 text-stone-100"
          style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}
        >
          ILYA <span className="text-yellow-400 text-sm font-normal tracking-normal">— Sistema</span>
        </h1>
        <NavLink to="/cadastros" className={linkClass}>Cadastros</NavLink>
        <NavLink to="/orcamentos" className={linkClass}>Novo Orçamento</NavLink>
        <NavLink to="/pedidos" className={linkClass}>Pedidos</NavLink>

        <div className="ml-auto flex items-center gap-3">
          {user && (
            <span className="text-xs text-stone-400 tracking-wide">
              {user.full_name} <span className="text-stone-600">·</span> {user.role}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="text-xs text-stone-400 hover:text-stone-200 uppercase tracking-widest transition"
          >
            Sair
          </button>
        </div>
      </nav>
      <Outlet />
    </>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<Navigate to="/cadastros" replace />} />
                <Route path="/cadastros" element={<CadastroPage />} />
                <Route path="/orcamentos" element={<OrcamentoPage />} />
                <Route path="/pedidos" element={<PedidosPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
