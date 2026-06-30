"""
Seed CRM — Zera e recria representantes, clientes e pedidos.
Mantém produtos, opcionais, tipos de produto e categorias intactos.

Executar dentro do container:
    docker compose exec backend python seed_crm.py
"""
import asyncio
import sys
import os
import uuid
import random
from datetime import datetime, timedelta, timezone

random.seed(2026)

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.models.client import Client
from app.models.representative import Representative
from app.models.order import Order, OrderItem


# ── Representantes ────────────────────────────────────────────────────────────

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
    {
        "name": "Daniela Fonseca",
        "phone": "(41) 99123-4567",
        "email": "daniela.fonseca@ilyarep.com",
        "cep": "80420-000",
        "numero": "88",
        "address": "Rua XV de Novembro, Centro",
        "city": "Curitiba",
        "state": "PR",
    },
    {
        "name": "Eduardo Tavares",
        "phone": "(51) 99876-5432",
        "email": "eduardo.tavares@ilyarep.com",
        "cep": "90010-190",
        "numero": "200",
        "address": "Rua dos Andradas, Centro Histórico",
        "city": "Porto Alegre",
        "state": "RS",
    },
]

# ── Clientes por representante ─────────────────────────────────────────────────
# André (SP): 3 · Bianca (RJ): 4 · Carlos (BH): 2 · Daniela (Curitiba): 5 · Eduardo (POA): 3

CLIENTS_BY_REP = [
    # André Menezes — 3 clientes
    [
        {
            "name": "Marina Drummond Arquitetura",
            "phone": "(11) 3234-5678",
            "email": "marina@drummondark.com.br",
            "cep": "01310-100",
            "numero": "450",
            "address": "Av. Paulista, Bela Vista",
            "city": "São Paulo",
            "state": "SP",
        },
        {
            "name": "Grupo Ópera Decor",
            "phone": "(11) 3421-8899",
            "email": "contato@operadecor.com.br",
            "cep": "04571-010",
            "numero": "220",
            "address": "Av. das Nações Unidas, Morumbi",
            "city": "São Paulo",
            "state": "SP",
        },
        {
            "name": "Felipe Cardoso",
            "phone": "(11) 98111-2222",
            "email": "felipe.cardoso@gmail.com",
            "cep": "04530-000",
            "numero": "88",
            "address": "Rua Joaquim Floriano, Itaim Bibi",
            "city": "São Paulo",
            "state": "SP",
        },
    ],
    # Bianca Rocha — 4 clientes
    [
        {
            "name": "Castro & Lobo Interiores",
            "phone": "(21) 3042-8800",
            "email": "projetos@castrolobo.com.br",
            "cep": "22440-040",
            "numero": "200",
            "address": "Rua Visconde de Pirajá, Ipanema",
            "city": "Rio de Janeiro",
            "state": "RJ",
        },
        {
            "name": "Cláudia Neves Design",
            "phone": "(21) 98776-5544",
            "email": "claudia@nevesdesign.com.br",
            "cep": "22460-020",
            "numero": "30",
            "address": "Av. Epitácio Pessoa, Lagoa",
            "city": "Rio de Janeiro",
            "state": "RJ",
        },
        {
            "name": "Hotel Verão Ipanema",
            "phone": "(21) 2512-3000",
            "email": "compras@hotelveraorj.com.br",
            "cep": "22420-050",
            "numero": "100",
            "address": "Rua Farme de Amoedo, Ipanema",
            "city": "Rio de Janeiro",
            "state": "RJ",
        },
        {
            "name": "Paulo Rezende",
            "phone": "(21) 99000-1111",
            "email": "paulo.rezende@arquitectura.com",
            "cep": "22215-060",
            "numero": "14",
            "address": "Rua Real Grandeza, Botafogo",
            "city": "Rio de Janeiro",
            "state": "RJ",
        },
    ],
    # Carlos Eduardo — 2 clientes
    [
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
        {
            "name": "Rafael Silvério",
            "phone": "(31) 98445-3399",
            "email": "rafael.silverio@arq.com.br",
            "cep": "30315-970",
            "numero": "55",
            "address": "Rua Goitacazes, Savassi",
            "city": "Belo Horizonte",
            "state": "MG",
        },
    ],
    # Daniela Fonseca — 5 clientes
    [
        {
            "name": "Espaço Vivo Interiores",
            "phone": "(41) 3223-5566",
            "email": "contato@espacovivo.com.br",
            "cep": "80240-000",
            "numero": "400",
            "address": "Rua Marechal Deodoro, Centro",
            "city": "Curitiba",
            "state": "PR",
        },
        {
            "name": "Eduardo Malucelli",
            "phone": "(41) 99887-4433",
            "email": "eduardo.malucelli@design.com.br",
            "cep": "80730-000",
            "numero": "150",
            "address": "Av. Batel, Batel",
            "city": "Curitiba",
            "state": "PR",
        },
        {
            "name": "Arch & Co. Arquitetura",
            "phone": "(41) 3025-1188",
            "email": "projetos@archco.com.br",
            "cep": "80410-000",
            "numero": "68",
            "address": "Rua João Negrão, Centro",
            "city": "Curitiba",
            "state": "PR",
        },
        {
            "name": "Giovanna Martins",
            "phone": "(41) 98654-2211",
            "email": "giovanna.martins@outlook.com",
            "cep": "80050-450",
            "numero": "9",
            "address": "Rua Emiliano Perneta, Centro",
            "city": "Curitiba",
            "state": "PR",
        },
        {
            "name": "Clínica São Lucas",
            "phone": "(41) 3361-4400",
            "email": "compras@clinicasaolucas.com.br",
            "cep": "80810-040",
            "numero": "280",
            "address": "Rua Padre Camargo, Alto da Glória",
            "city": "Curitiba",
            "state": "PR",
        },
    ],
    # Eduardo Tavares — 3 clientes
    [
        {
            "name": "Grupo Mirage Decor",
            "phone": "(51) 3212-7788",
            "email": "contato@miragedecor.com.br",
            "cep": "90010-170",
            "numero": "35",
            "address": "Av. Borges de Medeiros, Centro",
            "city": "Porto Alegre",
            "state": "RS",
        },
        {
            "name": "Isabella Borgmann",
            "phone": "(51) 99234-5566",
            "email": "isabella.borgmann@arqdesign.com",
            "cep": "90470-000",
            "numero": "77",
            "address": "Av. Ipiranga, Partenon",
            "city": "Porto Alegre",
            "state": "RS",
        },
        {
            "name": "Hotel das Pedras Gaúcho",
            "phone": "(51) 3055-2000",
            "email": "compras@hoteldaspedras.com.br",
            "cep": "90130-060",
            "numero": "500",
            "address": "Av. Augusto Meyer, Moinhos de Vento",
            "city": "Porto Alegre",
            "state": "RS",
        },
    ],
]

# ── Catálogo de produtos para simulação ───────────────────────────────────────

PRODUCTS_CATALOG = [
    {
        "code": "ILY-001", "desc": "Poltrona Riviera Outdoor",
        "price": 4800.0, "is_circular": False, "l": 0.75, "p": 0.80, "a": 0.72,
        "opt_aluminio": ["Natural", "Escovado", "Preto"],
        "opt_corda": ["Natural", "Grafite", "Areia"],
    },
    {
        "code": "ILY-002", "desc": "Sofá Modular Capri 3 Lugares",
        "price": 12500.0, "is_circular": False, "l": 2.25, "p": 0.90, "a": 0.85,
        "opt_aluminio": ["Natural", "Preto"],
        "opt_tecido": ["Camomila", "Areia", "Taupe"],
    },
    {
        "code": "ILY-003", "desc": "Mesa de Centro Atena — Tampo Circular em Teka",
        "price": 6800.0, "is_circular": True, "l": 0.90, "p": 0.0, "a": 0.38,
        "opt_madeira": ["Pátina", "Óleo Natural", "Carvão"],
    },
    {
        "code": "ILY-004", "desc": "Chaise Longue Amalfi em Freijó e Couro",
        "price": 11200.0, "is_circular": False, "l": 1.80, "p": 0.75, "a": 0.82,
        "opt_madeira": ["Pátina", "Óleo Natural", "Carvão"],
        "opt_couro": ["Caramelo", "Palha", "Preto"],
    },
    {
        "code": "ILY-005", "desc": "Cadeira Venezia com Corda e Couro Soleta",
        "price": 3200.0, "is_circular": False, "l": 0.55, "p": 0.60, "a": 0.92,
        "opt_aluminio": ["Natural", "Escovado", "Preto"],
        "opt_corda": ["Natural", "Grafite"],
        "opt_couro": ["Caramelo", "Palha", "Preto"],
    },
    {
        "code": "ILY-006", "desc": "Banqueta Alta Asti em Alumínio e Corda",
        "price": 2800.0, "is_circular": False, "l": 0.48, "p": 0.50, "a": 1.05,
        "opt_aluminio": ["Natural", "Preto"],
        "opt_corda": ["Natural", "Areia", "Grafite"],
    },
    {
        "code": "ILY-007", "desc": "Mesa de Jantar Gaia — Tampo Circular em Freijó",
        "price": 8200.0, "is_circular": True, "l": 1.40, "p": 0.0, "a": 0.76,
        "opt_madeira": ["Pátina", "Óleo Natural"],
    },
    {
        "code": "ILY-008", "desc": "Aparador Prisma em Teka e Couro Soleta",
        "price": 9500.0, "is_circular": False, "l": 1.60, "p": 0.45, "a": 0.78,
        "opt_madeira": ["Pátina", "Óleo Natural", "Carvão"],
        "opt_couro": ["Caramelo", "Palha", "Arara Azul", "Preto"],
    },
    {
        "code": "ILY-009", "desc": "Poltrona Lounge Ninho em Corda e Tecido",
        "price": 5400.0, "is_circular": False, "l": 0.85, "p": 0.82, "a": 0.74,
        "opt_corda": ["Natural", "Grafite", "Areia"],
        "opt_tecido": ["Camomila", "Canela", "Areia"],
    },
    {
        "code": "ILY-010", "desc": "Sofá Curvo Verano Outdoor em Tecido",
        "price": 15800.0, "is_circular": False, "l": 2.40, "p": 1.10, "a": 0.80,
        "opt_tecido": ["Camomila", "Areia", "Taupe"],
    },
]

NOTES_POOL = [
    "Entrega urgente — obra em andamento.",
    "Cliente solicitou embalagem reforçada.",
    "Pedido para projeto residencial de alto padrão.",
    "Confirmar medidas antes do envio.",
    "Faturar para CNPJ do escritório.",
    "Prazo de entrega combinado em 45 dias.",
    "Tecido aprovado em amostra física.",
    "Instalar na cobertura — acesso restrito.",
    None, None, None,  # ~30% sem observação
]


def pick(lst: list) -> str | None:
    return random.choice(lst) if lst else None


def random_date_past_year() -> datetime:
    days_back = random.randint(0, 365)
    return datetime.now(timezone.utc) - timedelta(days=days_back)


def make_order(code: str, orc_id: str, client: Client, rep: Representative, created_at: datetime) -> Order:
    num_items = random.randint(1, 3)
    chosen = random.sample(PRODUCTS_CATALOG, min(num_items, len(PRODUCTS_CATALOG)))
    items = []
    total = 0.0
    for p in chosen:
        qty = random.randint(1, 4)
        total += qty * p["price"]
        items.append(OrderItem(
            id=uuid.uuid4(),
            product_code=p["code"],
            description=p["desc"],
            is_circular=p["is_circular"],
            largura=p["l"],
            profundidade=p.get("p", 0.0),
            altura=p["a"],
            opt_aluminio=pick(p.get("opt_aluminio", [])),
            opt_madeira=pick(p.get("opt_madeira", [])),
            opt_tecido=pick(p.get("opt_tecido", [])),
            opt_couro=pick(p.get("opt_couro", [])),
            opt_corda=pick(p.get("opt_corda", [])),
            qty=qty,
            unit_price=p["price"],
        ))
    return Order(
        id=uuid.uuid4(),
        code=code,
        orc_id=orc_id,
        client_id=client.id,
        rep_id=rep.id,
        total_value=round(total, 2),
        notes=random.choice(NOTES_POOL),
        created_at=created_at,
        items=items,
    )


async def seed_crm() -> None:
    async with AsyncSessionLocal() as db:
        print("Limpando pedidos, clientes e representantes existentes...")
        await db.execute(text("DELETE FROM order_items"))
        await db.execute(text("DELETE FROM orders"))
        await db.execute(text(
            "UPDATE users SET rep_id = NULL, linked_id = NULL "
            "WHERE rep_id IS NOT NULL OR linked_id IS NOT NULL"
        ))
        await db.execute(text("DELETE FROM clients"))
        await db.execute(text("DELETE FROM representatives"))
        await db.commit()

        # ── Representantes ─────────────────────────────────────────────────
        print("Criando 5 representantes...")
        reps: list[Representative] = []
        for rdata in REPS_DATA:
            r = Representative(**rdata)
            db.add(r)
            reps.append(r)
        await db.flush()

        # ── Clientes ───────────────────────────────────────────────────────
        print("Criando clientes vinculados por representante...")
        clients_by_rep: list[list[Client]] = []
        total_clients = 0
        for rep, clients_data in zip(reps, CLIENTS_BY_REP):
            rep_clients: list[Client] = []
            for cdata in clients_data:
                c = Client(**cdata, rep_id=rep.id)
                db.add(c)
                rep_clients.append(c)
                total_clients += 1
            clients_by_rep.append(rep_clients)
        await db.flush()

        # ── Pedidos ────────────────────────────────────────────────────────
        print("Gerando pedidos simulados (10–15 por representante)...")
        order_counter = 1
        total_orders = 0
        for rep, rep_clients in zip(reps, clients_by_rep):
            num_orders = random.randint(10, 15)
            print(f"  {rep.name} ({rep.city}/{rep.state}) — {len(rep_clients)} clientes — {num_orders} pedidos")
            for _ in range(num_orders):
                client = random.choice(rep_clients)
                code = f"PED-{order_counter:04d}"
                orc_id = f"ORC-{order_counter:04d}"
                created_at = random_date_past_year()
                order = make_order(code, orc_id, client, rep, created_at)
                db.add(order)
                order_counter += 1
                total_orders += 1

        await db.commit()

        print(f"\n✓ Seed CRM concluído com sucesso!")
        print(f"  Representantes : 5")
        print(f"  Clientes       : {total_clients}")
        print(f"  Pedidos        : {total_orders}")


if __name__ == "__main__":
    asyncio.run(seed_crm())
