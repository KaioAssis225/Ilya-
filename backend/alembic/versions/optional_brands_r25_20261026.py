"""Separate ILYA/IBTW finishes using the approved Portugal list of 26/10/2026.

Brand is independent from market, category, photos and product associations.
The reference is frozen here: future creations explicitly choose their brand.
"""
import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "optional_brands_r25"
down_revision = "order_multi_catalog_r24"
branch_labels = None
depends_on = None

FABRICS = {
    "BAETA": "TOPAZIO|ARGILA|SISAL",
    "LONA": "COBALTO",
    "PANAMA": "DESERTO|NEVOA|TOPAZIO|SISAL|JADE|INDIGO|SISAL/INDIGO|SISAL/JADE|SISAL/ARGILA|BAUNILHA/NEVOA",
    "SARJA": "MARFIN|COBALTO|AVELA|MENTA|LAZULI",
    "UNIQUE": "DESERTO|MUSGO|MARFIM|SISAL|COBALTO|DESERTO/SISAL|SISAL/ARGILA",
    "BOUCLE": "PLATINA|DESERTO|TOPAZIO|SISAL|JADE|INDIGO",
    "JACQUARD TEXTURA": "CRU|AREIA/CRU",
    "RATIER RAMI": "AMENDOA|NEVOA",
    "TWEED": "CRU|CIDREIRA/AREIA|CANELA/TERRACOTA|NEBLINA/CROMO",
    "WAVES": "MARFIN|MENTA|COBALTO|AVELA",
    "TARTAN": "CIDREIRA/ARGILA",
}
LEATHER = "BRANCO FOSCO|CHUMBO|CARAMELO|CINZA|CIDREIRA"
REFERENCE = {
    "TECIDOS_IBTW": {f"{family} {name}" for family, names in FABRICS.items() for name in names.split("|")}
        | {f"COURO PELE {name}" for name in LEATHER.split("|")},
    "couro_soleta": set(LEATHER.split("|")),
    "CORDA_BOUCLE": set("CANELA|OPALA|CRU|CRIDREIRA|NEBLINA|CROMO|TAUPE".split("|")),
    "TELA_IBTW": set("KHAKI FECHADO|TAUPE UNIQUE|GRAFITE UNIQUE|AREIA MESCLA|TERRACOTA".split("|")),
    "ALUMINIO_IBTW": set("PRETO|CHUMBO|GRAFITE|AZUL MARINHO|TERRACOTA|TAUPE|AREIA|CAMOMILA|ERVA DOCE|CIDREIRA|CANELA|MARROM".split("|")),
    "TRICOT": set("PEROLA|AREIA|TAUPE|CANELA|CIDREIRA|SAFIRA|QUARTO|CINZA|MENTA".split("|")),
    "MARMORE": set("CALACATA|DONATELLO|NEGRONI|KILIMANJARO|VITORIA REGIA".split("|")),
    "PEDRA_COMPOSTA": set("PIPA|JUQUEHY|ILHA".split("|")),
    "TEKA": set("NATURAL OLEO|PATINA OLEO|TAUPE OLEO|CARVAO OLEO".split("|")),
    # Confirmed: keep Iroko Carvão/Pátina as ILYA, without renaming them to Teka.
    "MADEIRA": {"IROKO NATURAL OLEO", "IROKO TAUPE OLEO"},
    "TAPETE": set("PEROLA|AREIA|TAUPE|CANELA|CIDREIRA|SAFIRA|CINZA".split("|")),
    "URDUME": set("PEROLA|AREIA|TAUPE".split("|")),
    "PEDRA_SINTERIZADA": set("CORTEN|CARVAO|PEROLA|CONCRETO".split("|")),
    "CERAMICA_ARTESANAL": set("AREIA|AREIA FERRUGEM|AREIA MESCLA|AREIA OCEANO|AZUL ROYAL|BAUNILHA|CAMURCA|CANELA|ESMERALDA|JADE|PRETO|RECIFE|RECIFE BROWN|SAFIRA|VULCAN|VULCAN BLACK".split("|")),
    "FIBRA_DE_VIDRO": set("CHUMBO|TERRACOTA|TAUPE|AREIA|CAMOMILA|CIDREIRA".split("|")),
}


def normalize(value):
    text = "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))
    return re.sub(r"\s*/\s*", "/", " ".join(text.upper().split()))


def is_ibtw(category, name):
    return normalize(name) in REFERENCE.get(category, set())


def upgrade():
    op.add_column("optionals", sa.Column("brand", sa.String(4), nullable=False, server_default="ILYA"))
    op.create_check_constraint("ck_optionals_brand", "optionals", "brand IN ('ILYA', 'IBTW')")
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, category, color_name FROM optionals WHERE market_code = 'EU'"
    )).mappings().all()
    for row in rows:
        name = row["color_name"]
        # The user confirmed this correction; IDs, photos and associations stay.
        if row["category"] == "CERAMICA_ARTESANAL" and normalize(name) == "AMARELO MESCLA":
            name = "AREIA MESCLA"
        connection.execute(sa.text(
            "UPDATE optionals SET brand = :brand, color_name = :name WHERE id = :id"
        ), {"id": row["id"], "name": name, "brand": "IBTW" if is_ibtw(row["category"], name) else "ILYA"})


def downgrade():
    # Keep the approved name correction; never guess which later names to undo.
    op.drop_constraint("ck_optionals_brand", "optionals", type_="check")
    op.drop_column("optionals", "brand")
