"""cria catalogos e vincula produtos existentes ao catalogo Ilya

Revision ID: 0053
Revises: 0052
Create Date: 2026-09-11
"""
import uuid
from alembic import op
import sqlalchemy as sa


revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

# Catálogos iniciais. "Ilya" recebe todo o acervo atual; os demais nascem
# vazios e são preenchidos conforme os produtos forem cadastrados.
_SEED = ["Ilya", "IBTW", "Cerâmica", "Wupa", "Tapete"]


def upgrade() -> None:
    catalogs = op.create_table(
        "catalogs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False, unique=True),
    )
    op.add_column(
        "products",
        sa.Column("catalog_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_products_catalog_id", "products", ["catalog_id"])
    op.create_foreign_key(
        "fk_products_catalog_id", "products", "catalogs", ["catalog_id"], ["id"]
    )

    ilya_id = uuid.uuid4()
    op.bulk_insert(
        catalogs,
        [
            {"id": ilya_id if name == "Ilya" else uuid.uuid4(), "name": name}
            for name in _SEED
        ],
    )
    # Tudo que já está no site pertence ao catálogo Ilya.
    op.execute(
        sa.text("UPDATE products SET catalog_id = :cid").bindparams(cid=ilya_id)
    )


def downgrade() -> None:
    op.drop_constraint("fk_products_catalog_id", "products", type_="foreignkey")
    op.drop_index("ix_products_catalog_id", table_name="products")
    op.drop_column("products", "catalog_id")
    op.drop_table("catalogs")
