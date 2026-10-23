"""Idempotent, test-database-only fixtures for the browser journeys.

Run after migrations: python -m tests.e2e_support.seed_e2e
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.addresses import UF_SENTINEL
from app.core.security import hash_password
from app.models import (
    Catalog, Client, Market, PriceList, Product, ProductGroup, ProductMarket,
    ProductPrice, ProductType, User, UserMarket, UserRole,
)

DOMAIN = "ilya-test.example"
PRODUCTS = {"BR": ("E2E-BR-001", "Produto E2E BR"), "EU": ("E2E-EU-001", "Produto E2E EU")}


def database_url() -> str:
    raw = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError("TEST_DATABASE_URL (ou DATABASE_URL) é obrigatória para o seed E2E")
    url = make_url(raw)
    if url.drivername not in {"postgresql", "postgresql+asyncpg"} or not (url.database or "").endswith("_test"):
        raise RuntimeError("Seed E2E recusado: use exclusivamente um banco PostgreSQL com nome terminado em _test")
    return url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


async def one(db, statement):
    return (await db.execute(statement.execution_options(skip_market_scope=True))).scalar_one_or_none()


async def seed() -> None:
    password = os.environ.get("E2E_SEED_PASSWORD", "")
    if len(password) < 8:
        raise RuntimeError("Defina E2E_SEED_PASSWORD (mínimo 8 caracteres); não há senha padrão")
    engine = create_async_engine(database_url())
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as db:
            for code in ("BR", "EU"):
                market = await db.get(Market, code)
                if market is None:
                    raise RuntimeError(f"Mercado {code} ausente; execute alembic upgrade head antes do seed")
                market.is_enabled = True

            users: dict[str, User] = {}
            for role in ("admin", "executivo", "cadastros", "produtos", "cliente"):
                email = f"e2e-{role}@{DOMAIN}"
                user = await one(db, select(User).where(User.email == email))
                if user is None:
                    user = User(email=email, full_name=f"E2E {role.title()}", role=UserRole(role), home_market="BR")
                    db.add(user)
                user.hashed_password = hash_password(password)
                user.is_active = True
                user.must_change_password = False
                user.failed_login_attempts = 0
                user.locked_until = None
                await db.flush()
                users[role] = user

            clients: dict[str, Client] = {}
            for code in ("BR", "EU"):
                price_list = await one(db, select(PriceList).where(PriceList.market_code == code, PriceList.code == "lojista"))
                if price_list is None:
                    raise RuntimeError(f"Tabela lojista {code} ausente; execute as migrations")
                name = f"Cliente E2E {code}"
                client = await one(db, select(Client).where(Client.market_code == code, Client.email == f"e2e-client-{code.lower()}@{DOMAIN}"))
                if client is None:
                    client = Client(market_code=code, name=name, phone="11999999999", email=f"e2e-client-{code.lower()}@{DOMAIN}", cep="01310-100" if code == "BR" else "1234-567", address="Rua E2E, 1", city="São Paulo" if code == "BR" else "Lisboa", state="SP" if code == "BR" else UF_SENTINEL, country="BR" if code == "BR" else "PT", price_profile="lojista", price_list_id=price_list.id, max_discount=Decimal("0"))
                    db.add(client)
                client.name = name
                client.price_list_id = price_list.id
                await db.flush()
                clients[code] = client

                group = await one(db, select(ProductGroup).where(ProductGroup.market_code == code, ProductGroup.name == f"E2E Grupo {code}"))
                if group is None:
                    group = ProductGroup(market_code=code, name=f"E2E Grupo {code}", ipi=Decimal("0"))
                    db.add(group)
                    await db.flush()
                type_name = f"E2E Tipo {code}"
                product_type = await one(db, select(ProductType).where(ProductType.market_code == code, ProductType.name == type_name))
                if product_type is None:
                    product_type = ProductType(market_code=code, name=type_name, group_id=group.id)
                    db.add(product_type)
                # products.catalog_id é obrigatório desde catalog_permissions_r21 e a FK
                # composta exige catálogo do mesmo mercado do produto.
                catalog_name = f"E2E Catálogo {code}"
                catalog = await one(db, select(Catalog).where(Catalog.market_code == code, Catalog.name == catalog_name))
                if catalog is None:
                    catalog = Catalog(market_code=code, name=catalog_name)
                    db.add(catalog)
                    await db.flush()
                sku, description = PRODUCTS[code]
                product = await one(db, select(Product).where(Product.market_code == code, Product.product_code == sku))
                if product is None:
                    product = Product(market_code=code, catalog_id=catalog.id, product_code=sku, description=description, type=type_name, altura=Decimal("10"), largura=Decimal("10"), profundidade=Decimal("10"), price=Decimal("100"), price_lojista=Decimal("100"), price_corporativo=Decimal("100"), custo_desativado=Decimal("0"))
                    db.add(product)
                    await db.flush()
                product.is_active = True
                product.catalog_id = catalog.id
                product.description = description
                product.type = type_name
                listing = await db.get(ProductMarket, (product.id, code))
                if listing is None:
                    listing = ProductMarket(product_id=product.id, market_code=code)
                    db.add(listing)
                listing.is_available = True
                if code == "EU":
                    listing.description_pt_pt = description
                    listing.description_en = "E2E product EU"
                    listing.vat_rate = Decimal("23")
                    listing.vat_status = "approved"
                    listing.approved_by_user_id = users["admin"].id
                    listing.approved_at = datetime.now(timezone.utc)
                profiles = ("lojista", "corporativo", "pvp", "arquiteto") if code == "EU" else ("lojista",)
                for profile in profiles:
                    profile_list = price_list if profile == "lojista" else await one(
                        db, select(PriceList).where(PriceList.market_code == code, PriceList.code == profile)
                    )
                    if profile_list is None:
                        raise RuntimeError(f"Tabela {profile} {code} ausente; execute as migrations")
                    price = await db.get(ProductPrice, (product.id, profile_list.id))
                    if price is None:
                        price = ProductPrice(product_id=product.id, price_list_id=profile_list.id, amount=Decimal("100"))
                        db.add(price)
                    else:
                        price.amount = Decimal("100")

            for role, user in users.items():
                for code in (("BR", "EU") if role == "admin" else ("BR",)):
                    link = await db.get(UserMarket, (user.id, code))
                    if link is None:
                        link = UserMarket(user_id=user.id, market_code=code)
                        db.add(link)
                    link.role = role
                    link.status = "active"
                    link.linked_client_id = clients["BR"].id if role == "cliente" else None
                    link.rep_id = None
                    link.can_view_dashboard = role in {"admin", "executivo"}
                    link.can_approve_tax = role == "admin"
        print("Seed E2E aplicado em BR/EU; usuários, clientes e SKUs sintéticos prontos")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
