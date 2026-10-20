# Capacidade e Carga — P13

**Estado: gerador e orçamento preparados; nenhuma carga executada; aguardando homologação, janela autorizada e baseline P12.**

Este documento define o orçamento de conexões PostgreSQL, os patamares de rampa, a mistura de cenários, os critérios automáticos de aborto e o procedimento de execução controlada do gerador `ops/load/load_generator.py`. Nenhum resultado de execução é registrado aqui: os números de P13 só podem ser preenchidos após homologação com baseline P12 validado e janela autorizada.

---

## 1. Escopo e Pré-condições

**Escopo.** Execução do gerador de carga `ops/load/load_generator.py` contra ambiente de homologação do Ilya, com perfis A/B/C/D (e opcional E), para medir capacidade, latência p95, taxa de erro, saturação de pool e uso de conexões PostgreSQL nas configurações de referência.

**Pré-condições obrigatórias (bloqueantes):**

- **Gate P11 concluído:** identidades técnicas `benchmark_readonly` provisionadas em BR e EU, com permissões mínimas e escopo restrito a leitura. Nenhuma execução de carga é permitida antes deste gate.
- **Baseline P12 publicado:** `docs/BASELINE_AUTENTICADO_P12.md` com latências autenticadas de referência (por endpoint e por estágio) — obrigatório para os critérios de aborto comparativos (`p95 > 5 × baseline`).
- **Ambiente de homologação representativo:**
  - Mesma quantidade de workers e `WEB_CONCURRENCY`/pool da topologia alvo, ou diferença explicitamente registrada no relatório do patamar.
  - Redis compartilhado configurado em `RATE_LIMIT_STORAGE_URI` sempre que `WEB_CONCURRENCY > 1` (o backend recusa workers > 1 com `memory://`).
  - Volume de dados anonimizado e representativo da produção (mesma ordem de grandeza para produtos, pedidos, clientes, representantes).

**Bloqueio default-deny (fail-closed) no gerador:**

- `BENCHMARK_ENVIRONMENT` deve ser exatamente `homologacao` ou `staging`.
- `BENCHMARK_TARGET_URL` deve apontar para host **explicitamente listado** em `BENCHMARK_STAGING_ALLOWLIST` (hostname simples, sem esquema: `app-homolog.ilya.internal`, por exemplo).
- Esquema **HTTPS obrigatório**.
- Bloqueio absoluto de `*.up.railway.app` (qualquer rewriter/redirect) e de qualquer URL identificada como produção.

---

## 2. Orçamento Obrigatório de Conexões (PostgreSQL)

**Fórmula canônica:**

```text
conexões máximas da API = réplicas × WEB_CONCURRENCY × (DB_POOL_SIZE + DB_MAX_OVERFLOW)
```

**Padrões vigentes** (`backend/app/core/config.py` e `backend/startup.py`):

- `DB_POOL_SIZE = 5`
- `DB_MAX_OVERFLOW = 5`
- `WEB_CONCURRENCY = 1` — o backend **recusa** `WEB_CONCURRENCY > 1` quando `RATE_LIMIT_STORAGE_URI = memory://`.

**Reserva operacional mínima (obrigatória):** **10 conexões** dedicadas a:

- Migrations (`alembic upgrade head` com advisory lock `4_956_921_001` no pre-deploy);
- Observabilidade / scraper de métricas;
- Tarefas administrativas e diagnósticos pontuais.

**Tabela comparativa de orçamento** (banco de referência: 100 conexões; teto seguro de 85%):

| Configuração | Conexões API | Reserva | Total | % do banco (100) | Situação |
|---|---|---|---|---|---|
| **1 réplica × 1 worker** | 1 × 1 × (5+5) = **10** | 10 | **20** | 20% | Seguro |
| **1 réplica × 2 workers** | 1 × 2 × 10 = **20** | 10 | **30** | 30% | Seguro |
| **2 réplicas × 2 workers** | 2 × 2 × 10 = **40** | 10 | **50** | 50% | Seguro |
| **2 réplicas × 4 workers** | 2 × 4 × 10 = **80** | 10 | **90** | **90%** | **Acima do teto de 85% — não autorizado sem redimensionamento do pool** |

**Regra de bloqueio:** nenhuma carga é autorizada se o total exceder 85% da `max_connections` do PostgreSQL de homologação. Para `2×4` no banco de 100 conexões, é obrigatório reduzir `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` ou aumentar `max_connections` antes da execução.

---

## 3. Perfis e Patamares de Rampa (`ops/load/load_generator.py`)

Patamares padrão (`DEFAULT_STAGE_USERS = (1, 5, 10, 20)`):

| Patamar | Usuários virtuais | Duração | Natureza |
|---|---:|---|---|
| **A** | 1 | 60 s warm-up + 300 s sustentados | Linha de base sem concorrência |
| **B** | 5 | 60 s warm-up + 300 s sustentados | Equipe pequena |
| **C** | 10 | 60 s warm-up + 300 s sustentados | Uso concorrente normal |
| **D** | 20 | 60 s warm-up + 300 s sustentados | Pico planejado |
| **E** | 40 | 60 s warm-up + 300 s sustentados | **Condicional** (`--include-stage-40`) |

- **Warm-up descartado:** os primeiros 60 s de cada patamar são excluídos das estatísticas (aquecimento de JIT/pool/OS page cache).
- **Pacing controlado:** cada usuário virtual mantém intervalo entre requisições conforme o perfil do cenário, evitando rajadas não representativas.
- **Patamar E (=40)** só é autorizado quando:
  1. O patamar D (=20) concluiu **sem circuit breaker disparado**;
  2. Há **folga explícita** no orçamento de conexões (item 2) após reavaliar réplicas × workers;
  3. O time de operações autoriza por escrito no ticket da janela.

---

## 4. Mistura Representativa de Cenários (contratos reais)

Distribuição padrão (soma 100%):

| Grupo | Peso | Endpoint / contrato |
|---|---:|---|
| **Produtos** | 35% | `GET /api/v1/products?limit=20&include_total=false` (20%) — caminho rápido, sem `COUNT` |
|  |  | `GET /api/v1/products?limit=20&include_total=true` (15%) — caminho pesado, com `COUNT` |
| **Pedidos** | 25% | `GET /api/v1/orders?limit=20` (e detalhe por fixture sintética quando configurado) |
| **Dashboard** | 15% | `GET /api/v1/dashboard/overview?ranking_limit=5` |
| **Diretórios** | 15% | `GET /api/v1/clients?limit=20&include_total=false` (8%) |
|  |  | `GET /api/v1/representatives?limit=20` (7%) |
| **CEP / Código Postal** | 10% | `GET /api/v1/utils/cep/01001000` — **`--postal-mode simulated` por padrão** |

**Diretórios — condicionais.** Os endpoints de `clients` e `representatives` só são exercitados com `--include-directories` e após decisão formal sobre acesso sintético à massa anonimizada. Motivo: o papel `benchmark_readonly` (P11) **bloqueia diretórios por padrão**. Quando `--include-directories` é omitido:

- Os 15% de diretórios são **removidos** da mistura;
- Os 85% restantes são **reponderados proporcionalmente** (Produtos 35→41,2%, Pedidos 25→29,4%, Dashboard 15→17,6%, CEP 10→11,8%);
- A limitação é **registrada no relatório do patamar** como fator de não-cobertura.

**CEP — simulação por padrão.** `--postal-mode simulated` executa resolução local determinística (sem chamar ViaCEP / GeoAPI / Zippopotam). Motivo: isolar a capacidade interna do Ilya de dependências externas de terceiros; a latência observada mede apenas o caminho interno do serviço. O modo `--postal-mode live` só é permitido fora de janela de medição de capacidade.

---

## 5. Critérios Automáticos de Aborto (Circuit Breaker)

O gerador aborta a execução (marca stage como `ABORTED`) ao detectar qualquer condição abaixo. O aborto interrompe novas requisições e preserva os dados coletados até o instante.

1. **Taxa de erro sustentada:** `error_rate > 5%` por **120 segundos contínuos** (janela deslizante de 2 min).
2. **Degradação de latência:** `p95_stage > 5 × baseline_p95_ms` — só avaliado quando `--baseline-p95-ms` é informado (derivado de `docs/BASELINE_AUTENTICADO_P12.md`).
3. **Sinais de indisponibilidade:**
   - Falhas **5xx** ou **de rede** consecutivas acima do limiar do perfil; **ou**
   - Ausência de respostas **2xx válidas** em janela avaliada com falhas.
4. **Banco próximo do limite seguro de conexões** (via `/internal/metrics`):
   - `observed_db_connections >= safe_connection_ceiling` (85% de `max_connections`), ou
   - `pool_timeouts > 0` no intervalo de scrape.

Ao disparar circuit breaker, o gerador interrompe a progressão para os patamares seguintes e retorna código de saída não-zero.

---

## 6. Comandos de Validação e Execução Controlada

**Dry-run local, sem rede** (obrigatório antes de qualquer execução real):

```bash
python ops/load/load_generator.py --dry-run
```

Valida: parsing de argumentos, cálculo de orçamento, ponderação da mistura, checagens de allowlist (offline) e os critérios de aborto. **Não** realiza chamadas HTTP nem conecta ao banco.

**Execução em homologação.** Variáveis passadas **somente por nome** — nunca com valores secretos em documentação, commits ou logs:

| Variável | Papel | Segredo |
|---|---|---|
| `BENCHMARK_TARGET_URL` | URL HTTPS do alvo de homologação | não |
| `BENCHMARK_ENVIRONMENT` | `homologacao` ou `staging` (default-deny) | não |
| `BENCHMARK_STAGING_ALLOWLIST` | Hostname simples (sem esquema) autorizado | não |
| `ILYA_BENCHMARK_USERNAME` | Usuário técnico `benchmark_readonly` | **sim** |
| `ILYA_BENCHMARK_PASSWORD` | Senha do usuário técnico | **sim** |
| `ILYA_BENCHMARK_MARKET` | Mercado alvo (`BR` ou `EU`) | não |

Exemplo de invocação (variáveis já exportadas no shell/secret manager da janela):

```bash
python ops/load/load_generator.py \
  --baseline-p95-ms <p95-do-P12> \
  --postal-mode simulated \
  --output <artefato-privado>.json
# Patamar E, somente após D estável e folga de conexões confirmada:
python ops/load/load_generator.py --include-stage-40 --baseline-p95-ms <p95-do-P12>
# Diretórios, somente com decisão formal de acesso sintético:
python ops/load/load_generator.py --include-directories
```

---

## 7. Modelo de Relatório por Patamar e Rollback

**Relatório por patamar** (preencher apenas ao final efetivo da execução — sem dados fictícios):

```text
=== Patamar <A|B|C|D|E> — <users> usuários virtuais ===
Ambiente:          <homologacao|staging> @ <host>
Topologia:         réplicas=<N> WEB_CONCURRENCY=<M> pool=5+5
Orçamento DB:      API=<N×M×10> + reserva=10 → total=<X> (<X%> do banco)
Baseline P12 p95:  <p95_ms>  (fonte: docs/BASELINE_AUTENTICADO_P12.md)
Warm-up:           60 s (descartado)
Sustentado:        300 s
Mistura ativa:     Produtos=<%> Pedidos=<%> Dashboard=<%> Diretórios=<%|omitido> CEP=<%>
                   (--include-directories: <sim|não>; --postal-mode: <simulated|live>)
------------------------------------------------------------
requisições totais:      <N>
taxa de erro:            <pct>%
p50 / p95 / p99 (ms):    <p50> / <p95> / <p99>
throughput (req/s):      <rps>
pool_timeouts:           <N>
pico observed_db_conn:   <N>
circuit breaker:         <disparado|não> (motivo=<...>, t=<s>)
limitações registradas:  <ex.: diretórios omitidos; CEP simulado>
```

**Procedimento de rollback / contenção (em qualquer disparo de circuit breaker):**

1. **Interromper imediatamente** o gerador (o circuit breaker já bloqueia novas requisições; confirme que o processo saiu com código não-zero).
2. **Coletar evidências** antes de qualquer ação corretiva: logs sanitizados do gerador, snapshot de `/internal/metrics` (conexões, pool, latência), logs da API na janela, logs do PostgreSQL se disponíveis.
3. **Verificar saturação do banco:** se `observed_db_connections` estiver próximo de `max_connections` ou `pool_timeouts > 0`, aguardar normalização (drenagem) antes de qualquer nova tentativa.
4. **Reverter configuração de homologação** se algum parâmetro tiver sido alterado para o teste (ex.: `WEB_CONCURRENCY`, `DB_POOL_SIZE`): restaurar valores padrão e registrar a reversão no ticket da janela.
5. **Bloquear próxima execução** até que: (a) a causa raiz seja documentada; (b) o time aprove novo baseline ou ajuste no orçamento; (c) a janela seguinte seja autorizada.
6. **Registrar** o ocorrido em artefato privado de execução, com data, patamar, motivo do aborto e ações tomadas. Execuções abortadas **não** contam como resultado válido de capacidade.

---

## Referências

- `docs/BASELINE_AUTENTICADO_P12.md` — baseline autenticado obrigatório (P12).
- `backend/app/core/config.py`, `backend/startup.py` — defaults de pool e guarda de `WEB_CONCURRENCY`.
- `ops/load/load_generator.py` — gerador, mistura, orçamento e circuit breaker.
- Gate P11 — identidades `benchmark_readonly` BR/EU.
