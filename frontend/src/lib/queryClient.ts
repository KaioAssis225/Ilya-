import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

/**
 * Remove imediatamente todo dado carregado pela identidade anterior.
 *
 * As chaves de várias consultas são funcionais (clientes, representantes,
 * pedidos) e não carregam o ID do usuário. Portanto, manter o cache ao trocar
 * a sessão poderia renderizar por alguns instantes dados do login anterior.
 */
export function clearPrivateQueryState() {
  void queryClient.cancelQueries()
  queryClient.clear()
}
