"""Protótipos (Portugal): flag em `products`, dono, sequência PROT e permissão.

Aditiva e sem efeito para quem já usa o Ilya:

* `products.is_prototype` (default false) e `products.created_by_user_id`;
* CHECKs: protótipo só no mercado EU, sempre com dono e com o prefixo `PROT-`
  (a recíproca fica na aplicação, para não quebrar linha legada);
* `prototype_code_seq`: numeração atômica dos códigos `PROT-0001`…;
* `user_markets.can_manage_prototypes` (default false), válido só no vínculo EU.

Downgrade: remove os protótipos (os filhos saem por ON DELETE CASCADE), depois
as constraints, o índice, a sequence e as colunas.
"""

import logging

from alembic import op
import sqlalchemy as sa

log = logging.getLogger("alembic.runtime.migration")

revision = "prototypes_r45"
down_revision = "stock_access_r44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_prototype", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "products",
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_products_created_by_user",
        "products", "users",
        ["created_by_user_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_products_prototype_eu", "products",
        "NOT is_prototype OR market_code = 'EU'",
    )
    op.create_check_constraint(
        "ck_products_prototype_owner", "products",
        "NOT is_prototype OR created_by_user_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_products_prototype_code_prefix", "products",
        "NOT is_prototype OR product_code LIKE 'PROT-%'",
    )
    op.create_index(
        "ix_products_prototype_owner", "products",
        ["created_by_user_id", "id"],
        postgresql_where=sa.text("is_prototype"),
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS prototype_code_seq")

    op.add_column(
        "user_markets",
        sa.Column(
            "can_manage_prototypes", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_check_constraint(
        "ck_user_markets_prototypes_eu", "user_markets",
        "NOT can_manage_prototypes OR market_code = 'EU'",
    )
    _grant_to_james()


def _grant_to_james() -> None:
    """Migração de dados: liga a permissão para quem abriu o pedido ("James").

    Liga só se existir EXATAMENTE UM vínculo EU ativo cuja identidade ativa tenha
    `full_name` começando com "James" (sem diferenciar maiúsculas). Com 0 ou mais
    de 1, não toca em nada e registra o motivo no log. Sem e-mail nem id fixo.
    O administrador muda isso depois na Plataforma; o downgrade não desmarca.
    """
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT um.user_id, um.role FROM user_markets um "
        "JOIN users u ON u.id = um.user_id "
        "WHERE um.market_code = 'EU' AND um.status = 'active' "
        "AND um.role IS NOT NULL AND u.is_active "
        "AND lower(u.full_name) LIKE 'james%'"
    )).fetchall()
    if len(rows) != 1:
        log.warning(
            "prototypes_r45: permissão de protótipos NÃO foi ligada automaticamente "
            "(vínculos EU ativos com nome iniciado em 'James': %d; esperado exatamente 1). "
            "Ligue pela Plataforma → Identidades e acessos.",
            len(rows),
        )
        return
    user_id, role = rows[0]
    bind.execute(
        sa.text(
            "UPDATE user_markets SET can_manage_prototypes = true "
            "WHERE user_id = :user_id AND market_code = 'EU'"
        ),
        {"user_id": user_id},
    )
    log.info(
        "prototypes_r45: permissão de protótipos ligada no vínculo EU do usuário %s (papel %s).",
        user_id, role,
    )
    if role not in ("admin", "vendedor", "produtos"):
        log.warning(
            "prototypes_r45: o papel '%s' não abre a área de protótipos (só admin, vendedor, produtos).",
            role,
        )


def downgrade() -> None:
    op.drop_constraint("ck_user_markets_prototypes_eu", "user_markets", type_="check")
    op.drop_column("user_markets", "can_manage_prototypes")

    # Os protótipos só existem com estas colunas; sem elas viram produto
    # normal por engano. Apagar é o único destino seguro (filhos em CASCADE).
    op.execute("DELETE FROM products WHERE is_prototype")
    op.execute("DROP SEQUENCE IF EXISTS prototype_code_seq")
    op.drop_index("ix_products_prototype_owner", table_name="products")
    op.drop_constraint("ck_products_prototype_code_prefix", "products", type_="check")
    op.drop_constraint("ck_products_prototype_owner", "products", type_="check")
    op.drop_constraint("ck_products_prototype_eu", "products", type_="check")
    op.drop_constraint("fk_products_created_by_user", "products", type_="foreignkey")
    op.drop_column("products", "created_by_user_id")
    op.drop_column("products", "is_prototype")
