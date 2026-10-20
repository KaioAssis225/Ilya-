# P09/P17 — jornadas de navegador

Seis cenários em `journeys.spec.ts`: login e troca BR/EU, catálogo e foto em cada mercado, pedido BR, pedido EU, acesso por papel e isolamento de carrinho/resposta antiga após troca de identidade. O seed é uma CLI privada e idempotente em `backend/tests/e2e_support/seed_e2e.py`; não há endpoint de reset. As contas usam o domínio reservado `ilya-test.example`, aceito pelo validador de e-mail da API; os SKUs sintéticos usam `E2E-*`.

## Preparar no checkpoint de validação

Executar a partir da raiz do repositório, com Docker Compose e Node compatível com `frontend/package.json`:

```powershell
$env:E2E_SEED_PASSWORD = '<senha-sintetica-forte>'
docker compose -f docker-compose.test.yml -f docker-compose.e2e.yml --profile e2e run --rm backend alembic upgrade head
docker compose -f docker-compose.test.yml -f docker-compose.e2e.yml --profile e2e run --rm backend python -m tests.e2e_support.seed_e2e
docker compose -f docker-compose.test.yml -f docker-compose.e2e.yml --profile e2e up -d backend frontend
cd frontend
npm ci
npx playwright install chromium
$env:E2E_PASSWORD = $env:E2E_SEED_PASSWORD
npm run test:e2e
```

O seed recusa banco que não seja PostgreSQL com nome terminado em `_test` e senha ausente. A URL deve vir de `TEST_DATABASE_URL` ou `DATABASE_URL`; `TEST_DATABASE_URL` do Compose aponta para `ilya_test`. A mesma senha é usada pelo navegador; não salve a senha nos arquivos do repositório. O frontend usa Vite em `localhost:5173` e encaminha `/api` e `/static` ao backend. O overlay E2E configura buckets MinIO distintos BR/EU; o Compose comum continua com seu armazenamento de teste anterior.

Os cenários rodam com um worker, sem retry e sem esperas fixas. `npm run test:e2e` usa Chromium desktop; o nightly seleciona explicitamente `chromium-desktop`, `chromium-mobile` ou `webkit` com `--project`. O Playwright guarda trace, screenshot e vídeo somente em falha, sob `frontend/test-results/e2e`. Depois de corrigir eventuais falhas, executar **três rodadas consecutivas** de `npm run test:e2e` sem retry e registrar o resultado no ledger de validações. A suíte ainda não deve virar gate obrigatório de PR antes dessa evidência. Ao fim do checkpoint, `docker compose -f docker-compose.test.yml -f docker-compose.e2e.yml --profile e2e down` encerra os contêineres descartáveis.

Como os pedidos criados pela UI permanecem no banco até o Compose ser removido, as asserções usam o código retornado pela própria criação; não dependem de contagens globais. Cada teste Playwright recebe um contexto de navegador isolado. O seed pode ser reexecutado sem duplicar contas, clientes ou SKUs.
