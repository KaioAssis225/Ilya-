"""Marca se o cliente já foi contactado (ficha de cliente de Portugal).

Coluna nova NOT NULL com default false: as linhas existentes recebem "não
contactado" sem reescrita manual. Nenhum índice único é criado aqui.
"""

from alembic import op
import sqlalchemy as sa

revision = "client_contacted_r39"
down_revision = "order_item_special_r38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("contacted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("clients", "contacted")
