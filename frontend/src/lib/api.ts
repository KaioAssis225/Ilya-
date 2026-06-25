import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Injetado pelo AuthProvider após montar — evita dependência circular
let _getAccessToken: (() => string | null) | null = null
let _refreshSession: (() => Promise<string | null>) | null = null

export function bindAuthHandlers(
  getToken: () => string | null,
  refresh: () => Promise<string | null>
) {
  _getAccessToken = getToken
  _refreshSession = refresh
}

api.interceptors.request.use((config) => {
  const token = _getAccessToken?.()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
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
