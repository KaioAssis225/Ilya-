import { useContext } from 'react'
import { PlatformAuthContext } from '../contexts/platformAuth'

export function usePlatformAuth() {
  const context = useContext(PlatformAuthContext)
  if (!context) throw new Error('usePlatformAuth deve estar dentro de PlatformAuthProvider')
  return context
}
