"""
Seed script — popula o banco com 20 produtos iniciais.
Executar da pasta backend/:
    python -m asyncio seed.py
ou:
    python seed.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import AsyncSessionLocal
from app.models.product import Product


PRODUCTS = [
    {
        "product_code": "PRD-001",
        "description": "Sofá 2 Lugares Retrátil e Reclinável",
        "altura": 95.00,
        "largura": 160.00,
        "profundidade": 90.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Camomila",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-002",
        "description": "Sofá 3 Lugares Retrátil e Reclinável",
        "altura": 95.00,
        "largura": 220.00,
        "profundidade": 90.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Canela",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-003",
        "description": "Poltrona Reclinável Individual",
        "altura": 100.00,
        "largura": 85.00,
        "profundidade": 88.00,
        "opt_aluminio": "Escovado",
        "opt_tecido": "Areia",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-004",
        "description": "Chaise Longue Estofada",
        "altura": 80.00,
        "largura": 180.00,
        "profundidade": 70.00,
        "opt_aluminio": "Preto",
        "opt_tecido": "Taupe",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-005",
        "description": "Cadeira de Jantar Estofada",
        "altura": 92.00,
        "largura": 45.00,
        "profundidade": 50.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Camomila",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-006",
        "description": "Banco Estofado com Base em Alumínio",
        "altura": 48.00,
        "largura": 120.00,
        "profundidade": 40.00,
        "opt_aluminio": "Escovado",
        "opt_tecido": "Areia",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-007",
        "description": "Cabeceira de Cama Queen Estofada",
        "altura": 110.00,
        "largura": 160.00,
        "profundidade": 8.00,
        "opt_aluminio": None,
        "opt_tecido": "Canela",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-008",
        "description": "Cabeceira de Cama King Estofada",
        "altura": 110.00,
        "largura": 193.00,
        "profundidade": 8.00,
        "opt_aluminio": None,
        "opt_tecido": "Taupe",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-009",
        "description": "Puf Redondo Estofado",
        "altura": 42.00,
        "largura": 60.00,
        "profundidade": 60.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Camomila",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-010",
        "description": "Poltrona de Escritório Estofada",
        "altura": 105.00,
        "largura": 68.00,
        "profundidade": 65.00,
        "opt_aluminio": "Preto",
        "opt_tecido": "Areia",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-011",
        "description": "Sofá Canto em L Retrátil",
        "altura": 95.00,
        "largura": 280.00,
        "profundidade": 220.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Camomila",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-012",
        "description": "Cadeira de Balanço Estofada",
        "altura": 98.00,
        "largura": 65.00,
        "profundidade": 80.00,
        "opt_aluminio": "Escovado",
        "opt_tecido": "Canela",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-013",
        "description": "Banco de Entrada com Encosto",
        "altura": 85.00,
        "largura": 100.00,
        "profundidade": 38.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Taupe",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-014",
        "description": "Cadeira Suspensa com Corda Náutica",
        "altura": 120.00,
        "largura": 75.00,
        "profundidade": 75.00,
        "opt_aluminio": "Preto",
        "opt_tecido": None,
        "opt_corda": "Natural",
    },
    {
        "product_code": "PRD-015",
        "description": "Poltrona Área Externa com Corda",
        "altura": 85.00,
        "largura": 72.00,
        "profundidade": 70.00,
        "opt_aluminio": "Natural",
        "opt_tecido": None,
        "opt_corda": "Grafite",
    },
    {
        "product_code": "PRD-016",
        "description": "Sofá de 2 Lugares Área Externa com Corda",
        "altura": 80.00,
        "largura": 155.00,
        "profundidade": 72.00,
        "opt_aluminio": "Escovado",
        "opt_tecido": None,
        "opt_corda": "Areia",
    },
    {
        "product_code": "PRD-017",
        "description": "Mesa com Tampo Estofado",
        "altura": 45.00,
        "largura": 110.00,
        "profundidade": 60.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Camomila",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-018",
        "description": "Divã Estofado com Braço",
        "altura": 82.00,
        "largura": 200.00,
        "profundidade": 80.00,
        "opt_aluminio": None,
        "opt_tecido": "Areia",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-019",
        "description": "Cadeira Gamer Estofada Premium",
        "altura": 130.00,
        "largura": 70.00,
        "profundidade": 68.00,
        "opt_aluminio": "Preto",
        "opt_tecido": "Taupe",
        "opt_corda": None,
    },
    {
        "product_code": "PRD-020",
        "description": "Poltrona Amamentação com Balanço",
        "altura": 102.00,
        "largura": 78.00,
        "profundidade": 82.00,
        "opt_aluminio": "Natural",
        "opt_tecido": "Camomila",
        "opt_corda": None,
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            __import__("sqlalchemy").select(Product.product_code)
        )
        existing_codes = {row[0] for row in existing}

        new_products = [
            Product(**data)
            for data in PRODUCTS
            if data["product_code"] not in existing_codes
        ]

        if not new_products:
            print("Seed já executado — nenhum produto novo inserido.")
            return

        session.add_all(new_products)
        await session.commit()
        print(f"Seed concluído: {len(new_products)} produto(s) inserido(s).")
        for p in new_products:
            print(f"  {p.product_code} — {p.description}")


if __name__ == "__main__":
    asyncio.run(seed())
