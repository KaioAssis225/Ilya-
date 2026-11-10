import type { AuthUser } from '../contexts/AuthContext'

/**
 * Quem vê o dashboard de Clientes (rota /clientes e aba do Dashboard BI): só
 * Portugal, porque o dado "contactado" existe apenas na ficha de lá, e só
 * operadores com acesso ao diretório de clientes (conta de cliente e
 * executivo ficam de fora). O servidor repete a regra e limita a carteira.
 */
export function canSeeClientsDashboard(user: AuthUser): boolean {
  const isClientAccount = user.role === 'cliente' || (user.role === 'vendedor' && !!user.linked_id)
  return user.active_market === 'EU' && !isClientAccount && user.role !== 'executivo'
}
