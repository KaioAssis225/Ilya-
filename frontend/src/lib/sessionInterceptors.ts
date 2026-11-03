import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

type ScopedRequest = InternalAxiosRequestConfig & {
  _sessionGeneration?: number
  _sessionRetry?: boolean
}

export function bindSessionInterceptors(client: AxiosInstance, cancellationMessage: string) {
  let getAccessToken: (() => string | null) | null = null
  let refreshSession: (() => Promise<string | null>) | null = null
  let generation = 0
  let controller = new AbortController()

  function rotate() {
    controller.abort()
    controller = new AbortController()
    generation += 1
  }

  function bind(
    tokenGetter: () => string | null,
    refresh: () => Promise<string | null>,
  ) {
    getAccessToken = tokenGetter
    refreshSession = refresh
  }

  client.interceptors.request.use((config) => {
    const scoped = config as ScopedRequest
    scoped._sessionGeneration = generation
    if (!config.signal) config.signal = controller.signal
    const token = getAccessToken?.()
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  client.interceptors.response.use(
    (response) => {
      const scoped = response.config as ScopedRequest
      if (scoped._sessionGeneration !== generation) {
        return Promise.reject(new axios.CanceledError(cancellationMessage))
      }
      return response
    },
    async (error) => {
      const original = error.config as ScopedRequest | undefined
      if (
        axios.isCancel(error)
        || !original
        || original._sessionGeneration !== generation
      ) {
        return Promise.reject(error)
      }
      if (error.response?.status === 401 && !original._sessionRetry && refreshSession) {
        original._sessionRetry = true
        const token = await refreshSession()
        if (token) {
          original.headers.Authorization = `Bearer ${token}`
          return client(original)
        }
      }
      return Promise.reject(error)
    },
  )

  return { rotate, bind }
}
