import axios from 'axios'
import { bindSessionInterceptors } from './sessionInterceptors'

const baseConfig = {
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
}

export const platformAuthApi = axios.create(baseConfig)
const platformApi = axios.create(baseConfig)

const { rotate, bind } = bindSessionInterceptors(platformApi, 'Sessão de plataforma substituída.')
export { rotate as rotatePlatformApiSession, bind as bindPlatformAuthHandlers }

export default platformApi
