"""R13: grupos de produto por mercado — Portugal ganha grupos próprios, sem IPI.

Revision ID: eu_product_groups_r13_20261008
Revises: login_protection_r12_20261007
Create Date: 2026-10-08

Até aqui `product_groups` era global e carregava só a regra brasileira (IPI);
por isso tipos EU não podiam ter grupo (R7 deixou essa relação de fora e o
backend recusava o vínculo). Decisão de 08/10/2026: Portugal organiza seus
subgrupos em grupos próprios, de mercado EU e sem alíquota.

- `product_groups.market_code` (FK `markets.code`); linhas existentes = BR.
- Nome único por mercado (antes único global), para BR e EU poderem ter o
  mesmo nome de grupo.
- `ck_product_groups_eu_sem_ipi`: grupo EU tem `ipi = 0`. Pedido EU usa o IVA
  aprovado de `product_markets` e nunca lê o grupo; o check impede que um
  grupo EU passe a carregar uma alíquota por engano.
- `product_types -> product_groups` vira FK composta `(group_id, market_code)`,
  com `SET NULL (group_id)` (mesma forma do R7): o banco rejeita tipo EU em
  grupo BR e vice-versa.

Abortiva: se existir tipo apontando para grupo de outro mercado (hoje, tipo EU
com grupo), falha nomeando a contagem em vez de aplicar pela metade.
"""
import sqlalchemy as sa
from alembic import op


revision = "eu_product_groups_r13_20261008"
down_revision = "login_protection_r12_20261007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    crossed = conn.exec_driver_sql(
        "SELECT count(*) FROM product_types WHERE market_code <> 'BR' AND group_id IS NOT NULL"
    ).scalar() or 0
    if crossed:
        raise RuntimeError(
            "Migration abortada — há "
            f"{crossed} tipo(s) não-BR apontando para grupo fiscal BR. "
            "Desvincule-os antes de separar os grupos por mercado."
        )

    op.add_column(
        "product_groups",
        sa.Column(
            "market_code",
            sa.String(2),
            sa.ForeignKey("markets.code", name="fk_product_groups_market"),
            nullable=False,
            server_default="BR",
        ),
    )
    op.execute("ALTER TABLE product_groups DROP CONSTRAINT IF EXISTS product_groups_name_key")
    op.create_unique_constraint(
        "uq_product_groups_market_name", "product_groups", ["market_code", "name"]
    )
    op.create_unique_constraint(
        "uq_product_groups_id_market", "product_groups", ["id", "market_code"]
    )
    op.create_check_constraint(
        "ck_product_groups_eu_sem_ipi", "product_groups", "market_code = 'BR' OR ipi = 0"
    )

    op.drop_constraint("fk_product_types_group_id", "product_types", type_="foreignkey")
    op.execute(
        """
        ALTER TABLE product_types
        ADD CONSTRAINT fk_product_types_group_same_market
        FOREIGN KEY (group_id, market_code)
        REFERENCES product_groups (id, market_code)
        ON DELETE SET NULL (group_id)
        """
    )


def downgrade() -> None:
    # Grupos EU não existem no modelo anterior: os tipos EU perdem o grupo e os
    # grupos EU são removidos antes de voltar ao nome único global.
    op.execute(
        "UPDATE product_types SET group_id = NULL WHERE market_code <> 'BR' AND group_id IS NOT NULL"
    )
    op.execute("DELETE FROM product_groups WHERE market_code <> 'BR'")

    op.drop_constraint("fk_product_types_group_same_market", "product_types", type_="foreignkey")
    op.create_foreign_key(
        "fk_product_types_group_id", "product_types", "product_groups",
        ["group_id"], ["id"], ondelete="SET NULL",
    )
    op.drop_constraint("ck_product_groups_eu_sem_ipi", "product_groups", type_="check")
    op.drop_constraint("uq_product_groups_id_market", "product_groups", type_="unique")
    op.drop_constraint("uq_product_groups_market_name", "product_groups", type_="unique")
    op.create_unique_constraint("product_groups_name_key", "product_groups", ["name"])
    op.drop_constraint("fk_product_groups_market", "product_groups", type_="foreignkey")
    op.drop_column("product_groups", "market_code")
