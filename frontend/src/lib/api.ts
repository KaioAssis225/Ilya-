import axios from 'axios'
import { bindSessionInterceptors } from './sessionInterceptors'

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

// Instância "crua" para o fluxo de autenticação (login/refresh/me/logout).
// Sem interceptors: a `api` acima chama
// _refreshSession() em qualquer 401, o que criaria uma promise circular se o
// próprio refresh (chamado aqui) também passasse por esse interceptor.
export const authApi = axios.create(baseConfig)

const { rotate, bind } = bindSessionInterceptors(api, 'Sessão substituída.')
export { rotate as rotatePrivateApiSession, bind as bindAuthHandlers }

export default api
