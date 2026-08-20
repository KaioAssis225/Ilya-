import { createContext, useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import axios from 'axios'
import { authApi, bindAuthHandlers } from '../lib/api'
import { removeUnsafeLegacyCart } from '../lib/cart'
import { clearSignatureMemory, removeLegacySignatureStorage } from '../lib/signatureMemory'
import { DEMO_MODE, DEMO_USER } from '../lib/demo'
import { clearPrivateQueryState } from '../lib/queryClient'

export type UserRole = 'admin' | 'vendedor' | 'representante' | 'cadastros' | 'produtos' | 'cliente' | 'executivo'

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
  can_view_dashboard: boolean
  home_market: 'BR' | 'EU'
  active_market: 'BR' | 'EU'
  allowed_markets: Array<'BR' | 'EU'>
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
}

interface AuthContextValue extends AuthState {
  login: (identifier: string, password: string) => Promise<AuthUser>
  logout: () => Promise<void>
  refreshSession: () => Promise<string | null>
  refreshMe: () => Promise<void>
  switchMarket: (market: 'BR' | 'EU', reload?: boolean) => Promise<void>
  isLoading: boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

// O refresh token agora vive em Cookie HttpOnly — o frontend nunca o lê diretamente.
// O browser o envia automaticamente nas requisições para /api/v1/auth/*.

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(DEMO_MODE ? { user: DEMO_USER, accessToken: 'demo-token' } : { user: null, accessToken: null })
  const [isLoading, setIsLoading] = useState(!DEMO_MODE)
  const refreshingRef = useRef<Promise<string | null> | null>(null)
  // Mantém o token atual acessível de forma síncrona aos interceptores Axios,
  // evitando stale closure em bindAuthHandlers (V-F1).
  const accessTokenRef = useRef<string | null>(null)
  const sessionScopeRef = useRef<string | null>(
    DEMO_MODE ? `${DEMO_USER.id}:${DEMO_USER.active_market}` : null
  )

  const setSession = useCallback((accessToken: string, user: AuthUser) => {
    removeUnsafeLegacyCart()
    const nextScope = `${user.id}:${user.active_market}`
    if (sessionScopeRef.current !== nextScope) clearPrivateQueryState()
    sessionScopeRef.current = nextScope
    // Atualiza de forma síncrona: nenhuma requisição iniciada no mesmo frame
    // pode reutilizar o token da identidade anterior.
    accessTokenRef.current = accessToken
    sessionStorage.setItem('ilya-active-market', user.active_market)
    setState({ user, accessToken })
  }, [])

  const clearSession = useCallback(() => {
    accessTokenRef.current = null
    sessionScopeRef.current = null
    clearPrivateQueryState()
    setState({ user: null, accessToken: null })
  }, [])

  const refreshSession = useCallback((): Promise<string | null> => {
    if (refreshingRef.current) return refreshingRef.current

    refreshingRef.current = authApi
      .post<{ access_token: string }>('/auth/refresh')
      .then(async (res) => {
        if (res.status === 204) {
          clearSession()
          return null
        }
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
    removeLegacySignatureStorage()
    if (DEMO_MODE) return
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
      return me.data
    },
    [setSession]
  )

  const logout = useCallback(async () => {
    // Esconde e remove os dados privados antes da chamada de rede. Mesmo com
    // conexão lenta, a conta anterior nunca continua visível durante o logout.
    clearSignatureMemory()
    removeLegacySignatureStorage()
    clearSession()
    try {
      await authApi.post('/auth/logout')
    } catch {
      // ignora falha de rede no logout
    }
  }, [clearSession])

  const switchMarket = useCallback(async (market: 'BR' | 'EU', reload = true) => {
    if (!state.user || market === state.user.active_market) return
    const response = await authApi.post<{ access_token: string }>('/auth/switch-market', { market }, {
      headers: state.accessToken ? { Authorization: `Bearer ${state.accessToken}` } : undefined,
    })
    const me = await authApi.get<AuthUser>('/auth/me', {
      headers: { Authorization: `Bearer ${response.data.access_token}` },
    })
    setSession(response.data.access_token, me.data)
    // As queries e os carrinhos são dependentes de mercado. Recarregar elimina
    // qualquer cache visual do escopo anterior; o refresh HttpOnly preserva EU/BR.
    if (reload) window.location.reload()
  }, [state.user, state.accessToken, setSession])

  return (
    <AuthContext.Provider
      value={{ ...state, login, logout, refreshSession, refreshMe, switchMarket, isLoading }}
    >
      {children}
    </AuthContext.Provider>
  )
}
