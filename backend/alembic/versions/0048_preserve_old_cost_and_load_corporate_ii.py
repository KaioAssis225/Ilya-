"""preserva custo anterior e carrega tabela Corporativo II

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-10

O antigo ``price_corporativo`` é renomeado para ``custo_desativado`` e fica
restrito ao modelo interno. Um novo ``price_corporativo`` recebe a tabela
Corporativo II aprovada. A coluna histórica não integra schemas, APIs ou CSVs.
"""
from alembic import op
import sqlalchemy as sa
from decimal import Decimal


revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


CORPORATE_II_PRICES = {
    "IML0001": "895.00", "IML0002": "895.00", "IML0005": "895.00",
    "IMJ0001": "2039.00", "IMJ0092": "2039.00", "IMJ0002": "2039.00",
    "IMJ0003": "2290.00", "IMJ0004": "2290.00", "IMJ0005": "3162.00",
    "IMJ0094": "3162.00", "IMJ0006": "3162.00", "ICD0106": "1596.00",
    "ICD0107": "1596.00", "IMJ0191": "7930.00", "IMJ0192": "7930.00",
    "IMJ0177": "1679.00", "IMJ0178": "1835.00", "IMJ0179": "2142.00",
    "IMJ0187": "5128.00", "IMJ0097": "5128.00", "IMJ0160": "5128.00",
    "ICS0009": "22066.00", "ICD0108": "1052.00", "ICD0109": "948.00",
    "IMJ0193": "4512.00", "ICD0111": "1781.00", "IES0075": "4904.00",
    "ICC0002": "5375.00", "ICS0010": "24716.00", "IES0023": "2396.00",
    "IES0024": "2396.00", "ICD0112": "1450.00", "ICD0113": "1450.00",
    "IMJ0194": "13974.00", "CD0160": "1744.00", "CD0161": "1744.00",
    "CD0162": "1744.00", "ICD0114": "2296.00", "ICD0115": "2603.00",
    "ISF0101": "8085.00", "ISF0102": "8085.00", "IPL0093": "4082.00",
    "IPL0094": "4082.00", "IES0060": "2621.00", "IES0057": "2621.00",
    "IES0077": "3972.00", "IES0078": "3972.00", "IES0079": "3133.00",
    "IES0080": "3133.00", "IES0081": "4484.00", "IES0082": "4484.00",
    "ICS0011": "14734.00", "ICD0001": "1460.00", "ICD0002": "1460.00",
    "ICD0003": "1460.00", "IMJ0108": "1320.00", "IMJ0173": "1320.00",
    "IMJ0035": "1320.00", "ICS0012": "24001.00", "IBQ0016": "1860.00",
    "IBQ0017": "1860.00", "ICD0120": "1454.00", "ICD0121": "1454.00",
    "IMJ0195": "12709.00", "IMJ0196": "12709.00", "IMJ0007": "3556.00",
    "IMJ0008": "3556.00", "IMJ0009": "5128.00", "IMJ0010": "5128.00",
    "ICD0004": "974.00", "ICD0005": "974.00", "ICD0006": "974.00",
    "ICD0122": "1596.00", "ICD0123": "1596.00", "IMJ0198": "5851.00",
    "IES0001": "1929.00", "IES0002": "1929.00", "IES0003": "1929.00",
    "IES0004": "1929.00", "IES0034": "1929.00", "ICD0007": "836.00",
    "ICD0008": "836.00", "ICD0070": "836.00", "ICD0009": "836.00",
    "ICD0066": "836.00", "ICS0001": "13326.00", "ICS0002": "13326.00",
    "ICD0102": "1218.00", "IPL0098": "12727.00", "IPL0099": "12727.00",
    "ISF0109": "26651.00", "ISF0110": "26651.00", "ICC0003": "10855.00",
    "ICL0001": "76021.00", "ICD0110": "7094.00", "IPL0100": "12240.00",
    "IBQ0014": "2396.00", "IBQ0015": "2396.00", "ICD0116": "1909.00",
    "ICD0117": "1909.00", "ICD0118": "2097.00", "ICD0119": "2097.00",
    "IPL0101": "13363.00", "IPF0011": "7394.00", "IES0076": "7618.00",
    "IMJ0197": "25565.00", "IMC0047": "7282.00", "IPL0102": "12859.00",
    "ISF0108": "28073.00", "ICD0124": "4193.00", "IMJ0199": "18790.00",
    "IPL0103": "7150.00", "ICD0105": "3487.00", "ICD0125": "3767.00",
    "IPL0097": "6866.00", "IPL0105": "7270.00", "ISF0107": "12285.00",
    "ISF0111": "13030.00", "IPL0104": "5373.00", "IAC0136": "824.00",
    "IAC0135": "824.00", "IAC0134": "824.00", "IAC0137": "1423.00",
    "IAC0138": "1423.00", "IAC0146": "4642.00", "IAC0145": "4642.00",
    "IAC0141": "1255.00", "IAC0142": "1255.00", "IAC0143": "1311.00",
    "IAC0144": "1311.00", "IAC0120": "1872.00", "IAC0121": "1872.00",
    "IAC0122": "1722.00", "IAC0123": "2321.00", "IAC0140": "974.00",
    "IAC0139": "974.00", "IAC0124": "6176.00", "IAC0125": "6176.00",
    "IAC0126": "2209.00", "IAC0127": "2471.00", "IAC0128": "6925.00",
    "IAC0129": "6925.00", "IAC0130": "3856.00", "IAC0131": "2995.00",
    "IAC0147": "1405.00",
}


def upgrade() -> None:
    op.drop_index("ix_products_price_corporativo_id", table_name="products")
    op.alter_column(
        "products", "price_corporativo", new_column_name="custo_desativado"
    )
    op.add_column(
        "products",
        sa.Column(
            "price_corporativo",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_products_price_corporativo_id",
        "products",
        ["price_corporativo", "id"],
    )

    products = sa.table(
        "products",
        sa.column("product_code", sa.String()),
        sa.column("price_corporativo", sa.Numeric(10, 2)),
    )
    connection = op.get_bind()
    for product_code, price in CORPORATE_II_PRICES.items():
        connection.execute(
            products.update()
            .where(products.c.product_code == product_code)
            .values(price_corporativo=Decimal(price))
        )


def downgrade() -> None:
    op.drop_index("ix_products_price_corporativo_id", table_name="products")
    op.drop_column("products", "price_corporativo")
    op.alter_column(
        "products", "custo_desativado", new_column_name="price_corporativo"
    )
    op.create_index(
        "ix_products_price_corporativo_id",
        "products",
        ["price_corporativo", "id"],
    )
