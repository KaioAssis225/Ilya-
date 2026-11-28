# Virada Railway → VPS HostGator (Ilya + Estoque)

Stack de produção em `/opt/ilya-production` (Docker Compose, projeto `ilya-production`).
**Nada nela é público**: as APIs escutam só em `127.0.0.1:19080` (Ilya) e
`127.0.0.1:19082` (Estoque). O Caddy (`ilya-ingress`) segue com o Caddyfile antigo
(só `/health/*` e `/estoque-health/*`, apontando para a homologação) até o passo 4.

> **Este PR não pode ser mergeado antes da virada.** `frontend/vercel.json` já aponta
> os rewrites para `https://143.95.189.88`; o merge faz a Vercel publicar isso e o
> tráfego real muda de lugar.

## O que existe hoje

| Peça | Estado |
|---|---|
| Ilya: API, migração, worker de e-mail, Postgres 18, Redis 8 | no ar, saudáveis |
| Estoque: API, migração, worker operacional, Postgres 18, Redis 8 | no ar, saudáveis |
| Imagens | `ilya-production-api:899ad3e0`, `ilya-production-email:899ad3e0`, `ilya-production-estoque:5c94f57` |
| Dados | **cópia nova de produção ensaiada em 2026-11-24** (Ilya `ilya_copy_20261124_163857_e35ba962`, Estoque `estoque_copy_20261124_164045_73b5cea5`). Os bancos `*_ensaio_*` e as cópias do ensaio já foram removidos (com OK); a stack roda só nos bancos `ilya` e `estoque` |
| Segredos | `PASSWORD_PEPPER`, `SECRET_KEY`, `MEDIA_SIGNING_KEY`, par do login único: **copiados do Railway**. Senhas de banco/Redis: novas, geradas na VPS |
| Roles | `ilya_app`, `estoque_app`, `ilya_estoque_readonly` (GRANTs iguais aos de produção; `hashed_password` nunca liberado) |
| Travas | `ORDER_EMAIL_MODE=off`, Moloni e webhook desligados, sync do Estoque desligado (`ILYA_AUTO_SYNC_*=false`), **nenhum `sync-once` agendado** (ele grava produtos **e** pedidos) |
| Mídia | continua nos buckets atuais (`OBJECT_STORAGE_*` copiados do Railway). Ver pendências |

Env files: `/opt/ilya-production/env/*.env` (0600, fora do git). Regerar só se preciso:
`python3 generate_env.py` (não sobrescreve; `--force` troca as senhas e quebra os bancos já criados).

Comandos do dia a dia (em `/opt/ilya-production`):

```bash
docker compose ps
docker compose logs --tail 50 ilya-api          # nunca imprima os env files
python3 bootstrap_roles.py verify               # prova os GRANTs da role somente-leitura
python3 smoke_test.py --credentials-file /opt/ilya-acceptance/acceptance.env
```

## Tempos medidos no ensaio (2026-11-24)

Cópias reais de produção (Ilya ≈ 15 MB; Estoque ≈ 2,2 GB, dos quais ~7,4 milhões de linhas de
`security_audit_events`). Medido pelos scripts, a partir do computador do responsável.

| Etapa | Tempo | Como saiu |
|---|---|---|
| 2a. Copiar o Ilya (`ops/copy_railway_to_vps.py`) | **38,8 s** | medido |
| 2b. Copiar o Estoque (`ops/hostgator/copy_estoque_to_vps.py`) | **8 min 24 s** | medido; domina a janela (dump pela internet do dono) |
| 3. Trocar os dados (`swap_data.sh`, todas as etapas) | **57 s** | medido: parar 1 s · Ilya 1 s · Estoque 38 s · contagens 5 s · renomear 1 s · roles/GRANTs 3 s · subir + migrações 7 s |
| 5. `smoke_test.py` completo (BR e EU) | **4 s** | medido |
| 5. `reconcile-ilya` (leitura pela role somente-leitura) | **1,5 s** | medido |
| Volta (VPS → Postgres), dump dos dois bancos | **23 s** | medido (dumps: 351 MB + 0,5 MB) |
| Volta, restaurar em Postgres 18 | **39 s** | medido |
| Volta, restaurar em Postgres 16 (mais antigo que o dump) | **48 s** | medido, com o filtro de `transaction_timeout` (ver "Caminho de volta") |

**Estimativa da janela com gravações pausadas** (Ilya e Estoque ficam sem escrita do passo 1 até o passo 6):

| Parte | Tempo |
|---|---|
| Mecânica medida (cópias 2a em paralelo com 2b + troca + smoke) | **≈ 10 min** (8,5 + 1 + 0,5) |
| Pausar o Railway e confirmar zero escrita (passo 1) | ≈ 5 min *(estimado, manual)* |
| Caddy: validar e reiniciar o container (passo 4) | ≈ 1 min *(estimado; ensaiado só em loopback)* |
| Teste manual pelo preview da Vercel (login BR/EU, cotação, login único) | ≈ 10 min *(estimado)* |
| Merge + deploy da Vercel + conferência pelo domínio público | ≈ 5 min *(estimado)* |
| **Total** | **≈ 30 min; avise 45 min** |

Como encurtar: quase tudo é o dump do Estoque pela internet do responsável (8,4 min). Rodar a cópia de
uma máquina com banda melhor, ou rodar o `pg_dump` dentro do Railway por SSH (`--railway-ssh`, não
testado), reduz isso; o restore e a troca na VPS já são rápidos (< 1 min).

## Antes do dia da virada

1. Imagens finais: a revisão que vai para produção precisa estar nas tags acima
   (workflow `hostgator-image.yml` gera `ilya.tar.gz`; ajuste `.env` se mudar a tag).
2. Backup do Caddyfile: `cp /opt/ilya-ingress/Caddyfile /opt/ilya-ingress/Caddyfile.pre-virada`.
3. Decidir a mídia, backups e o rewrite do Estoque (ver "Pendências"). O passo 3 já foi ensaiado.
4. Avisar a janela (45 min) às pessoas. Conferir que o banco do Ilya no Railway tem URL pública
   de leitura e que o Postgres do Estoque (Postgres-51tP, sem proxy público) terá um proxy TCP
   temporário ligado **por quem tem acesso ao Railway**; desligue-o ao terminar.
5. Descobrir a versão do Postgres do Railway (`SHOW server_version;`): define se a volta precisa do filtro
   de `transaction_timeout` (ver "Caminho de volta").

## Virada

### 1. Pausar as gravações (Railway)
Ordem: (a) Estoque: cron/sync e worker; (b) Estoque API; (c) worker de e-mail do Ilya;
(d) API do Ilya. Confirme zero conexões de escrita no Postgres do Railway. Não apague
nada no Railway: pausado, ele é o caminho de volta.

### 2. Cópias finais (do computador do responsável, uma janela de terminal para cada)
```powershell
# Ilya: URL do cofre, nunca do chat; lida sem eco
$sec = Read-Host "URL do Postgres do Ilya" -AsSecureString
$env:PRODUCTION_DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
python ops/copy_railway_to_vps.py root@143.95.189.88
Remove-Item Env:PRODUCTION_DATABASE_URL
```
```powershell
# Estoque: URL do proxy TCP temporário do Postgres-51tP
$sec = Read-Host "URL do Postgres do Estoque" -AsSecureString
$env:ESTOQUE_PRODUCTION_DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
python ops/hostgator/copy_estoque_to_vps.py root@143.95.189.88
Remove-Item Env:ESTOQUE_PRODUCTION_DATABASE_URL
```
Cada um imprime o tempo das etapas e `Cópia validada na VPS: <banco>`. Anote os dois nomes. Depois **desligue o
proxy TCP** do Estoque. Ambos os scripts são somente leitura na origem (`default_transaction_read_only=on`,
`lock_timeout=3 s`) e criam um banco NOVO por execução; nunca tocam em bancos existentes.

### 3. Restaurar nesta stack (1 minuto)
```bash
cd /opt/ilya-production
bash swap_data.sh <ilya_copy_...> <estoque_copy_...> | tee swap-$(date -u +%Y%m%d_%H%M%S).log
```
O script para as APIs/workers, restaura em `ilya_new`/`estoque_new` (sem tocar nos bancos em uso), compara a
contagem de linhas de **todas** as tabelas contra a cópia (aborta se qualquer uma diferir), só então renomeia
(`ilya`→`ilya_ensaio_<carimbo>`, `ilya_new`→`ilya`; idem Estoque), roda `bootstrap_roles.py roles/grants/verify` e sobe a stack
(`docker compose up -d --wait`); a migração roda sobre o banco já restaurado.

**Segue** se: "contagens iguais" nas duas, `RESULTADO: tudo certo` do `verify`, todos os serviços `healthy` e
as migrações sem nenhuma linha `Running upgrade` (a revisão da cópia já é a da imagem; ensaio: nenhuma mudança).
**Volta** (e nada foi perdido: o Railway não foi tocado) se qualquer uma falhar: o script aborta antes de renomear.

Os bancos `*_ensaio_<carimbo>` ficam de reserva. **Removê-los (ou volumes antigos) é destrutivo: só com OK
explícito do responsável.** (O ensaio de 2026-11-24 já foi limpo; ver "Pendências".)

### 4. Abrir as rotas no Caddy
O Caddyfile final é o arquivo versionado [`Caddyfile.final`](Caddyfile.final). Foi **validado só em loopback**
(`127.0.0.1:18088`, sem TLS/ACME, container que se desliga sozinho) e nada público foi alterado no ensaio.
Resultado do ensaio, com a stack real atrás:

| Pedido | Resposta |
|---|---|
| `/health/ready` | 200 (Ilya) |
| `/api/v1/auth/me` sem token | 401 (chega na API do Ilya) |
| `/estoque-api/…` e `/estoque-health/ready` | chegam ao Estoque (o prefixo `/estoque-api` é removido) |
| `/`, `/docs`, `/openapi.json`, qualquer rota desconhecida | 404 |
| corpo de 20 MB em `/api/v1/auth/login` | 413 (teto de 15 MB, igual ao nginx da homologação) |
| `X-Forwarded-For: 1.2.3.4` forjado | o upstream recebe o IP de quem conectou, não o forjado |

Decisões: **`trusted_proxies` não definido** (a Vercel não publica faixas fixas; confiar em tudo deixaria qualquer um forjar o
IP do cliente e burlar o rate limit de login; no Railway o IP efetivo já era o da Vercel, então não há regressão). O Estoque
é publicado em **`/estoque-api/*`**: exige o rewrite correspondente no `vercel.json` do repositório do Estoque (fora deste PR).

Aplicar (como `admin off`, recarregar = reiniciar o container):
```bash
cp Caddyfile.final /opt/ilya-ingress/Caddyfile       # o anterior já está em Caddyfile.pre-virada
docker run --rm -v /opt/ilya-ingress/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile
docker restart ilya-ingress
```

### 5. Testar (antes de mergear)
- `curl -sk https://143.95.189.88/health/ready` e `/estoque-health/ready` → 200.
- `python3 smoke_test.py --credentials-file …` na VPS (conta sintética, só em 127.0.0.1). Cobre, em BR **e** EU:
  saúde, login, troca de mercado, catálogos, produtos, **foto assinada baixada do storage** e assinatura adulterada
  recusada (403), detalhe do pedido (cotação), PDF guardado do pedido e login único até a sessão do Estoque
  (reuso da autorização recusado). Ensaio: 100% OK. *Limite:* o PDF que o usuário gera na tela da cotação é feito no
  navegador, então só o teste manual pelo preview cobre isso; e o PDF "guardado" só existe depois de um envio de e-mail
  (hoje desligado), então o smoke avisa "PDF não testado" quando nenhum pedido tem um.
- A Vercel cria um **preview** deste PR já com os rewrites novos: logue por ele nos mercados BR e EU,
  abra uma cotação e gere o PDF, e use o login único para o Estoque.
- `docker compose run --rm estoque-tools python startup.py reconcile-ilya` (só leitura, via `ilya_estoque_readonly`).
  Ensaio: `order_extra_local=67, product_extra_local=277, tombstone_without_origin=115` (o Estoque tem pedidos/produtos
  que o escopo do Ilya não lista). Não é falha da virada, mas **é um motivo para não ligar o sync sem revisar**.
- Só então, com OK explícito, `docker compose run --rm estoque-tools python startup.py sync-once` (grava produtos **e**
  pedidos no Estoque) e decidir se liga `ILYA_AUTO_SYNC_ENABLED`. Nunca agende `sync-once`.

#### Conta sintética: só para o teste, nunca no banco final
A conta `qa-vps@ilya.example.com` é **admin BR+EU**. O banco restaurado da cópia final **não a tem**, então, para rodar o
smoke, ela é recriada à mão e **removida antes de reabrir**. Ensaiado em 2026-11-24 (`ID` = o `id` dela em `users`):
```bash
# recriar: as 3 linhas (users, user_markets, user_platform_permissions) estão guardadas na VPS em
# /opt/ilya-acceptance/synthetic-account-rows.sql (0600, só a conta sintética; o hash é o da homologação)
ID=07585223-1a0e-4ce2-8650-2c67dd02980b     # id da conta qa-vps@ilya.example.com
docker compose exec -T ilya-db psql -U postgres -d ilya -X -q -v ON_ERROR_STOP=1 --single-transaction \
  < /opt/ilya-acceptance/synthetic-account-rows.sql
# o hash guardado é o da homologação: refazer com o pepper de produção (abaixo) antes do login
docker compose exec -T estoque-db psql -U postgres -d estoque -X -q -c \
  "insert into stock_permissions (user_id, role, is_active) values ('$ID','consulta',true)"   # sem isso o login único dá 403
docker compose run --rm --no-deps -u root -v $PWD/rehash_synthetic_account.py:/tmp/rehash.py:ro \
  -v /opt/ilya-acceptance/acceptance.env:/tmp/cred.env:ro ilya-api python /tmp/rehash.py /tmp/cred.env
```
```bash
# REMOVER no fim (uma transação por banco; conferir 0)
docker compose exec -T estoque-db psql -U postgres -d estoque -X -q -v ON_ERROR_STOP=1 -At <<SQL
BEGIN;
DELETE FROM refresh_tokens WHERE user_id IN (SELECT id FROM users WHERE central_user_id = '$ID');
DELETE FROM central_assertion_jtis WHERE user_id = '$ID';
DELETE FROM stock_permissions WHERE user_id = '$ID';
DELETE FROM users WHERE central_user_id = '$ID' AND email LIKE '%@ilya.example.com';
COMMIT;
SQL
docker compose exec -T ilya-db psql -U postgres -d ilya -X -q -v ON_ERROR_STOP=1 -At <<SQL
BEGIN;
DELETE FROM refresh_tokens WHERE user_id = '$ID';
DELETE FROM notifications WHERE user_id = '$ID';
DELETE FROM user_platform_permissions WHERE user_id = '$ID';
DELETE FROM user_markets WHERE user_id = '$ID';
DELETE FROM users WHERE id = '$ID' AND email LIKE '%@ilya.example.com';
COMMIT;
SQL
# conferir: select count(*) from users where email like '%@ilya.example.com'  -> 0 nos dois bancos
```
Depois da remoção, a contagem de linhas volta à da cópia, exceto o que a própria stack grava (`refresh_tokens` expirados são
limpos pelo app; `privacy_events`, `security_audit_events` e `operational_*` ganham linhas de login e de verificação). Se a
conta ficou por engano, **não reabra**.

### 6. Reabrir
Mergear o PR (a Vercel publica os rewrites) → conferir `https://ilya-rust.vercel.app/health/ready`,
login e login único pelo domínio público → acompanhar `docker compose logs -f ilya-api estoque-api`
e a latência por ~30 min. Só depois, trocar `ORDER_EMAIL_MODE` (decisão separada, não faz parte da virada).

**Critérios de "volta" depois do merge** (propostos; o responsável confirma): `/health/ready` ≠ 200 por mais de 5 min,
login falhando para contas reais, `smoke_test` com falha, taxa de 5xx acima de 2% nos primeiros 30 min, ou foto assinada
sem carregar (storage). Qualquer um → "Caminho de volta" abaixo.

## Caminho de volta para o Railway

| Quando | O que fazer |
|---|---|
| Falhou nos passos 3–5 (PR não mergeado) | Restaurar `Caddyfile.pre-virada` e `docker restart ilya-ingress`; despausar os serviços do Railway (ordem inversa do passo 1). Nada foi gravado no Railway desde a pausa: **sem perda de dados**. |
| Falhou depois do merge, sem gravações reais na VPS | Reverter na Vercel (Instant Rollback para o deployment anterior ou `git revert` do `vercel.json`) e despausar o Railway. |
| Falhou depois do merge, **com** gravações reais na VPS | Levar os dados de volta (abaixo), **então** reverter a Vercel e despausar. |

### Levar os dados de volta (ensaiado em 2026-11-24, num Postgres DESCARTÁVEL na VPS; nunca no Railway)
`bash rehearse_return.sh` (em `/opt/ilya-production`) simula e mede: parar as gravações → `pg_dump -Fc --no-owner --no-acl`
dos dois bancos em uso → restaurar em Postgres 18 e 16 descartáveis (rede interna, sem portas) → conferir a contagem de linhas
de todas as tabelas. Com dados novos (uma linha-marcador no Ilya e as linhas que o worker do Estoque gravou: 17 incidentes
operacionais, auditoria), tudo voltou idêntico: **62 tabelas no Ilya e 57 no Estoque, em PG18 e PG16**.

| Etapa | Tempo |
|---|---|
| parar APIs/workers | 2 s |
| dump dos dois bancos | 23 s |
| restaurar em PG18 | 39 s |
| restaurar em PG16 | 48 s |
| **Total da volta (dump + restore + conferência)** | **≈ 2 min** mais religar o Railway e a Vercel |

**Achado importante.** O dump do PG18 **não restaura direto em servidor PG16**: o `pg_restore` 18 emite
`SET transaction_timeout = 0` (novo no PG17) e o servidor recusa (`unrecognized configuration parameter`). Se o Postgres do
Railway for anterior ao 17, restaure assim (testado):
```bash
pg_restore --no-owner --no-acl -f - ilya.dump | sed '/^SET transaction_timeout/d' \
  | psql "$RAILWAY_NEW_DB_URL" -X -q -v ON_ERROR_STOP=1 --single-transaction
```
Com servidor ≥ 17, `pg_restore -d … --no-owner --no-acl --single-transaction --exit-on-error` direto serve.

Para o Railway de verdade (só no dia, com o dono ligando um proxy TCP temporário):
1. Parar `ilya-api`, `estoque-api` e os workers na VPS; `pg_dump -Fc --no-owner --no-acl` dos dois bancos (como o script).
2. Criar um banco **novo** no Postgres do Railway (nunca restaurar sobre o que existe), restaurar, conferir as contagens
   (a mesma `COUNT_SQL` do `swap_data.sh`).
3. Apontar o serviço Railway para o banco novo (variável de conexão) **ou** renomear, com o serviço parado; só então
   despausar. O banco antigo do Railway fica de reserva (não apagar).
4. O schema precisa bater com a imagem que roda no Railway: se a VPS aplicou migrações novas depois da virada, o Railway
   precisa da mesma revisão antes de voltar (o ensaio não aplicou nenhuma: Ilya `showroom_transfers_20261117`, Estoque `0020`).
5. Reverter a Vercel (`vercel.json` / Instant Rollback) e só então despausar o Railway.

Mantenha os serviços e bancos do Railway pausados (não apagados) até a estabilidade ser confirmada.

## Pendências conhecidas (decisão do responsável)

- **Mídia:** `OBJECT_STORAGE_*` aponta para os buckets atuais (a foto assinada do smoke baixa de lá). Se o projeto Railway for
  desligado, é preciso migrar os buckets (`ops/copy_ilya_media.py` já tira o snapshot) e trocar as variáveis.
- **Backups e monitoramento:** nada configurado na stack nova. O worker do Estoque já abre o incidente crítico
  `infra.backup_overdue` (e 16 avisos `commercial.order_uncovered` do escopo comercial). Sem backup, a VPS é o único dono dos dados depois da virada.
- **IP do cliente / rate limit:** `trusted_proxies` fica indefinido (ver passo 4); o rate limit vê o IP da Vercel, como no Railway.
- **Estoque na Vercel:** rewrite do front do Estoque para `/estoque-api/*` (repositório do Estoque, fora deste PR).
- **Divergência Estoque × Ilya** (`reconcile-ilya`, passo 5): reavaliar antes de ligar qualquer sync. Nenhum `sync-once` foi rodado.
- **Limpeza do ensaio de 2026-11-24: feita, com OK do responsável.** Removidos: os bancos `ilya_ensaio_*` e `estoque_ensaio_*`,
  as 4 cópias `*_copy_*` e tudo que `rehearse_return.sh` criou (containers `ilya-return-pg16/18`, rede `ilya-return-net`, os dois dumps
  de produção). **Mantido de propósito:** `estoque_homologacao_20261124` (homologação, intocada). Na virada de verdade,
  `swap_data.sh` e `rehearse_return.sh` criam de novo bancos de reserva e dumps: remova-os só com OK, e **apague os dumps de
  produção da VPS assim que a volta deixar de ser necessária**.
- **Senha do Redis da homologação** apareceu na saída de um comando do ensaio anterior (só homologação): rotacionar.
