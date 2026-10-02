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

export function bindPlatformAuthHandlers(
  tokenGetter: () => string | null,
  refresh: () => Promise<string | null>,
) {
  getAccessToken = tokenGetter
  refreshSession = refresh
}

platformApi.interceptors.request.use((config) => {
  const token = getAccessToken?.()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

platformApi.interceptors.response.use(
  response => response,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && original && !original._platformRetry && refreshSession) {
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
