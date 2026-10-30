"""Subgrupos EU com terminologia brasileira e mesas por finalidade.

O catálogo europeu passa a distinguir mesas de jantar, centro, lateral e
bistrô, além de banqueta alta e baixa. O Brasil e os snapshots de itens de
pedidos não são alterados.

Revision ID: eu_subgroups_br_r33
Revises: eu_product_names_pt_r32
Create Date: 2026-10-30
"""
from __future__ import annotations

import re
import unicodedata
import uuid

import sqlalchemy as sa
from alembic import op


revision = "eu_subgroups_br_r33"
down_revision = "eu_product_names_pt_r32"
branch_labels = None
depends_on = None


_NEW_TYPE_IDS = {
    "MESA DE CENTRO": uuid.UUID("96d82f2a-fc2e-50ad-9a10-93dfcc4dbd6f"),
    "MESA LATERAL": uuid.UUID("47709f40-0ef7-5ec5-91a0-41f4519bc1cc"),
    "MESA BISTRÔ": uuid.UUID("1bca106f-87c9-5a9e-bb71-087784b4b89e"),
    "BANQUETA BAIXA": uuid.UUID("6c85e291-e597-52a2-85c1-04741eb5f742"),
}

# Estes nove SKUs eram os únicos produtos de mesa cadastrados como CERÂMICA
# antes desta migration. A lista torna o downgrade fiel ao estado anterior.
_CERAMIC_TABLE_CODES = (
    "MA0033", "MA0034", "MC0373", "MC0374", "MC0375",
    "ML0249", "ML0250", "ML0251", "ML0252",
)


def _search_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).upper().split())


def classify_eu_table_subgroup(
    product_code: str,
    description: str,
    current_type: str = "MESA",
) -> str | None:
    """Classificação documentada usada para proteger os dados da migration."""
    code = (product_code or "").strip().upper()
    name = _search_key(description)
    type_key = _search_key(current_type)
    if type_key not in {"MESA", "CERAMICA"}:
        return None
    if type_key == "CERAMICA" and "MESA" not in name:
        return None
    if "MESA DE JANTAR" in name or "MESA JANTAR" in name or re.match(r"^I?MJ", code):
        return "MESA DE JANTAR"
    if "MESA BISTR" in name or code.startswith("MB"):
        return "MESA BISTRÔ"
    if "MESA DE CENTRO" in name or "MESA CENTRO" in name or code.startswith("MC"):
        return "MESA DE CENTRO"
    if "MESA LATERAL" in name or code.startswith(("ML", "MA")):
        return "MESA LATERAL"
    return None


def classify_eu_stool_subgroup(description: str) -> str | None:
    name = _search_key(description)
    if "ALTA BANQUETA" in name or "BANQUETA ALTA" in name:
        return "BANQUETA ALTA"
    if "BAIXA BANQUETA" in name or "BANQUETA BAIXA" in name:
        return "BANQUETA BAIXA"
    return None


_LOCALIZED_NAME_SQL = "COALESCE(NULLIF(BTRIM(pm.description_pt_pt), ''), p.description)"
_TABLE_KIND_SQL = f"""
CASE
  WHEN UPPER({_LOCALIZED_NAME_SQL}) LIKE '%MESA DE JANTAR%'
    OR UPPER({_LOCALIZED_NAME_SQL}) LIKE '%MESA JANTAR%'
    OR p.product_code ~ '^(I?MJ)' THEN 'MESA DE JANTAR'
  WHEN UPPER({_LOCALIZED_NAME_SQL}) LIKE '%MESA BISTR%'
    OR p.product_code ~ '^MB' THEN 'MESA BISTRÔ'
  WHEN UPPER({_LOCALIZED_NAME_SQL}) LIKE '%MESA DE CENTRO%'
    OR UPPER({_LOCALIZED_NAME_SQL}) LIKE '%MESA CENTRO%'
    OR p.product_code ~ '^MC' THEN 'MESA DE CENTRO'
  WHEN UPPER({_LOCALIZED_NAME_SQL}) LIKE '%MESA LATERAL%'
    OR p.product_code ~ '^ML'
    OR p.product_code ~ '^MA' THEN 'MESA LATERAL'
END
"""
_TABLE_CANDIDATE_SQL = f"""
p.market_code = 'EU'
AND (
  UPPER(BTRIM(p.type)) = 'MESA'
  OR (
    UPPER(BTRIM(p.type)) = 'CERÂMICA'
    AND UPPER({_LOCALIZED_NAME_SQL}) LIKE '%MESA%'
  )
)
"""


def _insert_type(bind, *, type_id: uuid.UUID, name: str, group_id: uuid.UUID | None) -> None:
    bind.execute(
        sa.text("""
            INSERT INTO product_types (id, market_code, name, group_id)
            VALUES (:id, 'EU', :name, :group_id)
        """),
        {"id": type_id, "name": name, "group_id": group_id},
    )


def upgrade() -> None:
    bind = op.get_bind()

    table_candidate_count = bind.execute(sa.text(f"""
        SELECT count(*)
        FROM products p
        JOIN product_markets pm
          ON pm.product_id = p.id AND pm.market_code = 'EU'
        WHERE {_TABLE_CANDIDATE_SQL}
    """)).scalar_one()
    ambiguous_tables = bind.execute(sa.text(f"""
        SELECT p.product_code
        FROM products p
        JOIN product_markets pm
          ON pm.product_id = p.id AND pm.market_code = 'EU'
        WHERE {_TABLE_CANDIDATE_SQL}
          AND ({_TABLE_KIND_SQL}) IS NULL
        ORDER BY p.product_code
    """)).scalars().all()
    if ambiguous_tables:
        raise RuntimeError(
            "Mesas EU sem classificação segura: " + ", ".join(ambiguous_tables)
        )

    stool_candidate_count = bind.execute(sa.text("""
        SELECT count(*) FROM products
        WHERE market_code = 'EU' AND UPPER(BTRIM(type)) = 'BANQUETA'
    """)).scalar_one()
    ambiguous_stools = bind.execute(sa.text(f"""
        SELECT p.product_code
        FROM products p
        JOIN product_markets pm
          ON pm.product_id = p.id AND pm.market_code = 'EU'
        WHERE p.market_code = 'EU'
          AND UPPER(BTRIM(p.type)) = 'BANQUETA'
          AND UPPER({_LOCALIZED_NAME_SQL}) NOT LIKE '%ALTA BANQUETA%'
          AND UPPER({_LOCALIZED_NAME_SQL}) NOT LIKE '%BANQUETA ALTA%'
          AND UPPER({_LOCALIZED_NAME_SQL}) NOT LIKE '%BAIXA BANQUETA%'
          AND UPPER({_LOCALIZED_NAME_SQL}) NOT LIKE '%BANQUETA BAIXA%'
        ORDER BY p.product_code
    """)).scalars().all()
    if ambiguous_stools:
        raise RuntimeError(
            "Banquetas EU sem classificação segura: " + ", ".join(ambiguous_stools)
        )

    table_type_row = bind.execute(sa.text("""
        UPDATE product_types
        SET name = 'MESA DE JANTAR'
        WHERE market_code = 'EU' AND UPPER(BTRIM(name)) = 'MESA'
        RETURNING group_id
    """)).first()
    if table_type_row is None and table_candidate_count:
        raise RuntimeError("Produtos de mesa EU existem sem o subgrupo MESA cadastrado.")
    if table_type_row is not None:
        table_group_id = table_type_row[0]
        for name in ("MESA DE CENTRO", "MESA LATERAL", "MESA BISTRÔ"):
            _insert_type(bind, type_id=_NEW_TYPE_IDS[name], name=name, group_id=table_group_id)

    stool_type_row = bind.execute(sa.text("""
        UPDATE product_types
        SET name = 'BANQUETA ALTA'
        WHERE market_code = 'EU' AND UPPER(BTRIM(name)) = 'BANQUETA'
        RETURNING group_id
    """)).first()
    if stool_type_row is None and stool_candidate_count:
        raise RuntimeError("Produtos de banqueta EU existem sem o subgrupo BANQUETA cadastrado.")
    if stool_type_row is not None:
        _insert_type(
            bind,
            type_id=_NEW_TYPE_IDS["BANQUETA BAIXA"],
            name="BANQUETA BAIXA",
            group_id=stool_type_row[0],
        )

    bind.execute(sa.text(f"""
        UPDATE products p
        SET type = ({_TABLE_KIND_SQL}),
            updated_at = now(),
            source_version = p.source_version + 1
        FROM product_markets pm
        WHERE pm.product_id = p.id
          AND pm.market_code = 'EU'
          AND {_TABLE_CANDIDATE_SQL}
    """))
    bind.execute(sa.text(f"""
        UPDATE products p
        SET type = CASE
          WHEN UPPER({_LOCALIZED_NAME_SQL}) LIKE '%ALTA BANQUETA%'
            OR UPPER({_LOCALIZED_NAME_SQL}) LIKE '%BANQUETA ALTA%' THEN 'BANQUETA ALTA'
          WHEN UPPER({_LOCALIZED_NAME_SQL}) LIKE '%BAIXA BANQUETA%'
            OR UPPER({_LOCALIZED_NAME_SQL}) LIKE '%BANQUETA BAIXA%' THEN 'BANQUETA BAIXA'
        END,
        updated_at = now(),
        source_version = p.source_version + 1
        FROM product_markets pm
        WHERE pm.product_id = p.id
          AND pm.market_code = 'EU'
          AND p.market_code = 'EU'
          AND UPPER(BTRIM(p.type)) = 'BANQUETA'
    """))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("""
            UPDATE products
            SET type = CASE
              WHEN product_code = ANY(CAST(:ceramic_codes AS text[])) THEN 'CERÂMICA'
              ELSE 'MESA'
            END,
            updated_at = now(),
            source_version = source_version + 1
            WHERE market_code = 'EU'
              AND type IN ('MESA DE JANTAR', 'MESA DE CENTRO', 'MESA LATERAL', 'MESA BISTRÔ')
        """),
        {"ceramic_codes": list(_CERAMIC_TABLE_CODES)},
    )
    bind.execute(sa.text("""
        UPDATE products
        SET type = 'BANQUETA',
            updated_at = now(),
            source_version = source_version + 1
        WHERE market_code = 'EU' AND type IN ('BANQUETA ALTA', 'BANQUETA BAIXA')
    """))
    bind.execute(sa.text("""
        DELETE FROM product_types
        WHERE market_code = 'EU'
          AND name IN ('MESA DE CENTRO', 'MESA LATERAL', 'MESA BISTRÔ', 'BANQUETA BAIXA')
    """))
    bind.execute(sa.text("""
        UPDATE product_types SET name = 'MESA'
        WHERE market_code = 'EU' AND name = 'MESA DE JANTAR'
    """))
    bind.execute(sa.text("""
        UPDATE product_types SET name = 'BANQUETA'
        WHERE market_code = 'EU' AND name = 'BANQUETA ALTA'
    """))
