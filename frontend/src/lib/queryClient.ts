import { QueryClient } from '@tanstack/react-query'

/** Um cache novo e exclusivo para cada combinação de usuário e mercado. */
export function createPrivateQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, retry: 1 },
    },
  })
}

/** Cancela trabalho pendente antes de descartar um escopo privado. */
export function disposePrivateQueryClient(client: QueryClient) {
  void client.cancelQueries()
  client.clear()
}
