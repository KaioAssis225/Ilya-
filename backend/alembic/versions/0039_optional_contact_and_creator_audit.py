"""make contact email optional and audit directory creators

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-04
"""

import sqlalchemy as sa
from alembic import op


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    oversized = bind.execute(
        sa.text(
            """
            SELECT 'clients' AS source, id, phone
            FROM clients
            WHERE length(phone) > 20
            UNION ALL
            SELECT 'representatives' AS source, id, phone
            FROM representatives
            WHERE length(phone) > 20
            LIMIT 1
            """
        )
    ).mappings().first()
    if oversized:
        raise RuntimeError(
            "Migração 0039 interrompida: telefone maior que 20 caracteres em "
            f"{oversized['source']} id={oversized['id']}."
        )

    op.alter_column(
        "clients",
        "phone",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "representatives",
        "phone",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "clients",
        "email",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "representatives",
        "email",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.add_column(
        "clients",
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "representatives",
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_clients_created_by_user_id_users",
        "clients",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_representatives_created_by_user_id_users",
        "representatives",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_clients_created_by_user_id",
        "clients",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_representatives_created_by_user_id",
        "representatives",
        ["created_by_user_id"],
    )

    op.execute(
        sa.text(
            "UPDATE representatives SET max_discount = 30.00"
        )
    )
    op.alter_column(
        "representatives",
        "max_discount",
        existing_type=sa.Numeric(precision=5, scale=2),
        server_default=sa.text("30.00"),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    missing_email = bind.execute(
        sa.text(
            """
            SELECT 'clients' AS source, id
            FROM clients
            WHERE email IS NULL
            UNION ALL
            SELECT 'representatives' AS source, id
            FROM representatives
            WHERE email IS NULL
            LIMIT 1
            """
        )
    ).mappings().first()
    if missing_email:
        raise RuntimeError(
            "Downgrade 0039 não é seguro: existe e-mail vazio em "
            f"{missing_email['source']} id={missing_email['id']}."
        )

    op.alter_column(
        "representatives",
        "max_discount",
        existing_type=sa.Numeric(precision=5, scale=2),
        server_default=sa.text("15.00"),
        existing_nullable=False,
    )
    op.drop_index(
        "ix_representatives_created_by_user_id",
        table_name="representatives",
    )
    op.drop_index("ix_clients_created_by_user_id", table_name="clients")
    op.drop_constraint(
        "fk_representatives_created_by_user_id_users",
        "representatives",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_clients_created_by_user_id_users",
        "clients",
        type_="foreignkey",
    )
    op.drop_column("representatives", "created_by_user_id")
    op.drop_column("clients", "created_by_user_id")
    op.alter_column(
        "representatives",
        "email",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "clients",
        "email",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "representatives",
        "phone",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "clients",
        "phone",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
