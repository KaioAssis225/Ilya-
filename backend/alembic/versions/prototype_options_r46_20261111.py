"""Grupos de opcionais que existem só dentro de um protótipo (Portugal).

Aditiva: `optional_categories.prototype_id` e `optionals.prototype_id`, ambas
nulas por padrão (todo opcional existente continua geral) e com FK para o
protótipo (`products.id`, ON DELETE CASCADE). Quem tem `prototype_id` preenchido
é invisível nas listas gerais (negação por padrão em `app.db.market_scope`).

Downgrade: apaga primeiro os grupos/opções de protótipo e depois as colunas.
"""

from alembic import op
import sqlalchemy as sa


revision = "prototype_options_r46"
down_revision = "prototypes_r45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("optional_categories", "optionals"):
        op.add_column(table, sa.Column("prototype_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_prototype", table, "products",
            ["prototype_id"], ["id"], ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_prototype_id", table, ["prototype_id"])


def downgrade() -> None:
    # Aplicações de protótipo apontam para a categoria com RESTRICT: saem antes.
    op.execute(
        "DELETE FROM product_optional_applications WHERE category_id IN "
        "(SELECT id FROM optional_categories WHERE prototype_id IS NOT NULL)"
    )
    op.execute("DELETE FROM optionals WHERE prototype_id IS NOT NULL")
    op.execute("DELETE FROM optional_categories WHERE prototype_id IS NOT NULL")
    for table in ("optionals", "optional_categories"):
        op.drop_index(f"ix_{table}_prototype_id", table_name=table)
        op.drop_constraint(f"fk_{table}_prototype", table, type_="foreignkey")
        op.drop_column(table, "prototype_id")
