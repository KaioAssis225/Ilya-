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

# Suíte completa (exit 0; ~17 s sem cobertura)
python -m pytest

# Somente testes de lógica pura
python -m pytest -m unit

# Somente contratos HTTP / schema OpenAPI
python -m pytest -m contract

# Integração — nenhum teste no baseline; collect-only retorna exit 5 (esperado)
python -m pytest -m integration

# Com cobertura de linhas e branches
python -m pytest --cov=app --cov-report=xml --cov-report=term-missing
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

## 2. Marcadores pytest

| Marcador | Critério | Arquivos (P01) |
|---|---|---|
| `unit` | Lógica pura; sem TestClient, sem banco real | 41 arquivos (543 testes) |
| `contract` | Usa `TestClient` HTTP ou verifica schema OpenAPI | `test_auth_csrf.py`, `test_openapi_contract.py` (15 testes) |
| `integration` | Requer PostgreSQL/Redis/MinIO reais | nenhum no baseline P01 |

Os marcadores são aplicados automaticamente via `backend/tests/conftest.py` — nenhum arquivo de teste foi modificado para incluí-los.

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

7. **Benchmark e arquivos de diagnóstico ausentes:** `ops/benchmark_production_api.py` e arquivos relacionados não existem em `origin/main`. Serão tratados no P04 com revisão de proveniência.

---

## 6. Arquivos de configuração adicionados no P01

| Arquivo | Propósito |
|---|---|
| `backend/pytest.ini` | Configuração pytest: testpaths, markers, filterwarnings, addopts (JUnit) |
| `backend/.coveragerc` | Configuração coverage.py: source, branch, omit, xml output |
| `backend/tests/conftest.py` | Aplica marcadores unit/contract via `pytest_collection_modifyitems` |

---

## 7. Próximos passos (fora do escopo P01)

- **P02:** harness HTTP com PostgreSQL real, transações por teste, factories BR/EU
- **P03:** testes de componentes React com Vitest/Testing Library/MSW
- **P18–P20:** redução progressiva do lint 46 → 30 → 15 → 0
