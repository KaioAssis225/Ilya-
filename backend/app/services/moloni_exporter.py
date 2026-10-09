"""Adaptador profundo: transforma um pedido EU finalizado em orçamento Moloni."""
from datetime import date, datetime, timezone
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.moloni_crypto import decrypt_token
from app.models.client import Client
from app.models.moloni import MoloniConnection, MoloniCustomerLink, MoloniExportJob, MoloniProductLink, MoloniTaxMapping
from app.models.order import Order
from app.models.product import Product

class MoloniError(RuntimeError): pass

def _configured():
    return all((settings.MOLONI_DOCUMENT_SET_ID, settings.MOLONI_MATURITY_DATE_ID, settings.MOLONI_PAYMENT_METHOD_ID, settings.MOLONI_PRODUCT_CATEGORY_ID, settings.MOLONI_PRODUCT_UNIT_ID))

class MoloniApi:
    def __init__(self, connection): self.connection = connection; self.token = decrypt_token(connection.access_token_ciphertext)
    async def post(self, endpoint, data):
        url = settings.MOLONI_API_BASE_URL.rstrip("/") + "/" + endpoint.lstrip("/") + "/"
        async with httpx.AsyncClient(timeout=settings.MOLONI_TIMEOUT_SECONDS) as client:
            # Moloni aceita JSON somente com json=true; assim arrays de produtos
            # e impostos chegam como estruturas, sem serialização ambígua de form.
            response = await client.post(url, params={"access_token": self.token, "json": "true", "human_errors": "true"}, json=data)
        response.raise_for_status(); payload = response.json()
        if not payload.get("valid"):
            raise MoloniError("Moloni rejeitou os dados: " + str(payload.get("errors", "erro desconhecido"))[:400])
        return payload

async def deliver_job(db: AsyncSession, job: MoloniExportJob) -> int:
    if not _configured(): raise MoloniError("Configuração Moloni incompleta (série, prazo, pagamento, categoria ou unidade).")
    connection = (await db.execute(select(MoloniConnection).where(MoloniConnection.is_active.is_(True)).limit(1))).scalar_one_or_none()
    if not connection: raise MoloniError("Nenhuma conexão Moloni ativa.")
    order = (await db.execute(select(Order).where(Order.id == job.order_id).options(selectinload(Order.items)))).scalar_one()
    if order.market_code != "EU" or not order.is_finalized: raise MoloniError("Pedido não é um pedido EU finalizado.")
    client = (await db.execute(select(Client).where(Client.id == order.client_id))).scalar_one()
    if not client.tax_id: raise MoloniError("Cliente EU sem NIF/tax_id.")
    api = MoloniApi(connection)
    link = (await db.execute(select(MoloniCustomerLink).where(MoloniCustomerLink.connection_id == connection.id, MoloniCustomerLink.client_id == client.id))).scalar_one_or_none()
    if link: customer_id = link.moloni_customer_id
    else:
        found = await api.post("customers/getByVat", {"company_id": connection.company_id, "vat": client.tax_id})
        customers = found.get("customers") or found.get("data") or []
        if customers: customer_id = int(customers[0]["customer_id"])
        else:
            number = (await api.post("customers/getNextNumber", {"company_id": connection.company_id})).get("number")
            created = await api.post("customers/insert", {"company_id": connection.company_id, "vat": client.tax_id, "number": number, "name": client.name, "language_id": settings.MOLONI_LANGUAGE_ID, "address": client.address, "zip_code": client.cep, "city": client.city, "country_id": 1, "email": client.email or "", "phone": client.phone, "maturity_date_id": settings.MOLONI_MATURITY_DATE_ID, "payment_method_id": settings.MOLONI_PAYMENT_METHOD_ID})
            customer_id = int(created["customer_id"])
        db.add(MoloniCustomerLink(connection_id=connection.id, client_id=client.id, moloni_customer_id=customer_id))
    mappings = {str(rate): tax_id for rate, tax_id in (await db.execute(select(MoloniTaxMapping.vat_rate, MoloniTaxMapping.moloni_tax_id).where(MoloniTaxMapping.connection_id == connection.id))).all()}
    products = []
    for index, item in enumerate(order.items):
        product = (await db.execute(select(Product).where(Product.market_code == "EU", Product.product_code == item.product_code))).scalar_one_or_none()
        if not product: raise MoloniError("Produto EU não encontrado: " + item.product_code)
        plink = (await db.execute(select(MoloniProductLink).where(MoloniProductLink.connection_id == connection.id, MoloniProductLink.product_id == product.id))).scalar_one_or_none()
        if plink: pid = plink.moloni_product_id
        else:
            created = await api.post("products/insert", {"company_id": connection.company_id, "category_id": settings.MOLONI_PRODUCT_CATEGORY_ID, "type": 1, "name": product.description, "reference": product.product_code, "price": str(product.price_lojista), "unit_id": settings.MOLONI_PRODUCT_UNIT_ID, "has_stock": 0, "stock": 0})
            pid = int(created["product_id"]); db.add(MoloniProductLink(connection_id=connection.id, product_id=product.id, moloni_product_id=pid))
        rate = str(item.ipi_rate)
        if rate not in mappings: raise MoloniError("IVA sem mapeamento Moloni: " + rate)
        products.append({"product_id": pid, "name": item.description, "qty": str(item.qty), "price": str(item.unit_price), "discount": str(item.discount), "order": index + 1, "taxes": [{"tax_id": mappings[rate], "order": 1, "cumulative": 0}]})
    response = await api.post("estimates/insert", {"company_id": connection.company_id, "date": (order.finalized_at or datetime.now(timezone.utc)).date().isoformat(), "expiration_date": date.today().isoformat(), "maturity_date_id": settings.MOLONI_MATURITY_DATE_ID, "document_set_id": settings.MOLONI_DOCUMENT_SET_ID, "customer_id": customer_id, "your_reference": order.code, "products": products, "notes": order.notes or "", "status": 0})
    return int(response["document_id"])
