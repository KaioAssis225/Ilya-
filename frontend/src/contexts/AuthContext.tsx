import { createContext, useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import axios from 'axios'
import { bindAuthHandlers } from '../lib/api'

export type UserRole = 'admin' | 'vendedor' | 'representante'

export interface AuthUser {
  id: string
  email: string
  full_name: string
  role: UserRole
  rep_id: string | null
  is_active: boolean
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshSession: () => Promise<string | null>
  isLoading: boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

const REFRESH_KEY = 'ilya_refresh_token'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, accessToken: null })
  const [isLoading, setIsLoading] = useState(true)
  const refreshingRef = useRef<Promise<string | null> | null>(null)

  const setSession = useCallback((accessToken: string, refreshToken: string, user: AuthUser) => {
    localStorage.setItem(REFRESH_KEY, refreshToken)
    setState({ user, accessToken })
  }, [])

  const clearSession = useCallback(() => {
    localStorage.removeItem(REFRESH_KEY)
    setState({ user: null, accessToken: null })
  }, [])

  const refreshSession = useCallback((): Promise<string | null> => {
    if (refreshingRef.current) return refreshingRef.current

    const stored = localStorage.getItem(REFRESH_KEY)
    if (!stored) return Promise.resolve(null)

    refreshingRef.current = axios
      .post<{ access_token: string; refresh_token: string }>('/api/v1/auth/refresh', {
        refresh_token: stored,
      })
      .then(async (res) => {
        const { access_token, refresh_token } = res.data
        const me = await axios.get<AuthUser>('/api/v1/auth/me', {
          headers: { Authorization: `Bearer ${access_token}` },
        })
        setSession(access_token, refresh_token, me.data)
        return access_token
      })
      .catch(() => {
        clearSession()
        return null
      })
      .finally(() => {
        refreshingRef.current = null
      })

    return refreshingRef.current
  }, [setSession, clearSession])

  // Conecta interceptores Axios com os handlers de auth
  useEffect(() => {
    bindAuthHandlers(
      () => state.accessToken,
      refreshSession
    )
  }, [state.accessToken, refreshSession])

  // Restaura sessão ao iniciar
  useEffect(() => {
    const stored = localStorage.getItem(REFRESH_KEY)
    if (!stored) {
      setIsLoading(false)
      return
    }
    refreshSession().finally(() => setIsLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await axios.post<{ access_token: string; refresh_token: string }>(
        '/api/v1/auth/login',
        { email, password }
      )
      const { access_token, refresh_token } = res.data
      const me = await axios.get<AuthUser>('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${access_token}` },
      })
      setSession(access_token, refresh_token, me.data)
    },
    [setSession]
  )

  const logout = useCallback(async () => {
    const stored = localStorage.getItem(REFRESH_KEY)
    if (stored) {
      try {
        await axios.post('/api/v1/auth/logout', { refresh_token: stored })
      } catch {
        // ignora falha de rede no logout
      }
    }
    clearSession()
  }, [clearSession])

  return (
    <AuthContext.Provider
      value={{ ...state, login, logout, refreshSession, isLoading }}
    >
      {children}
    </AuthContext.Provider>
  )
}
