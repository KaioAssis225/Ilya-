"""
Seed de luxo — 5 produtos Ilya, catálogo de opcionais, 2 clientes, 1 rep, 3 pedidos.
Limpa todos os dados existentes antes de inserir.

Executar dentro do container:
    docker compose exec backend python seed.py
"""
import asyncio
import sys
import os
import re
import uuid
import math

sys.path.insert(0, os.path.dirname(__file__))


def _slugify(text: str) -> str:
    text = text.lower()
    for src, dst in [('á','a'),('à','a'),('â','a'),('ã','a'),('ä','a'),
                     ('é','e'),('è','e'),('ê','e'),('ë','e'),
                     ('í','i'),('ó','o'),('ô','o'),('õ','o'),
                     ('ú','u'),('ü','u'),('ç','c')]:
        text = text.replace(src, dst)
    text = re.sub(r'[^a-z0-9_]+', '_', text)
    return text.strip('_')

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.models.optional_color import OptionalColor
from app.models.product import Product
from app.models.product_type import ProductType
from app.models.optional_category import OptionalCategory
from app.models.client import Client
from app.models.representative import Representative
from app.models.order import Order, OrderItem


# ── Catálogo de opcionais ────────────────────────────────────────────────────

OPTIONALS_DATA = [
    # Alumínio
    {"category": "aluminio",       "color_name": "Natural"},
    {"category": "aluminio",       "color_name": "Escovado"},
    {"category": "aluminio",       "color_name": "Preto"},
    # Tecido Faixa 1 (exterior/contrato)
    {"category": "tecido_faixa_1", "color_name": "Camomila"},
    {"category": "tecido_faixa_1", "color_name": "Canela"},
    {"category": "tecido_faixa_1", "color_name": "Areia"},
    {"category": "tecido_faixa_1", "color_name": "Taupe"},
    # Tecido Faixa 2 (residencial premium)
    {"category": "tecido_faixa_2", "color_name": "Camomila"},
    {"category": "tecido_faixa_2", "color_name": "Canela"},
    {"category": "tecido_faixa_2", "color_name": "Areia"},
    # Corda náutica
    {"category": "corda",          "color_name": "Natural"},
    {"category": "corda",          "color_name": "Grafite"},
    {"category": "corda",          "color_name": "Areia"},
    # Madeira Teka
    {"category": "madeira_teka",   "color_name": "Pátina"},
    {"category": "madeira_teka",   "color_name": "Óleo Natural"},
    {"category": "madeira_teka",   "color_name": "Carvão"},
    # Madeira Freijó
    {"category": "madeira_freijo", "color_name": "Pátina"},
    {"category": "madeira_freijo", "color_name": "Óleo Natural"},
    {"category": "madeira_freijo", "color_name": "Carvão"},
    # Couro Soleta
    {"category": "couro_soleta",   "color_name": "Caramelo"},
    {"category": "couro_soleta",   "color_name": "Palha"},
    {"category": "couro_soleta",   "color_name": "Arara Azul"},
    {"category": "couro_soleta",   "color_name": "Preto"},
    {"category": "couro_soleta",   "color_name": "Cidreira"},
    # Couro Pele
    {"category": "couro_pele",     "color_name": "Caramelo"},
    {"category": "couro_pele",     "color_name": "Palha"},
    {"category": "couro_pele",     "color_name": "Arara Azul"},
    {"category": "couro_pele",     "color_name": "Preto"},
    {"category": "couro_pele",     "color_name": "Cidreira"},
]

# ── Produtos de luxo ─────────────────────────────────────────────────────────

PRODUCTS_DATA = [
    {
        "product_code": "ILY-001",
        "description": "Poltrona Riviera Outdoor",
        "type": "Poltrona",
        "is_circular": False,
        "largura": 0.75,
        "profundidade": 0.80,
        "altura": 0.72,
        "price": 4800.0,
        "optional_categories": ["aluminio", "corda", "tecido_faixa_1"],
    },
    {
        "product_code": "ILY-002",
        "description": "Sofá Modular Capri 3 Lugares",
        "type": "Sofá",
        "is_circular": False,
        "largura": 2.25,
        "profundidade": 0.90,
        "altura": 0.85,
        "price": 12500.0,
        "optional_categories": ["aluminio", "tecido_faixa_1", "tecido_faixa_2"],
    },
    {
        "product_code": "ILY-003",
        "description": "Mesa de Centro Atena — Tampo Circular em Teka",
        "type": "Mesa",
        "is_circular": True,
        "largura": 0.90,
        "profundidade": 0.0,
        "altura": 0.38,
        "price": 6800.0,
        "optional_categories": ["madeira_teka"],
    },
    {
        "product_code": "ILY-004",
        "description": "Chaise Longue Amalfi em Freijó e Couro",
        "type": "Chaise",
        "is_circular": False,
        "largura": 1.80,
        "profundidade": 0.75,
        "altura": 0.82,
        "price": 11200.0,
        "optional_categories": ["madeira_freijo", "couro_pele"],
    },
    {
        "product_code": "ILY-005",
        "description": "Cadeira Venezia com Corda e Couro Soleta",
        "type": "Cadeira",
        "is_circular": False,
        "largura": 0.55,
        "profundidade": 0.60,
        "altura": 0.92,
        "price": 3200.0,
        "optional_categories": ["aluminio", "corda", "couro_soleta"],
    },
    {
        "product_code": "ILY-006",
        "description": "Banqueta Alta Asti em Alumínio e Corda",
        "type": "Banqueta",
        "is_circular": False,
        "largura": 0.48,
        "profundidade": 0.50,
        "altura": 1.05,
        "price": 2800.0,
        "optional_categories": ["aluminio", "corda", "tecido_faixa_1"],
    },
    {
        "product_code": "ILY-007",
        "description": "Mesa de Jantar Gaia — Tampo Circular em Freijó",
        "type": "Mesa",
        "is_circular": True,
        "largura": 1.40,
        "profundidade": 0.0,
        "altura": 0.76,
        "price": 8200.0,
        "optional_categories": ["madeira_freijo"],
    },
    {
        "product_code": "ILY-008",
        "description": "Aparador Prisma em Teka e Couro Soleta",
        "type": "Aparador",
        "is_circular": False,
        "largura": 1.60,
        "profundidade": 0.45,
        "altura": 0.78,
        "price": 9500.0,
        "optional_categories": ["madeira_teka", "couro_soleta"],
    },
    {
        "product_code": "ILY-009",
        "description": "Poltrona Lounge Ninho em Corda e Tecido",
        "type": "Poltrona",
        "is_circular": False,
        "largura": 0.85,
        "profundidade": 0.82,
        "altura": 0.74,
        "price": 5400.0,
        "optional_categories": ["corda", "tecido_faixa_2"],
    },
    {
        "product_code": "ILY-010",
        "description": "Sofá Curvo Verano Outdoor em Tecido",
        "type": "Sofá",
        "is_circular": False,
        "largura": 2.40,
        "profundidade": 1.10,
        "altura": 0.80,
        "price": 15800.0,
        "optional_categories": ["tecido_faixa_1", "tecido_faixa_2"],
    },
]

CLIENTS_DATA = [
    {
        "name": "Marina Tavares",
        "phone": "(11) 99234-5678",
        "email": "marina.tavares@email.com",
        "cep": "01310-100",
        "numero": "450",
        "address": "Av. Paulista, Bela Vista",
        "city": "São Paulo",
        "state": "SP",
    },
    {
        "name": "Castro & Associados Arquitetura",
        "phone": "(21) 3042-8800",
        "email": "projetos@castroarq.com.br",
        "cep": "22440-040",
        "numero": "200",
        "address": "Rua Visconde de Pirajá, Ipanema",
        "city": "Rio de Janeiro",
        "state": "RJ",
    },
    {
        "name": "Ricardo Vasconcelos",
        "phone": "(11) 98111-2222",
        "email": "ricardo.vasc@design.com.br",
        "cep": "04530-000",
        "numero": "88",
        "address": "Rua Joaquim Floriano, Itaim Bibi",
        "city": "São Paulo",
        "state": "SP",
    },
    {
        "name": "Studio Lumina Interiores",
        "phone": "(31) 3288-4400",
        "email": "contato@studiolumina.com",
        "cep": "30130-100",
        "numero": "1012",
        "address": "Av. Afonso Pena, Centro",
        "city": "Belo Horizonte",
        "state": "MG",
    },
]

REPS_DATA = [
    {
        "name": "André Menezes",
        "phone": "(11) 98765-4321",
        "email": "andre.menezes@ilyarep.com",
        "cep": "04543-011",
        "numero": "12",
        "address": "Av. Brigadeiro Faria Lima, Itaim Bibi",
        "city": "São Paulo",
        "state": "SP",
    },
    {
        "name": "Bianca Rocha",
        "phone": "(21) 97654-3210",
        "email": "bianca.rocha@ilyarep.com",
        "cep": "22410-000",
        "numero": "55",
        "address": "Av. Vieira Souto, Ipanema",
        "city": "Rio de Janeiro",
        "state": "RJ",
    },
    {
        "name": "Carlos Eduardo",
        "phone": "(31) 98888-7777",
        "email": "carlos.eduardo@ilyarep.com",
        "cep": "30300-000",
        "numero": "300",
        "address": "Av. do Contorno, Savassi",
        "city": "Belo Horizonte",
        "state": "MG",
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        print("Limpando dados existentes...")
        await db.execute(text("DELETE FROM order_items"))
        await db.execute(text("DELETE FROM orders"))
        await db.execute(text("DELETE FROM product_optionals"))
        await db.execute(text("DELETE FROM products"))
        await db.execute(text("DELETE FROM optionals"))
        await db.execute(text("UPDATE users SET rep_id = NULL, linked_id = NULL WHERE rep_id IS NOT NULL OR linked_id IS NOT NULL"))
        await db.execute(text("DELETE FROM clients"))
        await db.execute(text("DELETE FROM representatives"))
        await db.execute(text("DELETE FROM product_types"))
        await db.execute(text("DELETE FROM optional_categories"))
        await db.commit()

        # ── Tipos de Móveis ───────────────────────────────────────────────
        print("Criando tipos de móveis...")
        for name in ['Poltrona', 'Sofá', 'Mesa', 'Cadeira', 'Banqueta', 'Chaise', 'Aparador', 'Outro']:
            db.add(ProductType(name=name))
        await db.flush()

        # ── Categorias de Opcionais ───────────────────────────────────────
        print("Criando categorias de opcionais...")
        for code, name in [
            ('aluminio',       'Alumínio'),
            ('tecido_faixa_1', 'Tecido Faixa 1'),
            ('tecido_faixa_2', 'Tecido Faixa 2'),
            ('corda',          'Corda'),
            ('madeira_teka',   'Madeira Teka'),
            ('madeira_freijo', 'Madeira Freijó'),
            ('couro_soleta',   'Couro Soleta'),
            ('couro_pele',     'Couro Pele'),
        ]:
            db.add(OptionalCategory(name=name, code=code))
        await db.flush()

        # ── Opcionais ──────────────────────────────────────────────────────
        print("Criando catálogo de opcionais...")
        SWATCH_DIR = "app/static/uploads/optionals"
        optionals_map: dict[str, list[OptionalColor]] = {}
        for data in OPTIONALS_DATA:
            cat_slug = _slugify(data["category"])
            color_slug = _slugify(data["color_name"])
            swatch_path = f"{SWATCH_DIR}/swatch_{cat_slug}_{color_slug}.png"
            photo_path = swatch_path if os.path.exists(swatch_path) else None
            opt = OptionalColor(**data, photo_path=photo_path)
            db.add(opt)
            optionals_map.setdefault(data["category"], []).append(opt)
        await db.flush()

        # ── Map beautiful physical product photos ────────────────────────────────
        PRODUCT_PHOTOS = {
            "ILY-001": "app/static/uploads/chair_rope_luxury.png",
            "ILY-002": "app/static/uploads/sofa_boucle_lux.png",
            "ILY-003": "app/static/uploads/table_freijo_center.png",
            "ILY-004": "app/static/uploads/stool_leather_bar.png",
            "ILY-005": "app/static/uploads/table_teak_dining.png",
            "ILY-006": "app/static/uploads/stool_rope_bar.png",
            "ILY-007": "app/static/uploads/table_freijo_dining.png",
            "ILY-008": "app/static/uploads/sideboard_teak_leather.png",
            "ILY-009": "app/static/uploads/armchair_lounge_nest.png",
            "ILY-010": "app/static/uploads/sofa_curved_outdoor.png",
        }

        # ── Produtos ───────────────────────────────────────────────────────
        print("Criando produtos de luxo...")
        products_map: dict[str, Product] = {}
        for data in PRODUCTS_DATA:
            code = data["product_code"]
            cats = data.pop("optional_categories")
            photo_path = PRODUCT_PHOTOS.get(code)
            product = Product(**data, photo_path=photo_path)
            product.optionals = [o for cat in cats for o in optionals_map.get(cat, [])]
            db.add(product)
            products_map[code] = product
        await db.flush()

        # ── Clientes ───────────────────────────────────────────────────────
        print("Criando clientes...")
        clients: list[Client] = []
        for data in CLIENTS_DATA:
            c = Client(**data)
            db.add(c)
            clients.append(c)
        await db.flush()

        # ── Representantes ──────────────────────────────────────────────────
        print("Criando representantes...")
        reps: list[Representative] = []
        for rdata in REPS_DATA:
            r = Representative(**rdata)
            db.add(r)
            reps.append(r)
        await db.flush()

        # ── Pedidos de simulação ───────────────────────────────────────────
        print("Criando pedidos de simulação...")

        def make_order(code: str, orc_id: str, client: Client, rep_obj, items_data: list[dict]) -> Order:
            items = []
            total = 0.0
            for d in items_data:
                p = products_map[d["product_code"]]
                subtotal = d["qty"] * d["unit_price"]
                total += subtotal
                items.append(OrderItem(
                    id=uuid.uuid4(),
                    product_code=p.product_code,
                    description=p.description,
                    is_circular=p.is_circular,
                    altura=p.altura,
                    largura=p.largura,
                    profundidade=p.profundidade,
                    opt_aluminio=d.get("opt_aluminio"),
                    opt_tecido=d.get("opt_tecido"),
                    opt_corda=d.get("opt_corda"),
                    qty=d["qty"],
                    unit_price=d["unit_price"],
                ))
            return Order(
                id=uuid.uuid4(),
                code=code,
                orc_id=orc_id,
                client_id=client.id,
                rep_id=rep_obj.id if rep_obj else None,
                total_value=round(total, 2),
                notes=None,
                items=items,
            )

        order1 = make_order("PED-0001", "ORC-0001", clients[0], reps[0], [
            {"product_code": "ILY-001", "qty": 2, "unit_price": 4800.0,
             "opt_aluminio": "Natural", "opt_tecido": "Areia", "opt_corda": "Grafite"},
        ])
        order2 = make_order("PED-0002", "ORC-0002", clients[1], None, [
            {"product_code": "ILY-002", "qty": 1, "unit_price": 12500.0,
             "opt_aluminio": "Preto", "opt_tecido": "Taupe", "opt_corda": None},
            {"product_code": "ILY-003", "qty": 1, "unit_price": 6800.0,
             "opt_aluminio": "Carvão", "opt_tecido": None, "opt_corda": None},
        ])
        order3 = make_order("PED-0003", "ORC-0003", clients[0], reps[0], [
            {"product_code": "ILY-005", "qty": 3, "unit_price": 3200.0,
             "opt_aluminio": "Escovado", "opt_tecido": "Caramelo", "opt_corda": "Natural"},
        ])
        order4 = make_order("PED-0004", "ORC-0004", clients[2], reps[1], [
            {"product_code": "ILY-006", "qty": 4, "unit_price": 1800.0,
             "opt_aluminio": "Preto", "opt_tecido": "Camomila", "opt_corda": "Grafite"},
            {"product_code": "ILY-007", "qty": 1, "unit_price": 8200.0,
             "opt_aluminio": "Óleo Natural", "opt_tecido": None, "opt_corda": None},
        ])
        order5 = make_order("PED-0005", "ORC-0005", clients[3], reps[2], [
            {"product_code": "ILY-008", "qty": 1, "unit_price": 9500.0,
             "opt_aluminio": "Óleo Natural", "opt_tecido": "Caramelo", "opt_corda": None},
        ])
        order6 = make_order("PED-0006", "ORC-0006", clients[2], reps[1], [
            {"product_code": "ILY-009", "qty": 2, "unit_price": 5400.0,
             "opt_aluminio": None, "opt_tecido": "Areia", "opt_corda": "Areia"},
        ])
        order7 = make_order("PED-0007", "ORC-0007", clients[1], reps[0], [
            {"product_code": "ILY-010", "qty": 1, "unit_price": 15800.0,
             "opt_aluminio": None, "opt_tecido": "Taupe", "opt_corda": None},
        ])
        order8 = make_order("PED-0008", "ORC-0008", clients[0], None, [
            {"product_code": "ILY-004", "qty": 1, "unit_price": 11200.0,
             "opt_aluminio": "Pátina", "opt_tecido": "Palha", "opt_corda": None},
        ])
        order9 = make_order("PED-0009", "ORC-0009", clients[3], reps[2], [
            {"product_code": "ILY-001", "qty": 4, "unit_price": 4800.0,
             "opt_aluminio": "Preto", "opt_tecido": "Taupe", "opt_corda": "Grafite"},
            {"product_code": "ILY-005", "qty": 4, "unit_price": 3200.0,
             "opt_aluminio": "Preto", "opt_tecido": "Preto", "opt_corda": "Grafite"},
        ])
        order10 = make_order("PED-0010", "ORC-0010", clients[2], None, [
            {"product_code": "ILY-003", "qty": 2, "unit_price": 6800.0,
             "opt_aluminio": "Óleo Natural", "opt_tecido": None, "opt_corda": None},
            {"product_code": "ILY-007", "qty": 1, "unit_price": 8200.0,
             "opt_aluminio": "Óleo Natural", "opt_tecido": None, "opt_corda": None},
        ])

        db.add_all([order1, order2, order3, order4, order5, order6, order7, order8, order9, order10])
        await db.commit()

        print("\nSeed concluído com sucesso!")
        print(f"  {len(OPTIONALS_DATA)} opcionais | {len(PRODUCTS_DATA)} produtos | {len(CLIENTS_DATA)} clientes | {len(REPS_DATA)} representantes | 10 pedidos")


if __name__ == "__main__":
    asyncio.run(seed())
