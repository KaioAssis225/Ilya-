import axios from 'axios'

const baseConfig = {
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
}

export const platformAuthApi = axios.create(baseConfig)
const platformApi = axios.create(baseConfig)

let getAccessToken: (() => string | null) | null = null
let refreshSession: (() => Promise<string | null>) | null = null
let platformSessionGeneration = 0
let platformSessionController = new AbortController()

type ScopedPlatformRequest = {
  _platformSessionGeneration?: number
}

/** Descarta requisições e respostas pertencentes à sessão de plataforma anterior. */
export function rotatePlatformApiSession() {
  platformSessionController.abort()
  platformSessionController = new AbortController()
  platformSessionGeneration += 1
}

export function bindPlatformAuthHandlers(
  tokenGetter: () => string | null,
  refresh: () => Promise<string | null>,
) {
  getAccessToken = tokenGetter
  refreshSession = refresh
}

platformApi.interceptors.request.use((config) => {
  const scoped = config as typeof config & ScopedPlatformRequest
  scoped._platformSessionGeneration = platformSessionGeneration
  if (!config.signal) config.signal = platformSessionController.signal
  const token = getAccessToken?.()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

platformApi.interceptors.response.use(
  response => {
    const scoped = response.config as typeof response.config & ScopedPlatformRequest
    if (scoped._platformSessionGeneration !== platformSessionGeneration) {
      return Promise.reject(new axios.CanceledError('Sessão de plataforma substituída.'))
    }
    return response
  },
  async (error) => {
    const original = error.config as (typeof error.config & ScopedPlatformRequest) | undefined
    if (
      axios.isCancel(error)
      || !original
      || original._platformSessionGeneration !== platformSessionGeneration
    ) {
      return Promise.reject(error)
    }
    if (error.response?.status === 401 && !original._platformRetry && refreshSession) {
      original._platformRetry = true
      const token = await refreshSession()
      if (token) {
        original.headers.Authorization = `Bearer ${token}`
        return platformApi(original)
      }
    }
    return Promise.reject(error)
  },
)

export default platformApi
