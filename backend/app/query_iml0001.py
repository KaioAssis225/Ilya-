import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.product import Product

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product).where(Product.product_code.in_(['IML0001', 'IML0002', 'IML0005'])))
        products = result.scalars().all()
        print(f"Lidos {len(products)} produtos:")
        for p in products:
            print(f"SKU: {p.product_code} | Lojista: {p.price_lojista} | Corp: {p.price_corporativo} | Price: {p.price}")

if __name__ == "__main__":
    asyncio.run(main())
