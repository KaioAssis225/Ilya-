# Envio do PDF do pedido por e-mail — validação no staging (modo `test`)

Guia operacional para ligar o envio em **staging** (projeto Railway `cozy-prosperity`, ambiente `staging`), sem afetar a produção. Nada aqui é aplicado pelo código: cada passo de infraestrutura precisa de aprovação explícita antes de ser feito. A chave do Resend nunca entra em código, log, chat ou commit; ela é digitada pelo responsável direto no painel do Railway.

Referência de variáveis: `docs/deploy-seguro.md` e `.env.example`.

## O que existe hoje no staging (leitura em 2026-10-29)

| Item | Estado |
|---|---|
| API `Ilya-` | domínio `ilya-staging.up.railway.app`, Railpack, root `/backend`, **branch `feat/estoque-appendix-source-version`** (antiga: precisa apontar para a branch/commit com esta feature antes de testar), volume de uploads em `/app/app/static/uploads` |
| Banco / Redis | `Postgres` e `Redis` próprios do staging (a migration `order_email_r31` roda no deploy da API, pelo `preDeployCommand` do `backend/railway.json`) |
| Armazenamento S3 | só o bucket BR (`OBJECT_STORAGE_*`); **não há** `OBJECT_STORAGE_EU_*` no staging, então valide com **pedido BR** (pedido EU falharia com `storage_not_configured`, que é o comportamento correto) |
| Worker de e-mail | **não existe** (o staging também não tem o worker do Moloni) |

## 1. Resend (conta do responsável)

1. Criar a conta no Resend com o e-mail que vai receber os testes.
2. **Remetente de teste:** `onboarding@resend.dev`. Sem DNS. O Resend só entrega para o e-mail dono da conta, por isso a allowlist do staging deve conter exatamente esse endereço.
3. Criar uma API key (permissão de envio) e guardá-la só no Railway.
4. Criar o webhook em *Webhooks → Add Endpoint*:
   - URL: `https://ilya-staging.up.railway.app/webhooks/resend`
   - Eventos: `email.delivered`, `email.bounced`, `email.failed`, `email.complained`, `email.delivery_delayed`
   - Copiar o *Signing Secret* (`whsec_…`) para `RESEND_WEBHOOK_SECRET` (passo 3).

## 2. Apontar a API do staging para esta versão (decisão de infra)

Trocar a branch do serviço `Ilya-` do staging de `feat/estoque-appendix-source-version` para a branch/commit que contém a feature (por exemplo `main` depois do merge). O deploy executa a migration `order_email_r31`. **Pedir aprovação antes** (muda o ambiente de staging; o ramo antigo carrega o trabalho de estoque).

## 3. Variáveis — serviço `Ilya-` (API, staging)

| Variável | Valor |
|---|---|
| `ORDER_EMAIL_MODE` | `test` |
| `ORDER_EMAIL_TEST_ALLOWLIST` | o e-mail do dono da conta Resend |
| `RESEND_WEBHOOK_SECRET` | o `whsec_…` do passo 1 |

A API só enfileira e recebe o webhook; **não** precisa de `RESEND_API_KEY`. Com `ORDER_EMAIL_MODE=off` (ou sem a variável) tudo volta ao comportamento anterior.

## 4. Worker de e-mail (serviço novo, só no staging)

Serviço novo no ambiente `staging`, mesmo repositório e branch da API, **root directory `backend`**, builder Railpack, **sempre ligado** (sem cron), start command:

```text
python -m app.workers.order_email_sender
```

O worker faz o ciclo a cada `ORDER_EMAIL_POLL_SECONDS` (10 s), renderiza o PDF no Chromium, grava no bucket e envia pelo Resend.

Variáveis:

| Variável | Valor |
|---|---|
| `DATABASE_URL` (ou `PG*`) | mesma referência da API do staging |
| `SECRET_KEY`, `PASSWORD_PEPPER` | mesmas da API (o app exige que existam) |
| `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_ACCESS_KEY_ID`, `OBJECT_STORAGE_SECRET_ACCESS_KEY`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_REGION`, `OBJECT_STORAGE_ADDRESSING_STYLE` | as mesmas da API (o worker lê e grava o PDF no mesmo bucket) |
| `ORDER_EMAIL_MODE` | `test` |
| `ORDER_EMAIL_TEST_ALLOWLIST` | igual à da API |
| `RESEND_API_KEY` | a chave (digitada no painel) |
| `ORDER_EMAIL_FROM` | `Ilya <onboarding@resend.dev>` |
| `ORDER_EMAIL_REPLY_TO` | caixa comercial de teste |
| `ORDER_EMAIL_PDF_RENDERER` | `playwright` |

Fotos de produto que estiverem só no volume local da API (`/app/app/static/uploads`) não são visíveis ao worker: o PDF sai com o quadro "sem foto" nesses itens. Produtos com foto no bucket saem com foto.

### 4.1 Chromium no build do worker (maior risco — pedir aprovação e fazer um spike)

Alterar **apenas o serviço novo**; a API e o worker do Moloni não mudam. Opção recomendada (a validar no spike, nesta ordem):

1. **Railpack + variáveis do serviço:**
   - `RAILPACK_DEPLOY_APT_PACKAGES` com as bibliotecas do Chromium (na imagem Debian de teste, `playwright install --with-deps chromium` instala: `libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2`; os nomes exatos dependem da base do Railpack, confirmar pelo log do build);
   - `PLAYWRIGHT_BROWSERS_PATH=/app/.pw-browsers` e `RAILPACK_BUILD_CMD="python -m playwright install chromium"` para baixar o navegador no build;
   - verificar no log de runtime se o diretório do navegador existe na imagem final.
2. Se o navegador não persistir na imagem final: arquivo `railpack` próprio do worker (apontado por `RAILPACK_CONFIG_FILE`, **sem** colocar um `railpack.json` em `backend/`, que afetaria a API e o Moloni), com `deploy.aptPackages` e a etapa de instalação mantida em `deploy.inputs`.
3. Último recurso: Dockerfile oficial do Playwright **só nesse serviço** (foge do padrão "Railpack, não Dockerfile.prod"; decisão do responsável).

**Memória:** cada renderização abre um Chromium e fecha ao terminar; contar com cerca de 0,5–1 GB de pico por documento (um por vez no processo). Confirmar que o plano do projeto permite esse limite para o serviço.

## 5. Roteiro de validação

1. `GET /health/ready` da API verde após o deploy; log do worker sem erros de configuração.
2. Cadastrar (ou editar) um cliente BR com o **e-mail do dono do Resend**; criar e **finalizar** um pedido para ele.
3. Em *Orçamentos → Ver detalhes* aparece a aba **E-mails**: documento "preparado" e, em segundos, a entrega **Aceito pelo serviço** e depois **Entregue** (webhook).
4. Conferir na caixa de entrada: assunto com o número do pedido, anexo `PED-….pdf` abrindo com o layout do navegador (fotos, impostos, medidas), *reply-to* correto.
5. **Baixar PDF enviado** deve devolver o mesmo arquivo (mesmo hash). **Reenviar** cria nova entrega com o mesmo documento.
6. Como admin, usar **Enviar e-mail de teste** com o e-mail do dono: passa pela fila e pelo worker. Com um e-mail fora da allowlist a entrega aparece como "Não enviado (modo de teste)" e nada sai.
7. Webhook: reenvio de um evento no painel do Resend não duplica nem rebaixa o estado.
8. Provedor fora do ar: com uma chave inválida, a entrega fica pendente e tenta de novo; a finalização do pedido continua funcionando.

## 6. Reverter

- `ORDER_EMAIL_MODE=off` na API e no worker (nada novo é enfileirado; o histórico já criado permanece).
- Remover o serviço do worker.
- A migration `order_email_r31` é aditiva; `alembic downgrade -1` só se for realmente preciso.
