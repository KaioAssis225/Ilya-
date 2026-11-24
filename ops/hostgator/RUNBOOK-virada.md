# Virada Railway → VPS HostGator (Ilya + Estoque)

Stack de produção em `/opt/ilya-production` (Docker Compose, projeto `ilya-production`).
**Nada nela é público**: as APIs escutam só em `127.0.0.1:19080` (Ilya) e
`127.0.0.1:19082` (Estoque). O Caddy (`ilya-ingress`) segue com o Caddyfile antigo
(só `/health/*` e `/estoque-health/*`, apontando para a homologação).

> **Este PR não pode ser mergeado antes da virada.** `frontend/vercel.json` já aponta
> os rewrites para `https://143.95.189.88`; o merge faz a Vercel publicar isso e o
> tráfego real muda de lugar.

## O que existe hoje (ensaio)

| Peça | Estado |
|---|---|
| Ilya: API, migração, worker de e-mail, Postgres 18, Redis 8 | no ar, saudáveis |
| Estoque: API, migração, worker operacional, Postgres 18, Redis 8 | no ar, saudáveis |
| Imagens | `ilya-production-api:899ad3e0`, `ilya-production-email:899ad3e0`, `ilya-production-estoque:5c94f57` (tags novas das imagens homologadas) |
| Dados do ensaio | Ilya = snapshot `ilya_copy_20261124_120153_54effd76`; Estoque = `estoque_copy_20261124_130014_5b41e52f` |
| Segredos | `PASSWORD_PEPPER`, `SECRET_KEY`, `MEDIA_SIGNING_KEY`, par do login único: **copiados do Railway**. Senhas de banco/Redis: novas, geradas na VPS |
| Roles | `ilya_app`, `estoque_app`, `ilya_estoque_readonly` (GRANTs iguais aos de produção; `hashed_password` nunca liberado) |
| Travas | `ORDER_EMAIL_MODE=off`, Moloni e webhook desligados, sync do Estoque desligado (`ILYA_AUTO_SYNC_*=false`) |
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

## Antes do dia da virada

1. Imagens finais: a revisão que vai para produção precisa estar nas tags acima
   (workflow `hostgator-image.yml` gera `ilya.tar.gz`; ajuste `.env` se mudar a tag).
2. Backup do Caddyfile: `cp /opt/ilya-ingress/Caddyfile /opt/ilya-ingress/Caddyfile.pre-virada`.
3. **Ensaiar o passo 3 (trocar os dados) uma vez** — ele não foi ensaiado, só a carga inicial.
4. Decidir a conta de teste (ver passo 5) e avisar a janela às pessoas.

## Virada

### 1. Pausar as gravações (Railway)
Ordem: (a) Estoque: cron/sync e worker; (b) Estoque API; (c) worker de e-mail do Ilya;
(d) API do Ilya. Confirme zero conexões de escrita no Postgres do Railway. Não apague
nada no Railway: pausado, ele é o caminho de volta.

### 2. Cópias finais
```powershell
# Ilya (consistente, somente leitura na origem) -> ilya_copy_<carimbo> na VPS
$env:PRODUCTION_DATABASE_URL = "<URL do Postgres do Ilya>"   # vem do cofre, não do chat
python ops/copy_railway_to_vps.py root@143.95.189.88
```
Estoque: mesmo procedimento com o Postgres do Estoque, para `ilya-estoque-pg`
(`estoque_copy_<carimbo>`). **Não há script versionado para o Estoque** — pendência.

### 3. Restaurar nesta stack
```bash
cd /opt/ilya-production
docker compose stop ilya-api ilya-email-worker estoque-api estoque-worker
# restaura em banco NOVO, sem tocar no atual (o antigo vira o "ensaio" e fica de reserva)
docker compose exec -T ilya-db psql -U postgres -c "CREATE DATABASE ilya_new OWNER ilya_app"
docker exec ilya-railway-copy-db pg_dump -U postgres -d ilya_copy_<carimbo> --no-owner --no-acl \
 | grep -v -E "^(COMMENT ON EXTENSION|CREATE EXTENSION)" \
 | docker compose exec -T ilya-db psql -U ilya_app -d ilya_new -X -q -v ON_ERROR_STOP=1 --single-transaction
# (Estoque: igual, com estoque-db / estoque_app / ilya-estoque-pg)
# confira contagens contra a origem; só então troque os nomes:
docker compose exec -T ilya-db psql -U postgres -d postgres -c "ALTER DATABASE ilya RENAME TO ilya_ensaio" \
  -c "ALTER DATABASE ilya_new RENAME TO ilya"
python3 bootstrap_roles.py roles && python3 bootstrap_roles.py grants && python3 bootstrap_roles.py verify
docker compose up -d        # a migração roda sobre o banco já restaurado (esperado: nenhuma mudança)
```
Remover `ilya_ensaio` (ou volumes antigos) é destrutivo: só com OK explícito do responsável.

### 4. Abrir as rotas no Caddy
Substitua o Caddyfile (guarde o `.pre-virada`). Como `admin off`, recarregar = reiniciar o container.
```caddyfile
{
	admin off
}
https://143.95.189.88 {
	tls {
		issuer acme {
			dir https://acme-v02.api.letsencrypt.org/directory
			profile shortlived
		}
	}
	@ilya path /api/v1/* /static/* /health/live /health/ready
	handle @ilya {
		reverse_proxy 127.0.0.1:19080
	}
	@stock_health path /estoque-health/live /estoque-health/ready
	handle @stock_health {
		uri replace /estoque-health /health
		reverse_proxy 127.0.0.1:19082
	}
	# PROPOSTA: caminho público do Estoque. Exige o rewrite correspondente no
	# vercel.json do repositório do Estoque (fora deste PR).
	handle_path /estoque-api/* {
		reverse_proxy 127.0.0.1:19082
	}
	handle {
		respond 404
	}
}
```
```bash
docker run --rm -v /opt/ilya-ingress/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile
docker restart ilya-ingress
```

### 5. Testar (antes de mergear)
- `curl -sk https://143.95.189.88/health/ready` e `/estoque-health/ready` → 200.
- A Vercel cria um **preview** deste PR já com os rewrites novos: logue por ele nos mercados BR e EU,
  abra um pedido de leitura e use o login único para o Estoque.
- `python3 smoke_test.py --credentials-file …` na VPS (conta sintética, só em 127.0.0.1).
- `docker compose run --rm estoque-tools python startup.py reconcile-ilya` (só leitura).
- Só então, com OK explícito, `docker compose run --rm estoque-tools python startup.py sync-once`
  (grava produtos **e** pedidos no Estoque) e decidir se liga `ILYA_AUTO_SYNC_ENABLED`.
- ⚠ A conta sintética é **admin BR+EU**. Se for criada no banco final para este teste
  (copiar linhas de `users`/`user_markets` do banco de homologação e rodar
  `rehash_synthetic_account.py`, porque o pepper difere), **remova-a antes de reabrir**
  (`users`, `user_markets`, `stock_permissions` e a âncora no Estoque).

### 6. Reabrir
Mergear o PR (a Vercel publica os rewrites) → conferir `https://ilya-rust.vercel.app/health/ready`,
login e login único pelo domínio público → acompanhar `docker compose logs -f ilya-api estoque-api`
e a latência por ~30 min. Só depois, trocar `ORDER_EMAIL_MODE` (decisão separada, não faz parte da virada).

## Caminho de volta para o Railway

| Quando | O que fazer |
|---|---|
| Falhou nos passos 3–5 (PR não mergeado) | Restaurar `Caddyfile.pre-virada` e `docker restart ilya-ingress`; despausar os serviços do Railway (ordem inversa do passo 1). Nada foi gravado no Railway desde a pausa: **sem perda de dados**. |
| Falhou depois do merge, sem gravações reais na VPS | Reverter na Vercel (Instant Rollback para o deployment anterior ou `git revert` do `vercel.json`) e despausar o Railway. |
| Falhou depois do merge, **com** gravações reais na VPS | Parar `ilya-api`/`estoque-api` na VPS, tirar dump (`pg_dump -Fc`) dos dois bancos, restaurar no Postgres do Railway (banco novo, validar, trocar), então reverter a Vercel e despausar. É o único caminho com perda possível se não for ensaiado: **ensaiar antes**. |

Mantenha os serviços e bancos do Railway pausados (não apagados) até a estabilidade ser confirmada.

## Pendências conhecidas (decisão do responsável)

- **Mídia:** `OBJECT_STORAGE_*` aponta para os buckets atuais. Se o projeto Railway for desligado,
  é preciso migrar os buckets (`ops/copy_ilya_media.py` já tira o snapshot) e trocar as variáveis.
- **IP do cliente:** o Caddy não repassa o `X-Forwarded-For` que a Vercel manda, então o rate limit
  e os logs veem o IP do proxy. `FORWARDED_ALLOW_IPS=172.29.10.1` (gateway da rede `edge`) já está pronto;
  falta decidir `trusted_proxies` no Caddy.
- **Backups** da stack nova (banco do Ilya e do Estoque) e monitoramento: ainda não configurados.
- **Estoque na Vercel:** rewrite do front do Estoque para o caminho público escolhido no passo 4.
- **Divergência Estoque × Ilya:** `reconcile-ilya` no ensaio acusa pedidos/produtos a mais no Estoque
  (cópias de horários diferentes e escopo automático desligado). Reavaliar na cópia final.
