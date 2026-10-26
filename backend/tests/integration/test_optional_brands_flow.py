"""Brand persistence, market isolation and the migration against real PostgreSQL."""
import importlib.util
from pathlib import Path
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core.security import create_access_token
from tests.factories import make_optional_category, make_user, make_user_market

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_create_change_brand_and_preserve_market_photo_and_identity(client, db_session):
    user = await make_user(db_session)
    await make_user_market(db_session, user, market_code="EU", role="admin")
    category = await make_optional_category(db_session, market_code="EU")
    foreign = await make_optional_category(db_session, market_code="BR")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, 'admin', user.auth_version, 'EU')}"}
    created = await client.post("/api/v1/optionals", headers=headers, json={
        "category": category.code, "color_name": "Cor sintética", "brand": "IBTW",
    })
    assert created.status_code == 201, created.text
    before = created.json()
    assert before["brand"] == "IBTW" and before["market_code"] == "EU"
    updated = await client.patch(f"/api/v1/optionals/{before['id']}", headers=headers, json={"brand": "ILYA"})
    assert updated.status_code == 200, updated.text
    after = updated.json()
    assert after["brand"] == "ILYA"
    assert all(after[field] == before[field] for field in ("id", "category", "color_name", "photo_url", "market_code"))
    invalid = await client.patch(f"/api/v1/optionals/{before['id']}", headers=headers, json={"brand": None})
    assert invalid.status_code == 422
    rejected = await client.post("/api/v1/optionals", headers=headers, json={
        "category": foreign.code, "color_name": "Estrangeira", "brand": "IBTW",
    })
    assert rejected.status_code == 422
    imported = await client.post("/api/v1/import/optionals", headers=headers, files={
        "file": ("brands.csv", f"category,color_name,brand\n{category.code},Cor CSV,IBTW\n".encode(), "text/csv"),
    })
    assert imported.status_code == 200, imported.text
    listed = await client.get("/api/v1/optionals", headers=headers)
    assert next(row for row in listed.json() if row["color_name"] == "Cor CSV")["brand"] == "IBTW"


async def test_migration_keeps_photos_ids_links_and_brazil(db_session, monkeypatch):
    spec = importlib.util.spec_from_file_location("brands_probe", Path(__file__).parents[2] / "alembic/versions/optional_brands_r25_20261026.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = f"brand_probe_{uuid.uuid4().hex}"

    def probe(connection):
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
        connection.execute(sa.text("CREATE TABLE optionals (id uuid PRIMARY KEY, market_code text, category text, color_name text, photo_path text)"))
        connection.execute(sa.text("CREATE TABLE links (optional_id uuid REFERENCES optionals(id))"))
        fixtures = [
            ("EU", "PEDRA_SINTERIZADA", "CARVÃO"),
            ("EU", "MADEIRA", "IROKO CARVÃO ÓLEO"),
            ("EU", "CERAMICA_ARTESANAL", "AMARELO MESCLA"),
            ("BR", "PEDRA_SINTERIZADA", "CARVÃO"),
        ]
        for market, category, name in fixtures:
            optional_id = uuid.uuid4()
            connection.execute(sa.text("INSERT INTO optionals VALUES (:id, :market, :category, :name, :photo)"),
                               {"id": optional_id, "market": market, "category": category, "name": name, "photo": f"photo/{optional_id}.webp"})
            connection.execute(sa.text("INSERT INTO links VALUES (:id)"), {"id": optional_id})
        before = connection.execute(sa.text("SELECT * FROM optionals ORDER BY id")).mappings().all()
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        after = connection.execute(sa.text("SELECT * FROM optionals ORDER BY id")).mappings().all()
        assert len(before) == len(after) == 4
        for old, new in zip(before, after):
            assert all(new[field] == old[field] for field in ("id", "market_code", "category", "photo_path"))
        assert [row["brand"] for row in after if row["market_code"] == "BR"] == ["ILYA"]
        assert next(row for row in after if row["market_code"] == "EU" and row["category"] == "PEDRA_SINTERIZADA")["brand"] == "IBTW"
        assert next(row for row in after if row["category"] == "MADEIRA")["brand"] == "ILYA"
        ceramic = next(row for row in after if row["category"] == "CERAMICA_ARTESANAL")
        assert ceramic["brand"] == "IBTW" and ceramic["color_name"] == "AREIA MESCLA"
        assert connection.execute(sa.text("SELECT count(*) FROM links JOIN optionals ON links.optional_id = optionals.id")).scalar_one() == 4
        migration.downgrade()
        assert "brand" not in connection.execute(sa.text("SELECT * FROM optionals LIMIT 1")).keys()

    connection = await db_session.connection()
    await connection.run_sync(probe)
