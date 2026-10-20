# Runbook de observabilidade mínima

## Ativação e segurança

A coleta nasce desligada. Para ativar em homologação, configure `OBSERVABILITY_ENABLED=true`, gere um segredo exclusivo em `OBSERVABILITY_METRICS_TOKEN` e reinicie a API. O coletor consulta `GET /internal/metrics` com `Authorization: Bearer <segredo>`. Sem flag ou com token ausente/incorreto, a rota responde 404. O token fica no gerenciador de segredos e nunca no Git, em query string ou em logs.

O formato é compatível com Prometheus e não exige um fornecedor. Cada processo mantém seu próprio acumulador; o scraper precisa coletar todas as réplicas/workers ou usar o mecanismo de descoberta da plataforma. Reiniciar um worker zera seus contadores e muda `ilya_process_start_time_seconds`. Não some histogramas de períodos com conjuntos diferentes de workers sem considerar esses resets.

Rollback imediato: defina `OBSERVABILITY_ENABLED=false` e reinicie. Os logs mínimos com `X-Request-ID`, template de rota, status, duração, mercado seguro e versão permanecem ativos. Com a coleta ligada, a mesma linha HTTP inclui contagem e tempo acumulado de SQL, aquisição de conexão e dependências externas daquele request; o request ID não vira rótulo de métrica.

## Rótulos permitidos

| Família | Rótulos |
|---|---|
| HTTP | método em allowlist, template FastAPI da rota ou `unmapped`, status HTTP, mercado `BR`, `EU` ou `none` |
| SQL | operação `SELECT`, `INSERT`, `UPDATE`, `DELETE` ou `OTHER`; pool fixo `primary` |
| Dependência | `viacep`, `geoapi`, `zippopotam`, `moloni`, `microsoft_graph`, `webhook` ou `unknown`; status e resultado limitados |
| Processo | versão publicada e quantidade configurada de workers |

IDs, UUIDs, URL completa, query string, SQL, valores SQL, CEP/código postal, corpo, token, cookie, assinatura, CPF/CNPJ, e-mail e telefone não são coletados. Rotas sem template viram `unmapped`; hosts desconhecidos viram `unknown`.

## Painel inicial

Monte quatro seções e permita comparar a versão atual com a anterior:

1. API: taxa de `ilya_http_requests_total`, disponibilidade, 4xx/5xx, p50/p95/p99 de `ilya_http_request_duration_seconds`, tamanho de resposta, cancelamentos e requisições em andamento.
2. Banco: p95 de aquisição e query, erros, `ilya_db_pool_connections` por estado e `ilya_db_pool_timeouts_total`.
3. Dependências: p95 por allowlist, status, timeout/conexão, resposta inválida e fallback.
4. Processo: CPU, RSS, início do processo, versão e workers. CPU/RSS são por processo; combine por réplica apenas na visualização.

O exportador mede duração de comandos SQL, sem texto ou parâmetros. A aquisição é medida quando uma operação da sessão solicita conexão; operações que gravam apenas durante `commit` podem não produzir a amostra de aquisição, embora as consultas emitidas continuem instrumentadas. Locks/deadlocks e transações longas exigem métricas do PostgreSQL/plataforma de coleta; não são inferidos pelo processo da API. `workers` reflete a configuração `WEB_CONCURRENCY`, e a quantidade realmente saudável deve ser conferida na plataforma. Bloqueio do event loop também depende do runtime/coletor e não é inferido por este exportador mínimo.

## Alertas para ensaio em homologação

Os limiares são iniciais e só viram gate após P12 aprovar SLO e amostra mínima:

- disponibilidade abaixo de 99% em 15 minutos, ignorando ausência de tráfego e janela planejada;
- 5xx acima de 2% por 5 minutos, com volume mínimo definido no coletor;
- p95 acima do SLO provisório da classe de rota por 10 minutos;
- qualquer incremento de timeout do pool;
- duas falhas consecutivas de `/health/ready`;
- início de processo mudando repetidamente fora de deploy;
- timeout ou erro de conexão de dependência acima do limiar aprovado.

Ensaiar cada alerta em homologação, registrar disparo e recuperação e guardar screenshot sanitizado. Não simular falha em produção.

## Triagem por request ID

1. Capture `X-Request-ID` da chamada do benchmark e localize a linha HTTP correspondente.
2. Confirme versão, template de rota, mercado e duração total. Nunca pesquise pelo identificador comercial presente na URL.
3. No mesmo intervalo, compare duração e quantidade de SQL, aquisição/pool e dependências externas.
4. Se pool estiver saturado ou houver timeout, preserve a configuração e leve a evidência ao P13/P14d; não aumente pool/workers sem orçamento de conexões.
5. Se a dependência dominar, confira timeout, status, resposta inválida e fallback antes de propor cache ou troca de fornecedor.
6. Se API continuar lenta sem SQL/dependência, compare CPU/RSS e versão e reproduza no mesmo seed/cenário.

## Evidência do checkpoint P10

Registrar flag e versão, uma chamada BR e uma EU com os respectivos request IDs, amostra sanitizada do endpoint, painel das quatro seções, overhead grosseiro ligado/desligado e resultado dos ensaios de alerta. A validação automatizada prevista é `python -m pytest tests/test_observability.py`; sua execução permanece no checkpoint combinado.
