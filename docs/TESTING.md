# TESTING.md — Guia de testes do Ilya

**Baseline medido em:** commit `f4d15385` (origin/main, 15/10/2026)

**Ambiente local medido:** Windows 11 Pro, Python 3.12.10, pytest 9.1.1, pytest-cov 6.2.1, pytest-asyncio 1.4.0, Node.js v26.3.1 (drive mapeado W:)

**Ambiente CI de referência:** Python 3.12, Node.js 22, Ubuntu (GitHub Actions)

---

## 1. Comandos locais

### Backend (rodar a partir de `backend/`)

```bash
# Instalar dependências de desenvolvimento
pip install -r requirements-dev.txt

# Variáveis mínimas (sem banco real — todos os testes usam mocks)
export SECRET_KEY="local-dev-secret-key-with-at-least-32-chars"
export PASSWORD_PEPPER="local-dev-pepper"
export BACKEND_CORS_ORIGINS='["http://localhost:5173"]'
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ilya_test"

# Suíte rápida — unit + contract, sem integração (exit 0; ~17 s sem cobertura)
python -m pytest -m "not integration"

# Suíte completa incluindo integração — requer infra via docker-compose.test.yml (ver seção 1b)
# python -m pytest

# Somente testes de lógica pura
python -m pytest -m unit

# Somente contratos HTTP / schema OpenAPI
python -m pytest -m contract

# Integração — requer PostgreSQL 16 + Redis 7 reais (ver seção 1b abaixo)
# Variáveis obrigatórias: TEST_DATABASE_URL, DATABASE_URL, DEBUG=true,
# BACKEND_CORS_ORIGINS, RATE_LIMIT_STORAGE_URI (ver seção 1b para valores)

# Passo 1: cobertura baseline unit+contract (sem relatório, apenas .coverage)
python -m pytest -m "not integration" -q --cov=app --cov-report=

# Passo 2: integração com append; gera cobertura combinada
python -m pytest -m integration -q --tb=short \
    --junitxml=test-results/integration-results.xml \
    --cov=app --cov-append \
    --cov-report=xml:test-results/integration-coverage.xml

# Com cobertura de linhas e branches (sem integração — sem banco real)
python -m pytest -m "not integration" --cov=app --cov-report=xml --cov-report=term-missing
# Artefatos: backend/test-results/pytest.xml (JUnit), backend/coverage.xml (Cobertura)
```

### Frontend (rodar a partir de `frontend/` via drive mapeado, não UNC path)

```bash
# Instalar dependências
npm ci

# Lint (baseline: 46 warnings; ≤46 = exit 0, ≥47 = exit 1)
npm run lint

# Prova de regressão bloqueada: --max-warnings=45 retorna exit 1
npx oxlint --max-warnings=45

# Testes de lógica (Node test runner, sem DOM)
npm test

# Build de produção
npm run build
```

> **Atenção:** `npm run lint` e `npm test` executados via caminho UNC (`\\server\share\...`) falham
> porque CMD.EXE não suporta UNC paths e resolve para `C:\Windows`, fazendo `tsc` e `oxlint`
> operarem no diretório errado. Sempre usar drive mapeado (ex.: `W:\PROJETOENG\Ilya\...`).

---

## 1b. Testes de integração (P02) — PostgreSQL 16 real

Os testes de integração requerem o harness HTTP definido em `docker-compose.test.yml` na raiz do repositório.

### Subir infraestrutura efêmera

```bash
# A partir da raiz do repositório
docker compose -f docker-compose.test.yml up -d --wait
```

### Variáveis de ambiente necessárias (além das da seção 1)

```bash
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/ilya_test"
# DATABASE_URL sem driver (usado pelo Alembic)
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ilya_test"
# Obrigatório para switch-market em tests: cookies sem Secure e Origin confiável
export DEBUG="true"
export BACKEND_CORS_ORIGINS='["http://testserver","http://localhost:5173"]'
# Rate limiter aponta para o Redis real do docker-compose.test.yml
export RATE_LIMIT_STORAGE_URI="redis://localhost:6379/0"
```

### Executar migrations e testes

```bash
# A partir de backend/
alembic upgrade head
python -m pytest -m integration -q --tb=short
```

### Derrubar infraestrutura

```bash
docker compose -f docker-compose.test.yml down -v
```

### Arquivos adicionados no P02

| Arquivo | Propósito |
|---|---|
| `docker-compose.test.yml` | PostgreSQL 16 + Redis 7 efêmeros (tmpfs, sem volume persistente) |
| `backend/Dockerfile.test` + `backend/Dockerfile.test.dockerignore` | Imagem isolada de testes com dependências de `requirements-dev.txt`; o ignore específico inclui `tests/` sem alterar a imagem de produção |
| `backend/tests/factories/users.py` | `make_user`, `make_user_market`, `make_platform_permission` |
| `backend/tests/factories/markets.py` | `market_defaults` e `require_market` — defaults sintéticos e validação dos mercados semeados |
| `backend/tests/factories/catalog.py` | `make_catalog`, `make_price_list`, `make_client`, `make_representative` |
| `backend/tests/factories/orders.py` | `make_order` |
| `backend/tests/factories/products.py` | `make_product_group`, `make_product_type`, `make_product`, `make_product_market`, `make_product_price` |
| `backend/tests/integration/conftest.py` | Engine, `db_session` (rollback por teste), `client` (ASGI+httpx) |
| `backend/tests/integration/test_health_and_auth.py` | health, login, /auth/me contra PostgreSQL real |
| `backend/tests/integration/test_market_isolation.py` | ISO-01, ISO-03, ISO-04, ISO-05, ISO-12, ISO-23 |

---

## 2. Marcadores pytest

| Marcador | Critério | Arquivos (P01) |
|---|---|---|
| `unit` | Lógica pura; sem TestClient, sem banco real | 41 arquivos (543 testes) |
| `contract` | Usa `TestClient` HTTP ou verifica schema OpenAPI | `test_auth_csrf.py`, `test_openapi_contract.py` (15 testes) |
| `integration` | Requer PostgreSQL 16 + Redis 7 reais | 15 testes P02 (2 arquivos) |

### Divergências de contrato documentadas

| Teste | Spec (fonte) | Contrato real | Motivo |
|---|---|---|---|
| `test_iso05_commercial_user_cannot_activate_market` | 403 | **401** | `POST /api/v1/markets/EU/activate` usa `require_platform_capability` que chama `get_platform_principal`; token com `scope=market` é rejeitado com 401 antes de chegar ao gate de capacidade. A regra de negócio não foi alterada para adequar o teste — o contrato real prevalece. |

**Aplicação dos marcadores**: testes antigos (P01) sem `pytestmark` recebem marcador automático via `pytest_collection_modifyitems` em `backend/tests/conftest.py`. Testes novos de integração (P02 em `tests/integration/`) usam `pytestmark = [pytest.mark.asyncio, pytest.mark.integration]` explícito no módulo, o que tem prioridade sobre a inferência automática por caminho.

---

## 3. Baseline medido (commit f4d15385)

### Backend — ambiente local (Windows 11, Python 3.12.10)

| Métrica | Valor |
|---|---|
| Arquivos de teste | 43 |
| Testes coletados | 558 |
| Testes unitários (`-m unit`) | 543 |
| Testes de contrato (`-m contract`) | 15 |
| Testes de integração (`-m integration`) | 0 (collect-only exit 5 — esperado) |
| Resultado suíte completa | 558 passed, exit 0 |
| Tempo aproximado (sem cobertura) | ~17 s |
| Warnings pytest | **0** (filterwarnings=error; apenas 2 filtros documentados) |
| Cobertura combinada (linhas + branches) | 59% |
| line-rate (XML) | 64,03% |
| branch-rate (XML) | 36,76% |
| Statements válidos | 7 895 |
| Statements cobertos | 5 055 |
| Branches totais | 1 972 |
| Branches cobertas | 725 |
| JUnit output | `backend/test-results/pytest.xml` |
| Coverage XML (CI) | `backend/coverage.xml` |

### Backend — filtros de warning mantidos

`pytest.ini` usa `filterwarnings = error`, convertendo **qualquer** warning não filtrado em falha de teste. Apenas dois filtros de supressão estão ativos, ambos dívida técnica conhecida **ainda não corrigida**:

1. **`ignore:Using httpx with starlette.testclient is deprecated:`**
   Emitido pela própria dependência Starlette/httpx ao usar `TestClient`. Não é código nosso; exige atualização/migração de dependência em PR próprio futuro.

2. **`ignore:The noload\(\) option is deprecated:sqlalchemy.exc.SADeprecationWarning`**
   Emitido por código da aplicação (`app/`) que ainda usa `noload()` do SQLAlchemy. Será substituído pela API atual em refatoração futura.

Qualquer outro warning — de código nosso ou de novas dependências — **falhará o teste automaticamente**.

### Frontend — ambiente local (Node.js v26.3.1 via drive W:)

| Métrica | Valor |
|---|---|
| Arquivos de teste | 7 |
| Testes (Node runner) | 29 |
| Resultado | 29 pass, 0 fail, exit 0 |
| Duração | ~702 ms |
| Warnings de lint (`npm run lint`/oxlint) | 46 |
| Gate de lint | ≤ 46 (exit 0); `npx oxlint --max-warnings=45` retorna **exit 1** — regressão bloqueada |
| Build de produção (`npm run build`) | exit 0; built in ~6,5 s |

---

## 4. Configuração da cobertura

`backend/.coveragerc` define:
- `source = app` — cobre apenas o código da aplicação
- `branch = true` — cobertura de branches além de linhas
- `omit` — exclui `tests/`, `alembic/`, `__pycache__/`
- Sem `fail_under` no P01 — threshold será adicionado após P02/P03 (veja PLANO_INTEGRADO_TESTES_E_MELHORIAS_ILYA.md §7)

Caminhos de artefatos coerentes com `pytest.ini` (`--junitxml=test-results/pytest.xml`) e com o workflow CI (que grava `coverage.xml` em `backend/coverage.xml`).

---

## 5. Limitações conhecidas (P01)

1. **Sem PostgreSQL real nos testes:** todos os 558 testes usam mocks ou stubs SQLAlchemy. Sem PostgreSQL, Redis ou MinIO reais. Testes de integração real serão adicionados no P02.

2. **Python local vs. Python 3.12 no CI:** versão local (3.12.10) pode diferir do CI. O `pytest.ini` não suprime `PytestUnraisableExceptionWarning` globalmente; se ocorrer localmente, indica problema real no código de teste.

3. **SO local difere do runner CI:** o backend foi instalado a partir de `requirements-dev.txt`/`requirements.txt` localmente, mas o runner CI usa Ubuntu. Diferenças de plataforma podem gerar comportamento distinto; o CI é a confirmação final.

4. **Frontend via UNC path:** `npm run lint` e `npm test` falham quando executados via caminho UNC (`\\192.168.3.59\...`) porque CMD.EXE não suporta UNC e resolve para `C:\Windows`. Sempre usar drive mapeado (ex.: `W:\`).

5. **Cobertura de 59% é baseline, não meta:** o percentual atual reflete principalmente testes unitários e de contrato com mocks. Após P02 (integração HTTP/PostgreSQL) e P03 (componentes React), o piso subirá e um threshold será ativado.

6. **Sem threshold de cobertura no P01:** conforme o plano (§7 ponto 1), nenhum `fail_under` está configurado. O primeiro threshold entrará após P02/P03 com tolerância de 0,5 pp de não-regressão.

7. **Benchmark e arquivos de diagnóstico no baseline P01:** no commit de baseline `f4d15385`, `ops/benchmark_production_api.py` e arquivos relacionados ainda não faziam parte da suíte; foram revisados e incorporados no P04 (ver seção 7).

---

## 6. Arquivos de configuração adicionados no P01

| Arquivo | Propósito |
|---|---|
| `backend/pytest.ini` | Configuração pytest: testpaths, markers, filterwarnings, addopts (JUnit) |
| `backend/.coveragerc` | Configuração coverage.py: source, branch, omit, xml output |
| `backend/tests/conftest.py` | Aplica marcadores unit/contract via `pytest_collection_modifyitems` |

---

## 7. Ferramenta de diagnóstico e benchmark (P04 v2)

`ops/benchmark_production_api.py` (v2.0.0) é a ferramenta de diagnóstico reproduzível.

### Modos

| Modo | Amostras por origem | Warmup por origem | p95/p99 |
|---|---:|---:|---|
| `smoke` | 3 | 0 | INCONCLUSIVO |
| `baseline` | 30 válidas (2xx) | 5 | Conclusivos |
| `load` | configurável | 5 | Conclusivos se >=30 válidas |

Estatísticas são produzidas **separadamente por origem** (railway / vercel). `valid_count` e percentis contam apenas respostas **2xx**; 401/403/4xx/5xx são excluídos.

### Execução básica

```bash
# Dry-run (sem requisição real; não expõe URLs nem token)
python ops/benchmark_production_api.py --dry-run

# Smoke sem credencial
python ops/benchmark_production_api.py \
  --mode smoke \
  --target-url https://staging.example.com

# Baseline autenticado (credencial SOMENTE via env var)
export BENCHMARK_API_TOKEN="<token somente leitura>"
python ops/benchmark_production_api.py \
  --mode baseline \
  --target-url "$BENCHMARK_TARGET_URL" \
  --vercel-url "$BENCHMARK_VERCEL_URL" \
  --environment homologacao \
  --output /tmp/baseline-$(date +%Y%m%d).json
```

### Wrapper PowerShell

```powershell
# Smoke
.\ops\benchmark-production-api.ps1 -TargetUrl https://staging.example.com

# Baseline com saida em arquivo
$env:BENCHMARK_API_TOKEN = (Get-Content .benchmark-token -Raw).Trim()
.\ops\benchmark-production-api.ps1 -Mode baseline -TargetUrl https://staging.example.com -Output report.json
```

O wrapper restaura env vars ao final (sem poluir a sessão PS). `-Seed` só define `BENCHMARK_SEED` se fornecido explicitamente.

### Código de saída

| Código | Significado |
|---|---|
| 0 | Sucesso real (>=1 amostra válida 2xx, sem 5xx) |
| 1 | Falha funcional (5xx), falha total de rede/timeout, ou sem válidas (não por auth) |
| 2 | Configuração inválida ou modo load não autorizado |

### Segurança do modo load (política positiva/default-deny)

O modo `load` exige **todas** as condições:
1. `BENCHMARK_ENVIRONMENT` = `staging` ou `homologacao`
2. `BENCHMARK_STAGING_ALLOWLIST` configurado (hosts separados por vírgula)
3. `target-url` (e `vercel-url`) presentes na allowlist
4. Nenhuma URL usa `*.up.railway.app` (sempre bloqueado)

### Políticas de segurança gerais

- `Authorization`, `X-Api-Key`, `Cookie`, `Set-Cookie` redactados para `***REDACTED***`
- `--api-token` não existe; token somente via `BENCHMARK_API_TOKEN`
- Dry-run exibe `has_token: bool`, nunca o valor do token
- 401/403 → `auth_failure_count`; nunca contam como operação válida
- Erros de rede e timeout → contadores separados, fora da distribuição

### Parâmetros do modo load

| Parâmetro | Padrão | Máximo |
|---|---:|---:|
| `--load-workers` | 4 | 50 |
| `--load-stages` | 3 | 10 |
| `--load-requests` | 10 | 100 |

### Arquivos adicionados/atualizados no P04

| Arquivo | Propósito |
|---|---|
| `ops/benchmark_production_api.py` | Ferramenta principal v2: stats por origem, política load, valid_count 2xx |
| `ops/benchmark-production-api.ps1` | Wrapper PowerShell: sem ForceStaging, restaura env, não expõe URLs |
| `backend/tests/test_production_diagnostics.py` | 129 testes unitários (6 critérios + 12 regressões) |
| `docs/RELATORIO_BENCHMARK_PRODUCAO.md` | Exemplo sanitizado do formato JSON v2 e limitações |

### Limitações (P04 v2)

- Execução real requer credencial provisionada para cenários autenticados
- Modo load depende de ambiente de homologação com allowlist configurada
- p95/p99 com 30 amostras válidas são o mínimo estatístico; não declarar SLO sem >=100
- Ver `docs/RELATORIO_BENCHMARK_PRODUCAO.md` para análise completa

---

## 8. Próximos passos

- **P02:** ✓ harness HTTP com PostgreSQL real, transações por teste, factories BR/EU
- **P03:** ✓ testes de componentes React com Vitest/Testing Library/MSW
- **P04:** ✓ ferramenta de diagnóstico e benchmark reproduzível
- **P18–P20:** redução progressiva do lint 46 → 30 → 15 → 0


---

## 9. Camadas adicionais implementadas (P06–P17)

| Bloco | Camada / Ferramenta | cwd | Comando de verificação |
|---|---|---|---|
| P06 | Integração PG + MinIO (buckets BR/EU) | `backend/` | `python -m pytest tests/integration/test_media_storage.py -m integration -q --tb=short` |
| P07 | Opcionais independentes e perfis fiscais | `backend/` | `python -m pytest tests/integration/test_optional_applications_flow.py tests/integration/test_price_profiles.py -m integration -q --tb=short` |
| P08a/b | Ciclo de pedido, snapshot PDF e outbox Moloni | `backend/` | `python -m pytest tests/integration/test_order_lifecycle.py tests/integration/test_order_pdf_outbox.py -m integration -q --tb=short` |
| P09 | E2E Playwright Chromium (sem retry) | `frontend/` | `npm run test:e2e` (ver `frontend/e2e/README.md`) |
| P10 | Observabilidade Prometheus e logs correlacionados | `backend/` | `python -m pytest tests/test_observability.py -q` |
| P11 | Identidade técnica `benchmark_readonly` e canários | raiz / `backend/` | `python -m pytest ops/test_benchmark_canary.py` / `python -m pytest tests/test_benchmark_readonly.py` |
| P13 | Gerador de carga e orçamento de conexões | raiz | `python -m pytest ops/load/test_load_generator.py -q` e `python ops/load/load_generator.py --dry-run` |
| P14a–d | Controles de escalabilidade e parecer condicional | `backend/` | `python -m pytest tests/test_scalability_controls.py -q` |
| P15 | Monitor sintético autenticado e recuperação 2× | raiz | `python -m pytest ops/test_synthetic_monitor.py -q` |
| P16 | Startup (`all`, `migrate`, `serve`) e deploy | `backend/` | `python -m pytest tests/test_startup.py -q` |
| P17 | Restore sintético e verificador de integridade | raiz | `python -m pytest ops/test_restore_integrity.py -q` e `python ops/test_restore.py ops/fixtures/synthetic_restore_pg16.sql` |

### Restore sintético e alinhamento de versão PostgreSQL (P17)

- `ops/test_restore.py` valida obrigatoriamente o arquivo `.sha256` adjacente ao dump, detecta a versão principal do PostgreSQL no cabeçalho do dump (`-- Dumped from database version 16.4` → `postgres:16-alpine`; dumps PG18 → `postgres:18-alpine`; ou sobrescrita explícita por `--postgres-image` / `RESTORE_POSTGRES_IMAGE`) e executa `verify_restored_integrity`:
  1. Presença de todas as tabelas essenciais (`markets`, `users`, `user_markets`, `catalogs`, `products`, `product_markets`, `clients`, `orders`, `order_items`) no schema `public`.
  2. Contagem mínima de linhas por tabela conhecida do dataset sintético (`ops/fixtures/synthetic_restore_pg16.sql`).
  3. Verificação de 11 consultas de integridade referencial (zero órfãos em FKs) e ausência de mistura cruzada de mercado (`BR`/`EU`) entre pedidos e clientes.
- **Regra de segurança:** nunca versionar nem baixar dumps reais de produção em runners de CI; utilizar exclusivamente `ops/fixtures/synthetic_restore_pg16.sql` (com `.sha256`).
