"""Galeria de fotos do produto: tabela `product_photos` com foto principal.

Aditiva e compatível com a API anterior: `products.photo_path` continua sendo a
foto principal. O backfill copia a foto atual de cada produto como principal
(posição 0) e não move nenhum arquivo. Reexecutável: não duplica linhas.
"""

from alembic import op
import sqlalchemy as sa


revision = "product_photos_r43"
down_revision = "supplied_fabric_eu_r42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_photos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("photo_path", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("product_id", "photo_path", name="uq_product_photos_product_path"),
    )
    op.create_index(
        "ix_product_photos_product_position", "product_photos", ["product_id", "position"]
    )
    op.create_index(
        "uq_product_photos_one_primary",
        "product_photos",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.execute(
        """
        INSERT INTO product_photos (id, product_id, photo_path, position, is_primary)
        SELECT gen_random_uuid(), p.id, p.photo_path, 0, true
        FROM products p
        WHERE p.photo_path IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM product_photos f WHERE f.product_id = p.id)
        """
    )


def downgrade() -> None:
    # Garante que a coluna continua com a principal antes de perder a tabela.
    op.execute(
        """
        UPDATE products p SET photo_path = f.photo_path
        FROM product_photos f
        WHERE f.product_id = p.id AND f.is_primary
        """
    )
    op.drop_index("uq_product_photos_one_primary", table_name="product_photos")
    op.drop_index("ix_product_photos_product_position", table_name="product_photos")
    op.drop_table("product_photos")
