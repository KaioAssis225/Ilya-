# ADR 0002 — Fronteira privada de sessão e cache no frontend

## Status

Aceito e implementado na branch `codex/market-principal`.

## Contexto

O frontend mantinha um `QueryClient` global e limpava seu conteúdo manualmente
durante logout e troca de mercado. Essa abordagem dependia de todos os fluxos
lembrarem da limpeza e não desmontava estados locais das páginas. Requisições
iniciadas pelo escopo anterior também poderiam terminar depois da limpeza.

Em um sistema multimercado, cache, estado React e respostas HTTP pertencem à
combinação exata de identidade e mercado autorizado.

## Decisão

- A chave da fronteira privada é `user.id + active_market`.
- Cada fronteira possui uma instância exclusiva de `QueryClient`.
- Trocar identidade ou mercado desmonta integralmente a árvore privada,
  descartando cache, mutations e estado local das páginas.
- Ao desmontar, consultas pendentes são canceladas antes da limpeza do cache.
- A camada HTTP mantém uma geração de sessão e um `AbortController` próprio.
- Trocar ou encerrar o escopo aborta requisições privadas em andamento.
- Respostas pertencentes a uma geração anterior são rejeitadas, mesmo se o
  transporte não tiver respeitado o cancelamento.
- O fluxo de autenticação usa uma instância HTTP separada e não é abortado pela
  rotação da fronteira privada.

## Invariantes

1. Dados de uma identidade nunca são renderizados pela árvore de outra.
2. Brasil e Portugal nunca compartilham uma instância de cache privado.
3. Nenhuma resposta tardia do escopo anterior pode preencher o escopo atual.
4. Logout remove a interface privada antes de aguardar a resposta de rede.
5. Renovar somente o token, sem mudar usuário ou mercado, preserva o escopo e
   não interrompe requisições válidas.

## Consequências

As query keys continuam descrevendo o recurso dentro de uma sessão, mas a
segurança não depende de cada hook repetir usuário e mercado. A troca de escopo
recarrega os dados necessários e perde estados locais transitórios por decisão
deliberada de isolamento.
