import { createContext, useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import axios from 'axios'
import { bindAuthHandlers } from '../lib/api'

export type UserRole = 'admin' | 'vendedor' | 'representante' | 'cadastros' | 'produtos'

export interface AuthUser {
  id: string
  email: string
  username: string | null
  full_name: string
  role: UserRole
  rep_id: string | null
  linked_id: string | null
  is_active: boolean
  must_change_password: boolean
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
}

interface AuthContextValue extends AuthState {
  login: (identifier: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshSession: () => Promise<string | null>
  refreshMe: () => Promise<void>
  isLoading: boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

// O refresh token agora vive em Cookie HttpOnly — o frontend nunca o lê diretamente.
// O browser o envia automaticamente nas requisições para /api/v1/auth/*.

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, accessToken: null })
  const [isLoading, setIsLoading] = useState(true)
  const refreshingRef = useRef<Promise<string | null> | null>(null)

  const setSession = useCallback((accessToken: string, user: AuthUser) => {
    setState({ user, accessToken })
  }, [])

  const clearSession = useCallback(() => {
    setState({ user: null, accessToken: null })
  }, [])

  const refreshSession = useCallback((): Promise<string | null> => {
    if (refreshingRef.current) return refreshingRef.current

    refreshingRef.current = axios
      .post<{ access_token: string }>('/api/v1/auth/refresh', null, { withCredentials: true })
      .then(async (res) => {
        const { access_token } = res.data
        const me = await axios.get<AuthUser>('/api/v1/auth/me', {
          headers: { Authorization: `Bearer ${access_token}` },
        })
        setSession(access_token, me.data)
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

  // Conecta interceptores Axios
  useEffect(() => {
    bindAuthHandlers(
      () => state.accessToken,
      refreshSession
    )
  }, [state.accessToken, refreshSession])

  // Tenta restaurar sessão ao montar via cookie HttpOnly
  useEffect(() => {
    refreshSession().finally(() => setIsLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const refreshMe = useCallback(async () => {
    const token = state.accessToken
    if (!token) return
    const me = await axios.get<AuthUser>('/api/v1/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
    setState((s) => ({ ...s, user: me.data }))
  }, [state.accessToken])

  const login = useCallback(
    async (identifier: string, password: string) => {
      const res = await axios.post<{ access_token: string }>(
        '/api/v1/auth/login',
        { identifier, password },
        { withCredentials: true }
      )
      const { access_token } = res.data
      const me = await axios.get<AuthUser>('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${access_token}` },
      })
      setSession(access_token, me.data)
    },
    [setSession]
  )

  const logout = useCallback(async () => {
    try {
      await axios.post('/api/v1/auth/logout', null, { withCredentials: true })
    } catch {
      // ignora falha de rede no logout
    }
    clearSession()
  }, [clearSession])

  return (
    <AuthContext.Provider
      value={{ ...state, login, logout, refreshSession, refreshMe, isLoading }}
    >
      {children}
    </AuthContext.Provider>
  )
}
