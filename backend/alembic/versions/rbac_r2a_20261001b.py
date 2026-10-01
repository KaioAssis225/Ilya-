"""RBAC R2a: user_markets authority columns, user_platform_permissions, refresh_tokens scope

Revision ID: rbac_r2a_20261001b
Revises: vat_approval_20261001
Create Date: 2026-10-01

Schema aditivo: apenas adiciona colunas/tabelas, sem drop de dados existentes.

MUDANÇAS:
  user_markets   — role (nullable), status (pending/active/suspended), linked_client_id,
                   rep_id, can_view_dashboard, can_approve_tax
  user_platform_permissions — nova tabela (user_id, capability, is_active); sem grants iniciais
  refresh_tokens — scope (market/platform); active_market perde NOT NULL e server_default='BR'

BACKFILL BR:
  Papéis legados globais mapeados por papel + validação de FK de mercado:
    representante + rep_id -> representative.market_code='BR'  -> active, role='representante'
    cliente       + linked_id -> client.market_code='BR'       -> active, role='cliente'
    vendedor      + linked_id -> client.market_code='BR'       -> active, role='cliente' (efetivo)
    admin / cadastros / produtos / executivo                   -> active, role=papel
    vendedor sem linked_id                                     -> active, role='vendedor'
    demais (FK invalida, mercado errado, papel ausente)        -> pending, role=NULL

BACKFILL EU:
  Todos os vinculos EU existentes (criados automaticamente para admins em
  europa_multimarket_20260820) permanecem pending: EU esta desabilitado em
  producao e requer revisao nominal antes de ativacao.

ROLLBACK:
  Seguro enquanto nenhuma sessao de plataforma (scope='platform') foi emitida.
  Se existirem tokens com active_market=NULL ao fazer downgrade, o script
  os revoga e so entao preenche 'BR' antes de recolocar NOT NULL. Nenhum token
  de plataforma e convertido em sessao comercial valida.
  Janela de deploy: aplicar antes de expor qualquer rota de login de plataforma
  (R2b+). Em R2a nao ha rotas de plataforma, portanto o rollback e trivial.

RISCOS:
  - O backfill de user_markets le users, clients e representatives sem lock de
    tabela. Em deploy com carga, os UPDATEs sao sequenciais; nenhum conflito de
    escrita ocorre porque as colunas novas ainda nao sao lidas por nenhuma rota.
  - active_market passando de NOT NULL para nullable: writers antigos que OMITEM
    active_market em INSERTs passarao a inserir NULL em vez de 'BR'. O CHECK
    ck_refresh_tokens_scope_market rejeitara scope='market' com active_market=NULL,
    evitando tokens invalidos silenciosos. Writers que informam active_market
    explicitamente nao sao afetados.
"""
from alembic import op
import sqlalchemy as sa


revision = "rbac_r2a_20261001b"
down_revision = "vat_approval_20261001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. user_markets: colunas de autoridade comercial por mercado ──────────
    # Adicionadas nullable para permitir backfill antes de travar status NOT NULL.
    # Booleans NOT NULL com server_default podem ser adicionados direto.
    op.add_column("user_markets", sa.Column("role", sa.String(30), nullable=True))
    op.add_column("user_markets", sa.Column("status", sa.String(20), nullable=True))
    op.add_column(
        "user_markets",
        sa.Column("linked_client_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "user_markets",
        sa.Column("rep_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "user_markets",
        sa.Column("can_view_dashboard", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "user_markets",
        sa.Column("can_approve_tax", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_user_markets_linked_client_id",
        "user_markets", "clients",
        ["linked_client_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_markets_rep_id",
        "user_markets", "representatives",
        ["rep_id"], ["id"],
        ondelete="RESTRICT",
    )

    # ── 2. Backfill EU: todos os vinculos EU permanecem pending ───────────────
    op.execute(sa.text(
        "UPDATE user_markets SET status = 'pending' WHERE market_code = 'EU'"
    ))

    # ── 3. Backfill BR por papel legado ───────────────────────────────────────
    # A ordem importa: cada UPDATE testa um papel especifico e so afeta linhas
    # ainda sem status (status IS NULL). Ambiguos ficam para a varredura final.

    # representante com FK valida: rep_id -> representatives.id, market_code='BR'
    op.execute(sa.text(
        "UPDATE user_markets um"
        " SET status = 'active',"
        "     role   = 'representante',"
        "     rep_id = u.rep_id"
        " FROM users u"
        " WHERE um.user_id       = u.id"
        "   AND um.market_code   = 'BR'"
        "   AND u.role           = 'representante'"
        "   AND u.rep_id IS NOT NULL"
        "   AND EXISTS ("
        "       SELECT 1 FROM representatives r"
        "       WHERE r.id = u.rep_id AND r.market_code = 'BR'"
        "   )"
        "   AND um.status IS NULL"
    ))

    # cliente com FK valida: linked_id -> clients.id, market_code='BR'
    op.execute(sa.text(
        "UPDATE user_markets um"
        " SET status           = 'active',"
        "     role             = 'cliente',"
        "     linked_client_id = u.linked_id"
        " FROM users u"
        " WHERE um.user_id       = u.id"
        "   AND um.market_code   = 'BR'"
        "   AND u.role           = 'cliente'"
        "   AND u.linked_id IS NOT NULL"
        "   AND EXISTS ("
        "       SELECT 1 FROM clients c"
        "       WHERE c.id = u.linked_id AND c.market_code = 'BR'"
        "   )"
        "   AND um.status IS NULL"
    ))

    # vendedor + linked_id: linked_id aponta para client em BR (cliente efetivo)
    op.execute(sa.text(
        "UPDATE user_markets um"
        " SET status           = 'active',"
        "     role             = 'cliente',"
        "     linked_client_id = u.linked_id"
        " FROM users u"
        " WHERE um.user_id       = u.id"
        "   AND um.market_code   = 'BR'"
        "   AND u.role           = 'vendedor'"
        "   AND u.linked_id IS NOT NULL"
        "   AND EXISTS ("
        "       SELECT 1 FROM clients c"
        "       WHERE c.id = u.linked_id AND c.market_code = 'BR'"
        "   )"
        "   AND um.status IS NULL"
    ))

    # papeis diretos sem vinculo de terceiro
    op.execute(sa.text(
        "UPDATE user_markets um"
        " SET status = 'active',"
        "     role   = u.role::text"
        " FROM users u"
        " WHERE um.user_id     = u.id"
        "   AND um.market_code = 'BR'"
        "   AND u.role IN ('admin', 'cadastros', 'produtos', 'executivo')"
        "   AND um.status IS NULL"
    ))

    # vendedor sem linked_id
    op.execute(sa.text(
        "UPDATE user_markets um"
        " SET status = 'active',"
        "     role   = 'vendedor'"
        " FROM users u"
        " WHERE um.user_id     = u.id"
        "   AND um.market_code = 'BR'"
        "   AND u.role         = 'vendedor'"
        "   AND u.linked_id IS NULL"
        "   AND um.status IS NULL"
    ))

    # Restantes: BR ambiguos (rep/client FK invalida ou mercado errado) -> pending
    op.execute(sa.text(
        "UPDATE user_markets SET status = 'pending' WHERE status IS NULL"
    ))

    # ── 4. status NOT NULL + CHECK ────────────────────────────────────────────
    op.alter_column(
        "user_markets", "status",
        existing_type=sa.String(20),
        nullable=False,
        server_default="pending",
    )
    op.create_check_constraint(
        "ck_user_markets_status",
        "user_markets",
        "status IN ('pending', 'active', 'suspended')",
    )
    op.create_check_constraint(
        "ck_user_markets_role",
        "user_markets",
        "role IS NULL OR role IN "
        "('admin', 'vendedor', 'representante', 'cadastros', "
        "'produtos', 'cliente', 'executivo')",
    )
    op.create_check_constraint(
        "ck_user_markets_active_role",
        "user_markets",
        "status != 'active' OR role IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_user_markets_role_links",
        "user_markets",
        "(role IS NULL AND linked_client_id IS NULL AND rep_id IS NULL) OR "
        "(role = 'cliente' AND linked_client_id IS NOT NULL AND rep_id IS NULL) OR "
        "(role = 'representante' AND rep_id IS NOT NULL AND linked_client_id IS NULL) OR "
        "(role IN ('admin', 'vendedor', 'cadastros', 'produtos', 'executivo') "
        "AND linked_client_id IS NULL AND rep_id IS NULL)",
    )

    # ── 5. user_platform_permissions ──────────────────────────────────────────
    # Capacidades de plataforma (sessao sem mercado). Sem grants iniciais:
    # a conta de admin de plataforma sera concedida nominalmente apos validacao.
    op.create_table(
        "user_platform_permissions",
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("capability", sa.String(50), primary_key=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── 6. refresh_tokens: scope market/platform ──────────────────────────────

    # Passo 1: scope nullable para permitir o backfill.
    op.add_column(
        "refresh_tokens",
        sa.Column("scope", sa.String(20), nullable=True),
    )
    # Passo 2: todos os tokens existentes sao de mercado.
    op.execute(sa.text("UPDATE refresh_tokens SET scope = 'market'"))
    # Passo 3: NOT NULL com server_default para novos tokens comerciais.
    op.alter_column(
        "refresh_tokens", "scope",
        existing_type=sa.String(20),
        nullable=False,
        server_default="market",
    )

    # Passo 4: active_market perde NOT NULL e server_default='BR'.
    # Tokens de plataforma (scope='platform') nao terao active_market.
    # O CHECK abaixo garante que market-scope nunca insira active_market=NULL.
    op.alter_column(
        "refresh_tokens", "active_market",
        existing_type=sa.String(2),
        nullable=True,
        server_default=None,
    )

    # Passo 5: CHECKs que unem scope e active_market.
    # Compativel com writers antigos: eles informam active_market explicitamente
    # e recebem scope='market' pelo server_default.
    op.create_check_constraint(
        "ck_refresh_tokens_scope_market",
        "refresh_tokens",
        "(scope = 'market' AND active_market IS NOT NULL)"
        " OR (scope = 'platform' AND active_market IS NULL)",
    )
    op.create_check_constraint(
        "ck_refresh_tokens_scope_values",
        "refresh_tokens",
        "scope IN ('market', 'platform')",
    )


def downgrade() -> None:
    # AVISO: seguro apenas se nenhum token com scope='platform' foi emitido.
    # Sessões de plataforma são revogadas antes de preencher BR. Isso impede
    # que um refresh token de plataforma vire sessão comercial no código antigo.

    # refresh_tokens
    op.drop_constraint("ck_refresh_tokens_scope_values", "refresh_tokens", type_="check")
    op.drop_constraint("ck_refresh_tokens_scope_market", "refresh_tokens", type_="check")
    op.execute(sa.text(
        "UPDATE refresh_tokens "
        "SET revoked = TRUE, revoked_at = now(), active_market = 'BR' "
        "WHERE scope = 'platform' OR active_market IS NULL"
    ))
    op.alter_column(
        "refresh_tokens", "active_market",
        existing_type=sa.String(2),
        nullable=False,
        server_default="BR",
    )
    op.drop_column("refresh_tokens", "scope")

    # user_platform_permissions
    op.drop_table("user_platform_permissions")

    # user_markets
    op.drop_constraint("ck_user_markets_role_links", "user_markets", type_="check")
    op.drop_constraint("ck_user_markets_active_role", "user_markets", type_="check")
    op.drop_constraint("ck_user_markets_role", "user_markets", type_="check")
    op.drop_constraint("ck_user_markets_status", "user_markets", type_="check")
    op.drop_constraint("fk_user_markets_rep_id", "user_markets", type_="foreignkey")
    op.drop_constraint("fk_user_markets_linked_client_id", "user_markets", type_="foreignkey")
    op.drop_column("user_markets", "can_approve_tax")
    op.drop_column("user_markets", "can_view_dashboard")
    op.drop_column("user_markets", "rep_id")
    op.drop_column("user_markets", "linked_client_id")
    op.drop_column("user_markets", "status")
    op.drop_column("user_markets", "role")
