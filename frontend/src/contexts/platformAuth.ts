import { createContext } from 'react'

export type PlatformCapability = 'platform_admin' | 'activate_market' | 'read_outbox'

export interface PlatformUser {
  id: string
  email: string
  full_name: string
  scope: 'platform'
  capabilities: PlatformCapability[]
}

export interface PlatformAuthValue {
  user: PlatformUser | null
  accessToken: string | null
  isLoading: boolean
  login: (identifier: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshSession: () => Promise<string | null>
}

export const PlatformAuthContext = createContext<PlatformAuthValue | null>(null)
