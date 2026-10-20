# PARECER CONDICIONAL — FAMÍLIA P14 (P14a–P14d)

**Estado da família P14 (P14a, P14b, P14c, P14d): AGUARDANDO EVIDÊNCIA EMPÍRICA (P12/P13). Nenhuma alteração em código de produção, cache, índice, pool ou migration foi aplicada.**

Este documento consolida o parecer técnico condicional da família P14. Cada subitem descreve o contrato atual preservado, o desenho técnico condicionado e o critério objetivo de decisão que precisa ser satisfeito por evidência empírica (P12 — perfil de latência autenticada; P13 — capacidade e saturação de pool/CPU) antes de qualquer implementação. Nenhuma linha de código de produção, cache, índice, pool ou migration foi alterada por este parecer.

---

## 1. P14a — CEP (ViaCEP) e Código Postal PT (GeoAPI / Zippopotam)

### 1.1 Parecer atual

**Aguardando evidência de P12** (p95, taxa de erro e frequência de uso) para os endpoints:

- `GET /api/v1/utils/cep/{cep}`
- `GET /api/v1/utils/postal-code/{postal_code}`

As 3 amostras públicas iniciais coletadas **não justificam cache em produção**. Sem p95 estável, taxa de erro e frequência real de chamadas por mercado, qualquer cache seria otimização especulativa e adicionaria superfície operacional (Redis, invalidação, observabilidade) sem ganho comprovado.

### 1.2 Contrato atual preservado (`backend/app/api/routers/utils.py`)

O contrato vigente **não é alterado** por este parecer:

- **Rate limit:** `60/minute` por cliente.
- **Validação:** 422 para entrada inválida — 8 dígitos para BR (CEP), 7 dígitos para PT (código postal).
- **Provedores:** GeoAPI como primário para PT, com **fallback transparente para Zippopotam** em Portugal; ViaCEP para BR.
- **Semântica de erro:** `404` para código inexistente; `502` para falha do fornecedor externo.

### 1.3 Desenho técnico condicionado (só implementar se P12 provar gargalo)

Se e somente se P12 demonstrar p95 acima do alvo, taxa de erro relevante ou volume que justifique cache, o desenho a ser implementado é:

- **Chave de cache obrigatória por `país + mercado + código normalizado`:**
  `postal:v1:{country}:{market}:{clean_code}`
  — o segmento `market` é obrigatório para impedir vazamento entre contextos (ver `ISO-34`).
- **TTL inicial:** 24h (ajustável por configuração, nunca hardcoded).
- **Feature flag:** desligada por padrão; ativação explícita por ambiente.
- **Fallback transparente:** se o Redis falhar (timeout, conexão, erro), a requisição segue para o fornecedor externo sem degradar o contrato.
- **Proteção contra stampede:** lock curto por chave ou single-flight para evitar rajada de chamadas ao fornecedor na expiração.
- **Zero armazenamento de dados de usuário:** apenas o código normalizado e o payload público do fornecedor; nenhum identificador de cliente, IP ou sessão é persistido.

---

## 2. P14b — Listagem, Busca e Lote de Produtos

Endpoints afetados: `GET /api/v1/products`, `POST /api/v1/products/batch`.

### 2.1 Parecer atual

**Aguardando evidência de P12** e planos `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` executados em **base representativa** (mesmo seed, mesma cardinalidade, mesmas distribuições de `market_code`, `type`, `group_id`, `catalog_id`). **Nenhuma migration ou mudança de query foi aplicada.**

### 2.2 Checklist de diagnóstico SQL obrigatório antes de qualquer código

Antes de propor índice, reescrita de query ou migration, é obrigatório produzir planos para:

1. **Primeira página (`limit=20`)** com `include_total=false` **e** `include_total=true` — o custo do `COUNT` deve ser medido separadamente.
2. **Busca por `product_code`** (igualdade/exata) **e** busca textual parcial (`q`) — incluindo comportamento de `LIKE`/`ILIKE` e uso (ou não) de índice.
3. **Filtros por `type`** (via `_normalized_product_type_expression`), **`group_id`** e **`catalog_id`** — isolados e combinados.
4. **Ordenações permitidas** e **offset profundo (`skip`)** — medir degradação em `skip` alto.
5. **Consultas secundárias em `_to_market_reads`** — `ProductOptionalApplication`, `ProductPrice`/`PriceList`, `ProductMarket` — para detectar N+1 ou joins custosos.

### 2.3 Critério de decisão

Só criar índice ou alterar query se:

- o plano **comprovar** scan sequencial, sort custoso ou join ineficiente; **e**
- a comparação **antes/depois no mesmo seed** provar **redução material de p95 e/ou buffers**; **e**
- **não houver degradação de escrita** (custo de índice em `INSERT`/`UPDATE`); **e**
- o isolamento multimercado for **preservado** (`ISO-20/21/34`).

Sem os critérios simultaneamente satisfeitos, a recomendação é **não alterar**.

---

## 3. P14c — Dashboard e Agregações

Endpoint afetado: `GET /api/v1/dashboard/overview`.

### 3.1 Parecer atual

**Aguardando evidência de P12** nas janelas de **30, 180 e 365 dias** e **decisão humana sobre tolerância de defasagem (frescor)**. Sem essa decisão, não é possível definir TTL de cache nem aceitar eventual leitura de dado levemente desatualizado.

### 3.2 Decomposição das 4 consultas atuais (`backend/app/api/routers/dashboard.py`)

1. **`metrics_stmt`** — somas e contagens em `orders`, filtradas por `market_code` e `created_at`.
2. **`chart_stmt`** — série temporal agrupada por `date_trunc(granularity, timezone('UTC', created_at))`, com granularidade `day` (≤45d), `week` (≤180d), `month` (>180d).
3. **`reps_stmt`** — ranking de representantes (`outerjoin Representative`, `limit=ranking_limit`).
4. **`products_stmt`** — ranking de produtos varrendo `order_items join orders`.

### 3.3 Desenho condicionado

Se cache curto for aprovado após P12 + decisão de frescor, a chave **deve incluir obrigatoriamente**:

`(market_code, start_date, end_date, rep_id, region, ranking_limit)`

**Nunca compartilhar dados entre `BR` e `EU`** — o `market_code` na chave é requisito de isolamento (`ISO-34`). Qualquer cache que omita `market_code` ou `region` é rejeitado por padrão.

---

## 4. P14d — Pool de Conexões, Workers e Réplicas

Arquivos afetados: `backend/app/core/config.py`, `backend/startup.py`.

### 4.1 Parecer atual

**Aguardando resultado empírico de P13** demonstrando **saturação de pool ou CPU** e **confirmação de Redis compartilhado** (necessário para rate limit consistente entre workers). **Valores atuais mantidos:**

- `DB_POOL_SIZE=5`
- `DB_MAX_OVERFLOW=5`
- `WEB_CONCURRENCY=1`

Nenhum ajuste é aplicado sem P13.

### 4.2 Tabela de variáveis de controle e limites

| Variável | Papel | Observação |
|---|---|---|
| `DB_POOL_SIZE` | Conexões base do pool por worker | Aumento multiplica conexões totais por `WEB_CONCURRENCY`. |
| `DB_MAX_OVERFLOW` | Conexões extras sob pico | Soma-se ao pool base; limite superior de conexões simultâneas. |
| `DB_POOL_TIMEOUT_SECONDS` | Espera por conexão livre | Valor alto mascara saturação; valor baixo gera erro rápido. |
| `DB_POOL_RECYCLE_SECONDS` | Reciclagem de conexões | Evita conexões obsoletas atrás de proxy/pooler. |
| `DB_COMMAND_TIMEOUT_SECONDS` | Timeout de comando no cliente | Deve ser compatível com `DB_STATEMENT_TIMEOUT_MS`. |
| `DB_STATEMENT_TIMEOUT_MS` | Timeout no servidor | Protege o banco de queries patológicas. |
| `WEB_CONCURRENCY` | Workers Uvicorn | Multiplica pool total; exige Redis compartilhado para rate limit. |
| `RATE_LIMIT_STORAGE_URI` | Backend do rate limit | **Deve ser Redis compartilhado** se `WEB_CONCURRENCY > 1`. |
| `UVICORN_LIMIT_CONCURRENCY` | Concorrência máxima por worker | Limita admissão; evita fila ilimitada. |
| `UVICORN_LIMIT_MAX_REQUESTS` | Reciclagem de worker | Mitiga vazamentos; reinicia worker após N requisições. |

**Regra de consistência:** `WEB_CONCURRENCY > 1` **exige** `RATE_LIMIT_STORAGE_URI` apontando para Redis compartilhado. Caso contrário, o rate limit fica por worker e o limite efetivo é multiplicado — comportamento recusado por `startup.py`.

### 4.3 Runbook de reversão rápida

Se qualquer ajuste futuro em homologação/produção elevar timeouts ou conexões:

1. **Restaurar `WEB_CONCURRENCY=1`** (reduz imediatamente o total de conexões e elimina dependência de Redis compartilhado para rate limit).
2. **Restaurar `DB_POOL_SIZE=5`** e **`DB_MAX_OVERFLOW=5`**.
3. **Reiniciar os workers** para aplicar os valores.
4. **Verificar** métricas de pool (conexões ativas, fila de espera, timeouts) e p95 dos endpoints críticos.
5. **Registrar** o incidente e o motivo da reversão antes de qualquer nova tentativa de ajuste.

A reversão é sempre preferível a manter um ajuste cujo efeito não foi comprovado por P13.

---

**Conclusão:** a família P14 permanece **integralmente condicionada**. Nenhuma alteração em código de produção, cache, índice, pool ou migration foi aplicada. Cada subitem só avança mediante evidência empírica de P12/P13 e, no caso de P14c, decisão humana explícita sobre tolerância de frescor.
