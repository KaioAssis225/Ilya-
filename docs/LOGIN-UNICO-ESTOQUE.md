# Login único Ilya ↔ Estoque Brasil (lado do Ilya)

O Ilya é o **porteiro**: sabe quem é a pessoa e se ela *pode* usar o Estoque
(`users.has_stock_access`). O papel dentro do Estoque é decidido no Estoque.
Contrato completo: `docs/plans/PEDIDO-AO-MAESTRO-DO-ILYA.md` do repositório do Estoque.

## Regras (todas no servidor)

- Só o **administrador da plataforma** (`platform_admin`) altera `has_stock_access`
  (`PATCH /api/v1/users/{id}`). Ninguém mais vê o campo; `/auth/me` só devolve
  `can_access_stock`, calculado.
- **Só Brasil**: exige vínculo **ativo** em `user_markets` com `market_code = 'BR'`.
  Usuário só-EU → 422 ao marcar; o emissor responde 403 genérico mesmo com a
  coluna marcada. O link "Estoque" só aparece na sessão do mercado BR.
- `cliente` e `benchmark_readonly` nunca recebem o acesso (422; 403 no emissor).
- Mudar o campo incrementa `users.auth_version` (o Estoque lê esse número e
  derruba a sessão em ≤ ~1 min) e é auditado em `privacy_events`
  (`stock_access_granted` / `stock_access_revoked`; emissão em
  `stock_handoff_issued` / `stock_handoff_denied`, sem gravar o token).
- Retirar o BR (ou virar cliente) retira o acesso junto (`reason = auto_*`).

## Emissor

`POST /api/v1/stock/handoff` (Bearer de sessão de mercado **ou** plataforma):
`200 {"assertion": "<jwt ES256>", "expires_in": 60}`, `401`, `403` (genérico),
`429` (10/min por usuário), `503` (chave não configurada).
`GET /api/v1/stock/link` devolve `{"origin"}` (a origem do Estoque, vinda do
servidor) para o menu e para `/estoque/conectar`.

Token: header `alg=ES256, typ=JWT, kid`; claims `iss="ilya"`, `aud="ilya-estoque"`,
`typ="stock-handoff"`, `sub` (users.id), `ver` (auth_version), `iat`, `exp=iat+60`,
`jti` (uuid4). Nada de e-mail, nome ou papel.

## Variáveis de ambiente (Railway do Ilya, colocadas pelo dono)

| Variável | Conteúdo | Segredo? |
|---|---|---|
| `STOCK_HANDOFF_PRIVATE_KEY` | chave privada EC P-256 em PEM | **SIM** |
| `STOCK_HANDOFF_KID` | ex.: `stock-handoff-2026-11` | não |
| `STOCK_APP_ORIGIN` | ex.: `https://ilya-estoque.vercel.app` (https, sem barra final nem caminho; `http` só em localhost) | não |

## Gerar o par de chaves (feito pelo DONO, nunca por uma sessão de IA)

```bash
openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt -out ilya-handoff-private.pem
openssl ec -in ilya-handoff-private.pem -pubout -out ilya-handoff-public.pem
```

- `ilya-handoff-private.pem` → **só** o Railway do Ilya, em `STOCK_HANDOFF_PRIVATE_KEY`
  (colar o PEM inteiro, com as linhas `-----BEGIN/END PRIVATE KEY-----`).
- `ilya-handoff-public.pem` → entrega ao Estoque (`ILYA_HANDOFF_PUBLIC_KEYS`, indexada pelo mesmo `kid`).
- Depois de colar no Railway, **apague** a privada do disco (`shred -u` / mover para o cofre).
  Nunca commitar, nunca enviar por chat.
- Rotação: gere outro par com outro `kid`, coloque a nova pública no Estoque
  (as duas valem ao mesmo tempo), troque `STOCK_HANDOFF_PRIVATE_KEY` + `STOCK_HANDOFF_KID`
  no Ilya e, depois de ~5 min, remova a pública antiga.

## Leitura do mercado BR pelo Estoque (conta somente-leitura)

```sql
GRANT SELECT (id, email, username, full_name, is_active, must_change_password,
              auth_version, has_stock_access) ON users TO <conta_readonly_do_estoque>;
GRANT SELECT (user_id, market_code, role, status) ON user_markets TO <conta_readonly_do_estoque>;
```

Nunca `hashed_password`. Decisão "tem BR" (junto de `is_active`, `has_stock_access`,
`auth_version = ver` do token):

```sql
SELECT u.id
FROM users u
WHERE u.id = :sub
  AND u.is_active
  AND u.has_stock_access
  AND u.auth_version = :ver
  AND EXISTS (SELECT 1 FROM user_markets m
              WHERE m.user_id = u.id AND m.market_code = 'BR'
                AND m.status = 'active' AND m.role IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM user_markets m
                  WHERE m.user_id = u.id
                    AND m.role IN ('cliente', 'benchmark_readonly'));
```

## Cabeçalhos de segurança

Nada foi alterado. O Ilya não define `Cross-Origin-Opener-Policy` (nem no backend nem em
`frontend/vercel.json`), então `window.opener` funciona; `connect-src`/`frame-ancestors`
não afetam `window.open`/`postMessage`. **O Estoque também não pode definir COOP `same-origin`
na página `/entrar-ilya`.**
