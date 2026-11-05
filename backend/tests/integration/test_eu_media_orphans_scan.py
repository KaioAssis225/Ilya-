"""Varredura de referências a fotos EU no banco real (PostgreSQL 16).

Prova que `scan_photo_references` enxerga a foto citada em qualquer lugar:
colunas `photo_path` de produto e opcional, texto livre, JSON/JSONB (inclusive
com barra escapada), arrays e URLs assinadas -- e que NÃO confunde chave do
bucket brasileiro com chave EU. A varredura percorre o schema inteiro, então o
teste também garante que nenhuma coluna do schema real fica ilegível.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.media_orphans import scan_photo_references
from tests.factories.markets import require_market
from tests.factories.optionals import make_optional, make_optional_category
from tests.factories.products import make_product

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_varredura_encontra_referencias_em_qualquer_coluna(db_session: AsyncSession):
    ids = {name: str(uuid.uuid4()) for name in (
        "produto", "opcional", "texto", "jsonb", "json_escapado", "array", "url", "maiuscula", "br",
    )}
    await require_market(db_session, "EU", enabled=True)
    produto = await make_product(db_session, market_code="EU")
    produto.photo_path = f"object://eu-products/{ids['produto']}.webp"
    categoria = await make_optional_category(db_session, market_code="EU")
    opcional = await make_optional(db_session, categoria, color_name="Cor Teste", market_code="EU")
    opcional.photo_path = f"object://eu-optionals/{ids['opcional']}.png"
    await db_session.flush()

    await db_session.execute(text(
        "CREATE TABLE zz_scan_demo (id int, nota text, doc jsonb, bruto json, tags text[])"
    ))
    await db_session.execute(
        text(
            "INSERT INTO zz_scan_demo (id, nota, doc, bruto, tags) VALUES "
            "(1, :nota, CAST(:doc AS jsonb), CAST(:bruto AS json), CAST(:tags AS text[]))"
        ),
        {
            "nota": f"foto em eu-product-thumbnails/{ids['texto']}.webp.webp, fim.",
            "doc": f'{{"photo_path": "object://eu-products/{ids["jsonb"]}.jpg"}}',
            "bruto": f'{{"u": "eu-optional-variants\\/{ids["json_escapado"]}.png.v1-zoom.webp"}}',
            "tags": ["x", f"/api/v1/media/eu-optionals/{ids['array']}.png?expires=1"],
        },
    )
    await db_session.execute(
        text("INSERT INTO zz_scan_demo (id, nota) VALUES (2, :n), (3, :b)"),
        {
            "n": f"https://x/api/v1/media/eu-products%2F{ids['url']}.webp?sig=1",
            "b": f"object://products/{ids['br']}.webp EU-PRODUCTS/{ids['maiuscula'].upper()}",
        },
    )

    references = await scan_photo_references(db_session)

    assert references.errors == []
    assert references.columns_scanned > 50  # schema inteiro, não uma lista fixa
    for nome in ("produto", "opcional", "texto", "jsonb", "json_escapado", "array", "url"):
        assert ids[nome] in references.uuids, nome
    # citação em maiúsculas também protege (na dúvida, não apaga)...
    assert ids["maiuscula"] in references.uuids
    # ...mas chave do bucket BR não conta como referência a foto EU
    assert ids["br"] not in references.uuids
