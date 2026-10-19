# Relatório de benchmark da API — referência sanitizada (P04 v2)

**Propósito:** este arquivo é um exemplo sintético do formato de saída de
`ops/benchmark_production_api.py` (v2.0.0). Serve como referência para validar a
estrutura antes de execuções reais e para documentar as limitações do diagnóstico.

**Dados:** completamente fictícios. Nenhuma URL, token, latência ou contagem
aqui reflete o estado real de produção.

**Política de artefatos reais:** relatórios gerados por execuções reais
(baseline autenticado, carga em homologação) NÃO devem ser versionados em git.
Armazená-los em objeto/bucket controlado.

**Mudanças em v2.0.0 (P04 rev2):**
- `valid_count` e percentis contam apenas respostas 2xx (antes incluíam 401/4xx/5xx).
- `client_error_count` adicionado (4xx excluindo 401/403).
- Estatísticas produzidas separadamente por origem (Railway e Vercel).
- Modo load usa política positiva/default-deny: `BENCHMARK_STAGING_ALLOWLIST` obrigatório.
- `--api-token` removido; token somente via `BENCHMARK_API_TOKEN`.
- Dry-run não expõe URLs nem valores de credenciais.
- `*.up.railway.app` sempre bloqueado para modo load.

---

## Exemplo: modo smoke (3 amostras — sem credencial)

```json
{
  "meta": {
    "commit": "d4e5c05a",
    "app_version": "unknown",
    "environment": "exemplo-sintetico",
    "seed": 42,
    "tool": "benchmark_production_api",
    "tool_version": "2.0.0",
    "mode": "smoke",
    "generated_at": "2026-10-19T00:00:00+00:00",
    "min_samples_for_percentiles": 30
  },
  "scenarios": [
    {
      "name": "health_live_railway",
      "route_template": "GET /health/live",
      "origins_tested": ["railway"],
      "sample_count": 3,
      "valid_count": 3,
      "network_error_count": 0,
      "timeout_count": 0,
      "auth_failure_count": 0,
      "client_error_count": 0,
      "functional_failure_count": 0,
      "p50_ms": "45.2",
      "p95_ms": "INCONCLUSIVO (n=3, precisa >=30)",
      "p99_ms": "INCONCLUSIVO (n=3, precisa >=30)",
      "max_ms": "48.1"
    },
    {
      "name": "health_ready_railway",
      "route_template": "GET /health/ready",
      "origins_tested": ["railway"],
      "sample_count": 3,
      "valid_count": 3,
      "network_error_count": 0,
      "timeout_count": 0,
      "auth_failure_count": 0,
      "client_error_count": 0,
      "functional_failure_count": 0,
      "p50_ms": "47.8",
      "p95_ms": "INCONCLUSIVO (n=3, precisa >=30)",
      "p99_ms": "INCONCLUSIVO (n=3, precisa >=30)",
      "max_ms": "52.3"
    }
  ],
  "limitations": [
    "Modo smoke: 3 amostras por origem — p95/p99 são inconclusivos (necessário >=30).",
    "Sem credencial: apenas rotas públicas testadas. 401 de rotas autenticadas não são operação comercial válida.",
    "Sem URL Vercel: comparação Railway/Vercel indisponível."
  ]
}
```

---

## Exemplo: modo baseline (30 amostras validas + 5 warmups — com credencial)

```json
{
  "meta": {
    "commit": "d4e5c05a",
    "app_version": "1.0.0",
    "environment": "homologacao",
    "seed": 42,
    "tool": "benchmark_production_api",
    "tool_version": "2.0.0",
    "mode": "baseline",
    "generated_at": "2026-10-19T00:00:00+00:00",
    "min_samples_for_percentiles": 30
  },
  "scenarios": [
    {
      "name": "health_live_railway",
      "route_template": "GET /health/live",
      "origins_tested": ["railway"],
      "sample_count": 30,
      "valid_count": 30,
      "network_error_count": 0,
      "timeout_count": 0,
      "auth_failure_count": 0,
      "client_error_count": 0,
      "functional_failure_count": 0,
      "p50_ms": "38.4",
      "p95_ms": "92.1",
      "p99_ms": "105.3",
      "max_ms": "110.7"
    },
    {
      "name": "health_live_vercel",
      "route_template": "GET /health/live",
      "origins_tested": ["vercel"],
      "sample_count": 30,
      "valid_count": 30,
      "network_error_count": 0,
      "timeout_count": 0,
      "auth_failure_count": 0,
      "client_error_count": 0,
      "functional_failure_count": 0,
      "p50_ms": "41.2",
      "p95_ms": "98.5",
      "p99_ms": "112.0",
      "max_ms": "118.3"
    },
    {
      "name": "auth_me_railway",
      "route_template": "GET /auth/me",
      "origins_tested": ["railway"],
      "sample_count": 30,
      "valid_count": 30,
      "network_error_count": 0,
      "timeout_count": 0,
      "auth_failure_count": 0,
      "client_error_count": 0,
      "functional_failure_count": 0,
      "p50_ms": "52.7",
      "p95_ms": "124.8",
      "p99_ms": "138.2",
      "max_ms": "145.0"
    }
  ],
  "limitations": []
}
```

---

## Limitacoes do diagnostico

### Amostragem

| Modo | Amostras | p95/p99 | Observacao |
|---|---:|---|---|
| smoke | 3 | **INCONCLUSIVO** | Provar conectividade; nao inferir desempenho |
| baseline | >=30 validas + >=5 warmups | Conclusivos | Minimo para inferencia estatistica basica |
| load | configuravel | Conclusivos se >=30 | Restrito a homologacao |

Para p95/p99 com intervalo de confianca aceitavel, recomenda-se >=100 amostras em
condicoes estaveis. O limite de 30 e o minimo para produzir um valor, nao para declarar
que o SLO foi atingido ou violado.

### O que nao e medido

- **Latencia de cold start:** warmup descarta as primeiras amostras, mas nao garante que
  o servidor esta em regime permanente. Comparar apenas execucoes com aquecimento equivalente.
- **Concorrencia:** modos smoke e baseline fazem requisicoes sequenciais. Para medir
  degradacao sob carga concorrente, usar modo load em homologacao.
- **Latencia do usuario final:** a ferramenta mede Railway direta ou Vercel rewrite, nao
  a pilha de rede do cliente. Nao somar os dois como latencia percebida.
- **Operacoes de escrita:** a ferramenta so testa rotas de leitura por padrao.

### Semantica de 401

Um 401 indica que a credencial nao foi aceita — nao que a operacao comercial falhou.
Contagem de 401 em `auth_failure_count` **nao** entra em `functional_failure_count`.
Um diagnostico sem credencial configurada pode retornar exit 0 mesmo que todas as
rotas autenticadas respondam 401.

### Redaction

`Authorization`, `X-Api-Key`, `Cookie` e `Set-Cookie` sao substituidos por
`***REDACTED***` em qualquer saida. Nunca inspecionar headers crus no relatorio
para depurar falha de autenticacao — usar o log sanitizado do servidor.

### Erros de rede

`network_error_count` e `timeout_count` refletem falhas de conectividade entre o
executor e o servidor, nao falhas comerciais. Um runner de CI em rede lenta pode
inflar esses contadores sem que o backend apresente problema real.

---

## Comandos para gerar relatorio real (apos P11 — credenciais provisionadas)

```bash
# Smoke sem credencial (conectividade basica)
python ops/benchmark_production_api.py \
  --mode smoke \
  --target-url "$BENCHMARK_TARGET_URL" \
  --environment homologacao

# Baseline autenticado (credencial somente leitura BR)
export BENCHMARK_API_TOKEN="$(cat /run/secrets/benchmark-br-token)"
python ops/benchmark_production_api.py \
  --mode baseline \
  --target-url "$BENCHMARK_TARGET_URL" \
  --vercel-url "$BENCHMARK_VERCEL_URL" \
  --environment homologacao \
  --commit "$GITHUB_SHA" \
  --app-version "$APP_VERSION" \
  --output /tmp/baseline-$(date +%Y%m%d-%H%M%S).json
```

Relatorios gerados devem ser auditados manualmente antes de mover para armazenamento
controlado. Nunca comitar arquivos gerados em git.
