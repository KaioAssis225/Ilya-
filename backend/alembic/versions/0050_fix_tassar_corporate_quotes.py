"""corrige perfil e orçamentos corporativos de Tassar Neto

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-12

O cliente foi cadastrado como lojista apesar de operar pela tabela corporativa.
Esta correção atualiza o perfil e recalcula os snapshots de preço dos dois
orçamentos já emitidos, preservando quantidade, desconto e IPI originais.
"""
from alembic import op
import sqlalchemy as sa


revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

_CLIENT_ID = "3ab2a653-1b4c-45d5-a71e-eb61c9a0b3fd"
_HISTORY_IDS = {
    "ORC-0002": "00500000-0000-0000-0000-000000000002",
    "ORC-0003": "00500000-0000-0000-0000-000000000003",
}

_CORPORATE_ITEMS = {
    ("ORC-0002", "ICS0009"): ("22066.00", "5737.16"),
    ("ORC-0003", "ISF0101"): ("8085.00", "2102.10"),
    ("ORC-0003", "IPL0093"): ("4082.00", "2122.64"),
}

_CORPORATE_TOTALS = {
    "ORC-0002": ("176528.00", "5737.16", "182265.16"),
    "ORC-0003": ("129992.00", "4224.74", "134216.74"),
}

_LOJISTA_ITEMS = {
    ("ORC-0002", "ICS0009"): ("11201.00", "2912.26"),
    ("ORC-0003", "ISF0101"): ("4104.00", "1067.04"),
    ("ORC-0003", "IPL0093"): ("2072.00", "1077.44"),
}

_LOJISTA_TOTALS = {
    "ORC-0002": ("89608.00", "2912.26", "92520.26"),
    "ORC-0003": ("65984.00", "2144.48", "68128.48"),
}


def _apply(profile: str, items: dict, totals: dict) -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE clients
               SET price_profile = :profile,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = CAST(:client_id AS uuid)
               AND lower(name) = lower('Tassar Neto')
            """
        ),
        {"profile": profile, "client_id": _CLIENT_ID},
    )

    for (orc_id, product_code), (unit_price, ipi_value) in items.items():
        bind.execute(
            sa.text(
                """
                UPDATE order_items AS item
                   SET unit_price = :unit_price,
                       ipi_value = :ipi_value,
                       updated_at = CURRENT_TIMESTAMP
                  FROM orders AS current_order
                 WHERE item.order_id = current_order.id
                   AND current_order.client_id = CAST(:client_id AS uuid)
                   AND current_order.orc_id = :orc_id
                   AND item.product_code = :product_code
                """
            ),
            {
                "client_id": _CLIENT_ID,
                "orc_id": orc_id,
                "product_code": product_code,
                "unit_price": unit_price,
                "ipi_value": ipi_value,
            },
        )

    for orc_id, (total_value, total_ipi, total_with_ipi) in totals.items():
        bind.execute(
            sa.text(
                """
                UPDATE orders
                   SET total_value = :total_value,
                       total_ipi = :total_ipi,
                       total_with_ipi = :total_with_ipi,
                       source_version = source_version + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE client_id = CAST(:client_id AS uuid)
                   AND orc_id = :orc_id
                """
            ),
            {
                "client_id": _CLIENT_ID,
                "orc_id": orc_id,
                "total_value": total_value,
                "total_ipi": total_ipi,
                "total_with_ipi": total_with_ipi,
            },
        )


def upgrade() -> None:
    _apply("corporativo", _CORPORATE_ITEMS, _CORPORATE_TOTALS)
    bind = op.get_bind()
    for orc_id, history_id in _HISTORY_IDS.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO order_history
                    (id, order_id, user_id, action, details, created_at, updated_at)
                SELECT CAST(:history_id AS uuid), id, NULL,
                       'price_profile_corrected',
                       'Perfil corrigido de lojista para corporativo; valores recalculados pela tabela corporativa.',
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                  FROM orders
                 WHERE client_id = CAST(:client_id AS uuid)
                   AND orc_id = :orc_id
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "history_id": history_id,
                "client_id": _CLIENT_ID,
                "orc_id": orc_id,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM order_history
             WHERE id IN (CAST(:id_2 AS uuid), CAST(:id_3 AS uuid))
            """
        ),
        {
            "id_2": _HISTORY_IDS["ORC-0002"],
            "id_3": _HISTORY_IDS["ORC-0003"],
        },
    )
    _apply("lojista", _LOJISTA_ITEMS, _LOJISTA_TOTALS)
