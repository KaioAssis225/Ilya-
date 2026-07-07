"""add products.type column (never had a migration — model-only drift)

O modelo Product sempre teve a coluna `type`, mas nenhuma migration do
historico a criava — bancos que passaram por `Base.metadata.create_all()`
numa fase inicial (ex.: dev local) ja tinham a coluna; bancos criados do
zero via `alembic upgrade head` (ex.: Railway) nunca a recebiam, causando
UndefinedColumnError em qualquer SELECT/INSERT em products.

IF NOT EXISTS torna a migration segura para ambos os casos.
"""
from alembic import op
import sqlalchemy as sa

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS type VARCHAR(50) NOT NULL DEFAULT 'Outro'"
    )


def downgrade() -> None:
    op.drop_column('products', 'type')
