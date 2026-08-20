import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'

import { AuthProvider, type AuthUser } from './contexts/AuthContext'
import { useAuth } from './hooks/useAuth'
import { ELECTRONIC_SIGNATURES_ENABLED } from './lib/features'
import LoginPage from './pages/LoginPage'
import { DEMO_MODE } from './lib/demo'
import { MarketTransition } from './components/MarketTransition'
import type { MarketCode } from './components/MarketFlag'

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
    const storedMarket = sessionStorage.getItem('ilya-active-market')
    return <MarketTransition market={storedMarket === 'EU' ? 'EU' : 'BR'} />
  }

  if (!user) return <Navigate to="/login" replace />
  if (user.must_change_password && location.pathname !== '/trocar-senha') {
    return <Navigate to="/trocar-senha" replace />
  }
  return <Outlet />
}

function RouteFallback() {
  const { user } = useAuth()
  const storedMarket = sessionStorage.getItem('ilya-active-market')
  const market: MarketCode = user?.active_market ?? (storedMarket === 'EU' ? 'EU' : 'BR')
  return <MarketTransition market={market} />
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
