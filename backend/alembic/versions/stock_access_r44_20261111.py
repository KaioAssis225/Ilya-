"""Login único com o Estoque Brasil: `users.has_stock_access`.

Coluna aditiva e sem efeito para quem já usa o Ilya (default false). Só o
administrador da plataforma a altera e só vale para quem tem vínculo ativo no
mercado BR; as regras vivem em `app.core.stock_access`.

Sem índice: a coluna é lida por chave primária (emissão do handoff) e em
conjunto pelo painel de administração, que já pagina a tabela de usuários.
"""

from alembic import op
import sqlalchemy as sa


revision = "stock_access_r44"
down_revision = "product_photos_r43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "has_stock_access",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "has_stock_access")
