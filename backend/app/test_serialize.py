import asyncio
import json
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.product import Product
from app.api.routers.products import _to_read

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product).limit(5))
        products = result.scalars().all()
        for p in products:
            read_model = _to_read(p)
            # Serialize to json
            js = read_model.model_dump_json()
            print(f"Serialized product {p.product_code}: {js}")

if __name__ == "__main__":
    asyncio.run(main())
