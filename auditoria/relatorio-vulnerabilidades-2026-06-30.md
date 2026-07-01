# Relatório de Vulnerabilidades — Projeto Ilya
**Data:** 2026-06-30  
**Ferramentas:** Semgrep 1.168.0 · Secretlint · npm audit · Review manual

---

## Sumário Executivo

| Severidade | Quantidade |
|------------|-----------|
| 🔴 Alta    | 2 |
| 🟡 Média   | 2 |
| 🔵 Baixa   | 3 |
| ℹ️ Info    | 2 |

**Dependências (npm audit):** 0 vulnerabilidades em 159 pacotes  
**Secrets expostos (secretlint):** Nenhum encontrado  
**Semgrep (código do projeto):** 1 achado real — 62 restantes são na ferramenta de terceiros `.claude/skills/impeccable/` (descartados)

> As issues de infraestrutura (Dockerfile, docker-compose) estão anotadas mas **não são prioridade agora** (ambiente local apenas).

---

## 🔴 Alta Severidade

### V-01 — Race Condition na Geração de Código de Pedido
**Arquivo:** `backend/app/api/routers/orders.py:28-31`  
**Ferramenta:** Review manual

```python
async def _next_code(db: AsyncSession) -> tuple[str, str]:
    result = await db.execute(select(func.count()).select_from(Order))
    n = (result.scalar() or 0) + 1
    return f"PED-{n:04d}", f"ORC-{n:04d}"
```

**Problema:** `COUNT(*)` + incremento manual não é atômico. Se dois pedidos forem criados simultaneamente (async), ambos podem receber o mesmo código (`PED-0042 / ORC-0042`), causando colisão silenciosa. Com o volume atual é baixa probabilidade, mas é uma condição de corrida real.

**Correção:**
```python
# Em models/order.py — adicionar sequência no banco
from sqlalchemy import Sequence

order_seq = Sequence("order_seq", start=1)

# Na migration Alembic:
op.execute("CREATE SEQUENCE IF NOT EXISTS order_seq START 1")

# No router — trocar _next_code por:
async def _next_code(db: AsyncSession) -> tuple[str, str]:
    n = (await db.execute(select(order_seq.next_value()))).scalar()
    return f"PED-{n:04d}", f"ORC-{n:04d}"
```

---

### V-02 — Assinatura sem Validação de Tamanho (DoS Potencial)
**Arquivo:** `backend/app/api/routers/orders.py:241-261` e `319-348`  
**Ferramenta:** Review manual

```python
class SignPayload(BaseModel):
    signature: str  # sem limite de tamanho
```

**Problema:** A assinatura é uma imagem em base64 (`data:image/png;base64,...`). Sem limitação, um cliente malicioso pode enviar um payload de centenas de MB, sobrecarregando o banco de dados e a memória do servidor. O campo é salvo diretamente em coluna `TEXT` do PostgreSQL.

**Correção:**
```python
from pydantic import field_validator

class SignPayload(BaseModel):
    signature: str

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, v: str) -> str:
        MAX_B64_SIZE = 500_000  # ~375KB PNG descomprimida
        if len(v) > MAX_B64_SIZE:
            raise ValueError("Assinatura excede o tamanho máximo permitido.")
        if not v.startswith("data:image/"):
            raise ValueError("Formato de assinatura inválido.")
        return v
```

---

## 🟡 Média Severidade

### V-03 — Content-Security-Policy com `unsafe-inline` em style-src
**Arquivo:** `backend/app/main.py:65-72`  
**Ferramenta:** Review manual

```python
"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
```

**Problema:** `'unsafe-inline'` para estilos permite que qualquer CSS injetado via XSS (ex: via atributo `style=`) seja executado. Reduz a eficácia do CSP como segunda camada de defesa contra XSS.

**Causa raiz:** O frontend usa Tailwind v4 que injeta estilos inline via `<style>` tags no `<head>` durante o build. Em produção (SPA estático), o Tailwind é compilado em um `.css` externo, então `unsafe-inline` pode ser substituído por um hash.

**Correção para produção:**
```python
# Gerar o hash SHA-256 do bloco <style> inline do Tailwind após build:
# openssl dgst -sha256 -binary dist/assets/index.css | openssl base64 -A
# Então: "style-src 'self' 'sha256-<hash>' https://fonts.googleapis.com"
```

---

### V-04 — Token de Assinatura Exposto na URL (Querystring Leak)
**Arquivo:** `backend/app/api/routers/orders.py:198`  
**Ferramenta:** Review manual

```python
url = f"/sign-contract?token={token}"
```

**Problema:** O JWT de assinatura de contrato vai para a querystring da URL. URLs com tokens em querystring vazam via:
- Header `Referer` se o usuário clicar em links externos
- Logs de servidor/proxy
- Histórico do browser do cliente

O token tem 60 min de validade, o que mitiga parcialmente, mas o padrão é arriscado.

**Correção:** Passar o token via fragment (#) — fragments não são enviados ao servidor nem ao Referer:
```python
url = f"/sign-contract#{token}"
```
No frontend `SignContractPage.tsx`, trocar:
```typescript
// Antes:
const [params] = useSearchParams()
const t = params.get('token') ?? ''

// Depois:
const t = window.location.hash.slice(1)
```

---

## 🔵 Baixa Severidade

### V-05 — CORS `allow_headers=["*"]` (Permissivo)
**Arquivo:** `backend/app/main.py:51-53`  
**Ferramenta:** Review manual

```python
allow_headers=["*"],
```

**Problema:** Aceitar qualquer header aumenta a superfície de ataque para ataques CORS. Melhor prática é listar apenas os headers que a API realmente usa.

**Correção:**
```python
allow_headers=["Authorization", "Content-Type", "Accept"],
```

---

### V-06 — Dockerfile sem Usuário Não-Root
**Arquivo:** `backend/Dockerfile:13`  
**Ferramenta:** Semgrep (ERROR `missing-user`)  
**Status:** ⚠️ Não prioritário agora — apenas ambiente local

**Problema:** O container roda como root. Se houver RCE, o atacante terá privilégios de root dentro do container.

**Correção:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p app/static/uploads && \
    addgroup --system ilya && \
    adduser --system --ingroup ilya ilya && \
    chown -R ilya:ilya /app
USER ilya
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### V-07 — Flag `--reload` no CMD do Dockerfile
**Arquivo:** `backend/Dockerfile` + `docker-compose.yml`  
**Ferramenta:** Review manual  
**Status:** ⚠️ Não prioritário agora — apenas ambiente local

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Problema:** `--reload` é exclusivo para desenvolvimento. Em produção aumenta consumo de recursos e pode expor mensagens de diagnóstico via mensagens de erro de reload. O `Dockerfile.prod` (já existe) deve ser verificado para garantir que não usa esta flag.

---

## ℹ️ Informativo

### I-01 — Semgrep: 62 Achados em Arquivos de Ferramenta de Terceiros
**Arquivos:** `.claude/skills/impeccable/scripts/*`  
**Ferramenta:** Semgrep

Todos os 62 achados restantes (ReDoS warnings, wildcard postMessage, child_process calls) estão nos scripts internos da skill `impeccable` — ferramenta de desenvolvimento que **não faz parte do código do produto** e não é exposta em nenhum ambiente. Descartados.

---

### I-02 — Dados do Carrinho em `localStorage`
**Arquivo:** `frontend/src/pages/ProdutosPage.tsx:25-46`  
**Ferramenta:** Review manual

```typescript
const raw = localStorage.getItem('carrinho_orcamento')
```

**Observação:** O carrinho persiste em `localStorage`. Os dados são apenas produtos de catálogo (sem PII ou financeiro), então o risco é baixo. Documentado para ciência — qualquer extensão maliciosa no browser do usuário pode ler esses dados.

---

## ✅ O que Está Bem

| Item | Status |
|------|--------|
| Hashing de senhas (Argon2 + pepper, params OWASP) | ✅ Seguro |
| Proteção contra timing attack no login (`dummy_verify`) | ✅ Implementado |
| JWT tipado com claim `type` (`access` / `sign`) | ✅ Correto |
| Refresh token rotacionado a cada uso (token binding) | ✅ Implementado |
| Cookie httpOnly + SameSite=strict para refresh | ✅ Correto |
| Rate limiting no login (5/15min) e troca de senha (5/min) | ✅ Implementado |
| CORS restrito a origens via `.env` | ✅ Correto |
| Security headers (X-Frame-Options, Referrer-Policy, etc.) | ✅ Implementado |
| Swagger desabilitado em produção (`DEBUG=False`) | ✅ Correto |
| Sem SQL injection — ORM com queries parametrizadas | ✅ Seguro |
| Sem secrets hardcoded (secretlint: 0 findings) | ✅ Limpo |
| 0 vulnerabilidades em 159 dependências npm | ✅ Limpo |
| Validação de extensão e tamanho em uploads de imagem | ✅ Implementado |
| RBAC com roles verificados em todos os endpoints | ✅ Correto |
| Autorização por recurso (pedido pertence ao rep/cliente) | ✅ Implementado |

---

## Priorização de Correções

| # | Issue | Esforço | Impacto | Fazer quando |
|---|-------|---------|---------|-------------|
| V-02 | Validação de tamanho da assinatura | 30 min | Alto | **Agora** |
| V-01 | Sequência atômica para código do pedido | 1h + migration | Alto | Antes do volume crescer |
| V-04 | Token no fragment em vez de querystring | 30 min | Médio | Próximo sprint |
| V-05 | CORS allow_headers explícito | 5 min | Baixo | Manutenção |
| V-03 | CSP sem unsafe-inline | Build setup | Baixo | Antes do deploy em produção |
| V-06 | Dockerfile com USER não-root | 15 min | Baixo | Antes do deploy |
| V-07 | Remover --reload do CMD | 5 min | Baixo | Antes do deploy |

---

*Relatório gerado em 2026-06-30 — Projeto Ilya CRM*
