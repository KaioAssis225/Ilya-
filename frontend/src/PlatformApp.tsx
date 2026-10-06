import { Navigate, Route, Routes } from 'react-router'
import { usePlatformAuth } from './hooks/usePlatformAuth'
import PlatformLoginPage from './pages/PlatformLoginPage'
import PlatformPage from './pages/PlatformPage'

export default function PlatformApp() {
  const { user, isLoading } = usePlatformAuth()
  if (isLoading) return <div className="min-h-screen bg-bg" />
  return (
    <Routes>
      <Route path="login" element={<PlatformLoginPage />} />
      <Route path="" element={user ? <PlatformPage /> : <Navigate to="login" replace />} />
      <Route path="*" element={<Navigate to={user ? '/platform' : '/platform/login'} replace />} />
    </Routes>
  )
}
