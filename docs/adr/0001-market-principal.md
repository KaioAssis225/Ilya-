# ADR 0001 — Principal de mercado por requisição

- Status: aceito para implementação incremental
- Data: 2026-08-21
- Escopo: autenticação e isolamento Brasil/Portugal

## Contexto

O mercado ativo é parte da autorização, não uma preferência visual. Hoje ele é
extraído do token, gravado dinamicamente no objeto ORM `User`, copiado para
`Session.info` e inferido por helpers com fallback para `home_market` ou `BR`.
Essa distribuição já produziu dois incidentes: reutilização de critério ORM
entre mercados e exibição temporária do cache de outra sessão.

## Decisão

Cada requisição autenticada terá um `MarketPrincipal` imutável contendo:

- o usuário autenticado;
- o código de mercado validado a partir do token;
- moeda, locale e rótulo fiscal do mercado;
- a operação interna que vincula o mesmo código à sessão ORM.

Após a validação do token, nenhum código pode inferir mercado por IP, query,
header, `home_market` ou fallback BR. Rotas recebem o principal pela injeção de
dependência e usam `principal.market.code` explicitamente. Adaptadores antigos
podem coexistir somente durante a migração incremental.

## Invariantes

1. O mercado vem do access token e precisa constar nos vínculos autorizados.
2. A sessão ORM e as rotas observam exatamente o mesmo mercado.
3. IDs comerciais de outro mercado respondem como inexistentes.
4. Admin acessa outro mercado apenas por troca explícita.
5. Telas operacionais nunca misturam mercados.
6. Moeda, locale e imposto derivam do principal ou de snapshots históricos.

## Consequências

- Positiva: fonte única e tipada para autorização e contexto regional.
- Positiva: testes podem construir um principal sem mutar `User`.
- Negativa: rotas precisam ser migradas em etapas; haverá uma janela curta de
  compatibilidade com os helpers antigos.
- Rejeitado: remover filtros explícitos e depender apenas do evento ORM. O
  evento permanece defesa em profundidade, não fonte exclusiva de segurança.

## Verificação e rollback

Cada grupo de rotas será migrado em commit isolável. A suíte deve cobrir troca
BR/EU, IDOR, login/refresh/logout e criação/leitura de dados. O rollback consiste
em reverter somente o grupo migrado, mantendo o principal compatível.
