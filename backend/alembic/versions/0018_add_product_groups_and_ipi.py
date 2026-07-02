"""add product_groups and ipi fiscal fields"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'product_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('ipi', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.add_column('product_types', sa.Column('group_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_product_types_group_id', 'product_types', 'product_groups',
        ['group_id'], ['id'], ondelete='SET NULL',
    )

    op.add_column('order_items', sa.Column('ipi_rate', sa.Numeric(5, 2), nullable=False, server_default='0'))
    op.add_column('order_items', sa.Column('ipi_value', sa.Numeric(12, 2), nullable=False, server_default='0'))

    op.add_column('orders', sa.Column('total_ipi', sa.Numeric(12, 2), nullable=False, server_default='0'))
    op.add_column('orders', sa.Column('total_with_ipi', sa.Numeric(12, 2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('orders', 'total_with_ipi')
    op.drop_column('orders', 'total_ipi')
    op.drop_column('order_items', 'ipi_value')
    op.drop_column('order_items', 'ipi_rate')
    op.drop_constraint('fk_product_types_group_id', 'product_types', type_='foreignkey')
    op.drop_column('product_types', 'group_id')
    op.drop_table('product_groups')
