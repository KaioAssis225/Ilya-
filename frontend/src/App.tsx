import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'

import { AuthProvider, type AuthUser } from './contexts/AuthContext'
import { useAuth } from './hooks/useAuth'
import { ELECTRONIC_SIGNATURES_ENABLED } from './lib/features'
import LoginPage from './pages/LoginPage'
import { DEMO_MODE } from './lib/demo'

const PrivateApp = lazy(() => import('./PrivateApp'))
const SignContractPage = lazy(() => import('./pages/SignContractPage'))
const PrivacyPolicyPage = lazy(() => import('./pages/PrivacyPolicyPage'))

function isClient(user: AuthUser) {
  return user.role === 'cliente' || (user.role === 'vendedor' && Boolean(user.linked_id))
}

function defaultRoute(user: AuthUser) {
  if (user.role === 'executivo') return '/dashboard'
  if (user.role === 'representante') return '/orcamentos'
  if (!isClient(user)) return '/cadastros'
  return '/orcamentos'
}

function RootPage() {
  const { user } = useAuth()
  return user ? <Navigate to={DEMO_MODE ? '/produtos?demo=1' : defaultRoute(user)} replace /> : <LoginPage />
}

function PrivateGate() {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg" role="status">
        <span className="text-sm tracking-widest uppercase text-muted-2">Carregando…</span>
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />
  if (user.must_change_password && location.pathname !== '/trocar-senha') {
    return <Navigate to="/trocar-senha" replace />
  }
  return <Outlet />
}

function RouteFallback() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center" role="status">
      <span className="sr-only">Carregando…</span>
      <div className="w-8 h-8 rounded-full border-2 border-gold/25 border-t-gold animate-spin" aria-hidden="true" />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<RootPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/sign-contract"
              element={ELECTRONIC_SIGNATURES_ENABLED ? <SignContractPage /> : <Navigate to="/login" replace />}
            />
            <Route path="/privacy-policy" element={<PrivacyPolicyPage />} />
            <Route element={<PrivateGate />}>
              <Route path="/*" element={<PrivateApp />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  )
}
