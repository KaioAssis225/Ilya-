import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.product import Product

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product).limit(10))
        products = result.scalars().all()
        print(f"Lidos {len(products)} produtos do banco:")
        for p in products:
            print(f"SKU: {p.product_code} | Desc: {p.description} | Lojista: {p.price_lojista} | Corporativo: {p.price_corporativo} | Price: {p.price}")

if __name__ == "__main__":
    asyncio.run(main())
