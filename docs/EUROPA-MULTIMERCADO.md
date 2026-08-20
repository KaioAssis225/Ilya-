# Ilya Brasil e Europa

## Estado da entrega

A estrutura multimercado está implementada no mesmo frontend, backend e banco.
O mercado Brasil recebe todo o legado durante a migration. O mercado Europa é
criado desativado e não fica acessível apenas porque o código foi publicado.

Para a Europa ficar operacional, duas condições independentes precisam existir:

1. `markets.is_enabled = true`, liberado pelo endpoint administrativo somente
   depois de todos os SKUs disponíveis terem Lojista, Corporativo e PVP;
2. `EUROPE_MARKET_ENABLED=true` no ambiente do backend (valor padrão após a
   importação e reconciliação inicial; use `false` como bloqueio de emergência).

Essa dupla trava permite publicar schema e código antes de publicar preços.

## Isolamento e autenticação

- `users` continua sendo a identidade central.
- `home_market` define onde a conta entra.
- `user_markets` registra os mercados concedidos pelo administrador.
- Admin possui vínculos BR e EU por padrão; a feature flag e o status do mercado
  continuam valendo.
- O access token assina `market`. O refresh token persiste `active_market`.
- `POST /api/v1/auth/switch-market` só aceita um vínculo persistido e emite um
  novo token. IP, query string e cabeçalho não selecionam mercado.
- Clientes, representantes, pedidos e notificações recebem `market_code`.
- A sessão ORM aplica o mercado ativo a leituras dessas entidades. Rotas de
  criação gravam o mercado da sessão e IDs externos retornam como inexistentes.
- Carrinho, cliente selecionado e representante selecionado usam chaves locais
  separadas por `usuário + mercado`.

## Catálogo e preços

O produto continua único: SKU, descrição, foto, dimensões, componentes e
opcionais são compartilhados. As tabelas novas são:

- `product_markets`: disponibilidade e IVA opcional por SKU/mercado;
- `price_lists`: listas pertencentes a um mercado e moeda;
- `product_prices`: preço por produto/lista;
- `market_tax_rates`: IVA padrão por tipo, usado quando o SKU não tem override.

As colunas brasileiras legadas permanecem por compatibilidade, mas criação,
edição e importação BR sincronizam as novas listas. No mercado EU, o catálogo-
base é somente leitura; disponibilidade, EUR e IVA entram pela importação EU.
`custo_desativado` não foi exposto.

## CSV Europa

Endpoint: `POST /api/v1/markets/EU/import` (admin ou cadastros).

Arquivo UTF-8 separado por ponto e vírgula:

```csv
product_code;lojista;corporativo;pvp;is_available
IML0001;55,63;72,11;103,02;true
```

O arquivo inteiro é rejeitado se houver SKU ausente/duplicado, preço vazio,
negativo ou inválido, IVA informado fora de 0–100 ou configuração incorreta das
listas. A coluna `vat_rate` é opcional: quando ausente ou vazia, a importação
copia para o SKU europeu a taxa já cadastrada no grupo do produto no Ilya. Ela
pode ser informada para sobrescrever casos específicos. A moeda é sempre EUR e
não pode ser escolhida no CSV.

Depois da conferência, `POST /api/v1/markets/EU/activate` valida cobertura das
três listas. Ainda é necessário configurar `EUROPE_MARKET_ENABLED=true` e fazer
novo deploy do backend. Para interrupção imediata, use `/EU/deactivate` ou volte
a variável para `false`.

## Pedidos e documentos

- ORC e PED usam contadores separados por mercado; o texto continua
  `ORC-0001` e `PED-0001`.
- O pedido preserva mercado, lista, moeda e locale.
- Cada item preserva preço unitário, taxa, valor do imposto, rótulo IPI/IVA e
  moeda. Mudanças futuras em tabela não reescrevem documentos anteriores.
- PDFs usam `pt-BR`/BRL/IPI no Brasil e `pt-PT`/EUR/IVA na Europa.
- Cadastro EU usa país, código postal, localidade, região opcional e VAT/Tax ID.

## Rollout seguro

1. Confirmar backup restaurável do banco.
2. Publicar com `EUROPE_MARKET_ENABLED=false`.
3. Confirmar migration `europa_multimarket_20260820` e health checks.
4. Importar uma amostra em staging e comparar preços com a fonte aprovada.
5. Importar a lista final; conferir SKUs, três listas e IVA.
6. Criar usuários EU e manter seus acessos sem uso até a abertura.
7. Chamar `/EU/activate`.
8. Configurar `EUROPE_MARKET_ENABLED=true` e redeploy.
9. Testar login EU, troca do admin, orçamento, pedido e PDF.

Rollback operacional: desativar a flag. Isso bloqueia imediatamente novos tokens
EU sem apagar dados. Rollback de schema deve ser evitado depois da primeira venda.

## Verificações automatizadas

- suíte backend existente e testes de mercado/token/permissão;
- lint e build de produção do frontend;
- CI exige uma única head Alembic;
- CI migra banco vazio e também executa `0050 -> head`;
- migration foi validada localmente em PostgreSQL 16 real.

## Decisões deliberadas

- Não há seleção geográfica por IP.
- Não há cópia do produto nem segundo sistema.
- Telas operacionais nunca comparam mercados; comparação existe somente no admin.
- A branch isolada de integração com outro sistema não faz parte desta entrega.
