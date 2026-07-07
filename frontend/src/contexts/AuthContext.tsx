import { createContext, useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import axios from 'axios'
import { authApi, bindAuthHandlers } from '../lib/api'

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
  max_discount: number
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
  // Mantém o token atual acessível de forma síncrona aos interceptores Axios,
  // evitando stale closure em bindAuthHandlers (V-F1).
  const accessTokenRef = useRef<string | null>(null)

  const setSession = useCallback((accessToken: string, user: AuthUser) => {
    setState({ user, accessToken })
  }, [])

  const clearSession = useCallback(() => {
    setState({ user: null, accessToken: null })
  }, [])

  const refreshSession = useCallback((): Promise<string | null> => {
    if (refreshingRef.current) return refreshingRef.current

    refreshingRef.current = authApi
      .post<{ access_token: string }>('/auth/refresh')
      .then(async (res) => {
        const { access_token } = res.data
        const me = await authApi.get<AuthUser>('/auth/me', {
          headers: { Authorization: `Bearer ${access_token}` },
        })
        setSession(access_token, me.data)
        return access_token
      })
      .catch((err) => {
        // Só encerra a sessão em falha de autenticação real (401). Erros de rede /
        // 5xx são transitórios e não devem deslogar o usuário (V-M3).
        if (axios.isAxiosError(err) && err.response?.status === 401) {
          clearSession()
        } else {
          if (import.meta.env.DEV) console.error('Falha ao renovar sessão (sessão preservada):', err)
        }
        return null
      })
      .finally(() => {
        refreshingRef.current = null
      })

    return refreshingRef.current
  }, [setSession, clearSession])

  // Mantém o ref sincronizado com o token corrente.
  useEffect(() => {
    accessTokenRef.current = state.accessToken
  }, [state.accessToken])

  // Conecta interceptores Axios uma única vez — o getter lê sempre o token atual via ref.
  useEffect(() => {
    bindAuthHandlers(
      () => accessTokenRef.current,
      refreshSession
    )
  }, [refreshSession])

  // Tenta restaurar sessão ao montar via cookie HttpOnly
  useEffect(() => {
    refreshSession().finally(() => setIsLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const refreshMe = useCallback(async () => {
    const token = state.accessToken
    if (!token) return
    try {
      const me = await authApi.get<AuthUser>('/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      setState((s) => ({ ...s, user: me.data }))
    } catch (err) {
      // Não propaga: callers (ex.: troca de senha) não devem exibir erro falso (V-M6).
      if (import.meta.env.DEV) console.error('Falha ao atualizar dados do usuário:', err)
    }
  }, [state.accessToken])

  const login = useCallback(
    async (identifier: string, password: string) => {
      const res = await authApi.post<{ access_token: string }>(
        '/auth/login',
        { identifier, password }
      )
      const { access_token } = res.data
      const me = await authApi.get<AuthUser>('/auth/me', {
        headers: { Authorization: `Bearer ${access_token}` },
      })
      setSession(access_token, me.data)
    },
    [setSession]
  )

  const logout = useCallback(async () => {
    try {
      await authApi.post('/auth/logout')
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
