import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import axios from 'axios'
import { bindPlatformAuthHandlers, platformAuthApi, rotatePlatformApiSession } from '../lib/platformApi'
import { PlatformAuthContext, type PlatformUser } from './platformAuth'

export function PlatformAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<PlatformUser | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const tokenRef = useRef<string | null>(null)
  const refreshingRef = useRef<Promise<string | null> | null>(null)
  const sessionGenerationRef = useRef(0)
  const sessionIdentityRef = useRef<string | null>(null)

  const clearSession = useCallback(() => {
    sessionGenerationRef.current += 1
    sessionIdentityRef.current = null
    tokenRef.current = null
    rotatePlatformApiSession()
    setAccessToken(null)
    setUser(null)
  }, [])

  const setSession = useCallback((token: string, identity: PlatformUser) => {
    if (sessionIdentityRef.current !== identity.id) rotatePlatformApiSession()
    sessionIdentityRef.current = identity.id
    tokenRef.current = token
    setAccessToken(token)
    setUser(identity)
  }, [])

  const refreshSession = useCallback(() => {
    if (refreshingRef.current) return refreshingRef.current
    const generation = sessionGenerationRef.current
    refreshingRef.current = platformAuthApi
      .post<{ access_token: string }>('/platform/auth/refresh')
      .then(async response => {
        if (sessionGenerationRef.current !== generation) return null
        if (response.status === 204) {
          clearSession()
          return null
        }
        const token = response.data.access_token
        const me = await platformAuthApi.get<PlatformUser>('/platform/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (sessionGenerationRef.current !== generation) return null
        setSession(token, me.data)
        return token
      })
      .catch(error => {
        if (axios.isAxiosError(error) && error.response?.status === 401) clearSession()
        return null
      })
      .finally(() => {
        refreshingRef.current = null
      })
    return refreshingRef.current
  }, [clearSession, setSession])

  useEffect(() => {
    bindPlatformAuthHandlers(() => tokenRef.current, refreshSession)
    refreshSession().finally(() => setIsLoading(false))
    return () => {
      sessionGenerationRef.current += 1
      rotatePlatformApiSession()
    }
  }, [refreshSession])

  const login = useCallback(async (identifier: string, password: string) => {
    const generation = sessionGenerationRef.current
    const response = await platformAuthApi.post<{ access_token: string }>(
      '/platform/auth/login',
      { identifier, password },
    )
    const token = response.data.access_token
    const me = await platformAuthApi.get<PlatformUser>('/platform/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (sessionGenerationRef.current !== generation) {
      throw new axios.CanceledError('Sessão de plataforma substituída.')
    }
    setSession(token, me.data)
  }, [setSession])

  const logout = useCallback(async () => {
    clearSession()
    try {
      await platformAuthApi.post('/platform/auth/logout')
    } catch {
      // A sessão local já foi encerrada.
    }
  }, [clearSession])

  return (
    <PlatformAuthContext.Provider value={{ user, accessToken, isLoading, login, logout, refreshSession }}>
      {children}
    </PlatformAuthContext.Provider>
  )
}
