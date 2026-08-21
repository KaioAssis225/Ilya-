import axios from 'axios'

// Mantém as chamadas no mesmo domínio do frontend. Em desenvolvimento, o Vite
// encaminha /api para o backend local; em produção, a Vercel encaminha /api/v1
// ao Railway. Assim, uma falha de DNS do Railway no computador do cliente não
// impede login, refresh de sessão ou demais operações da aplicação.
const API_BASE_URL = '/api/v1'

const baseConfig = {
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,  // envia Cookie HttpOnly do refresh token automaticamente
}

const api = axios.create(baseConfig)

// Instância "crua" para o fluxo de autenticação (login/refresh/me/logout) e
// endpoints públicos de assinatura. Sem interceptors: a `api` acima chama
// _refreshSession() em qualquer 401, o que criaria uma promise circular se o
// próprio refresh (chamado aqui) também passasse por esse interceptor.
export const authApi = axios.create(baseConfig)

// Injetado pelo AuthProvider após montar — evita dependência circular
let _getAccessToken: (() => string | null) | null = null
let _refreshSession: (() => Promise<string | null>) | null = null
let _privateSessionGeneration = 0
let _privateSessionController = new AbortController()

type ScopedRequest = {
  _ilyaSessionGeneration?: number
}

/**
 * Fecha a fronteira HTTP da identidade anterior.
 *
 * Requisições privadas em andamento são abortadas e respostas tardias são
 * rejeitadas, impedindo que um resultado antigo alimente a interface nova.
 */
export function rotatePrivateApiSession() {
  _privateSessionController.abort()
  _privateSessionController = new AbortController()
  _privateSessionGeneration += 1
}

export function bindAuthHandlers(
  getToken: () => string | null,
  refresh: () => Promise<string | null>
) {
  _getAccessToken = getToken
  _refreshSession = refresh
}

api.interceptors.request.use((config) => {
  const scoped = config as typeof config & ScopedRequest
  scoped._ilyaSessionGeneration = _privateSessionGeneration
  if (!config.signal) config.signal = _privateSessionController.signal
  const token = _getAccessToken?.()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => {
    const scoped = res.config as typeof res.config & ScopedRequest
    if (scoped._ilyaSessionGeneration !== _privateSessionGeneration) {
      return Promise.reject(new axios.CanceledError('Sessão substituída.'))
    }
    return res
  },
  async (error) => {
    const original = error.config as (typeof error.config & ScopedRequest) | undefined
    if (
      axios.isCancel(error)
      || !original
      || original._ilyaSessionGeneration !== _privateSessionGeneration
    ) {
      return Promise.reject(error)
    }
    if (error.response?.status === 401 && !original._retry && _refreshSession) {
      original._retry = true
      const newToken = await _refreshSession()
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      }
    }
    return Promise.reject(error)
  }
)

export default api
