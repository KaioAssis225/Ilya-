"""Adaptador profundo: transforma um pedido EU finalizado em orçamento Moloni."""
from datetime import date, datetime, timedelta, timezone
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.moloni_crypto import decrypt_token, encrypt_token
from app.models.client import Client
from app.models.moloni import MoloniConnection, MoloniCustomerLink, MoloniExportJob, MoloniProductLink, MoloniTaxMapping
from app.models.order import Order
from app.models.product import Product

class MoloniError(RuntimeError): pass

def _configured():
    return all((settings.MOLONI_DOCUMENT_SET_ID, settings.MOLONI_MATURITY_DATE_ID, settings.MOLONI_PAYMENT_METHOD_ID, settings.MOLONI_PRODUCT_CATEGORY_ID, settings.MOLONI_PRODUCT_UNIT_ID))

class MoloniApi:
    def __init__(self, connection, db: AsyncSession):
        self.connection = connection
        self.db = db
        self.token = decrypt_token(connection.access_token_ciphertext)

    async def _refresh_if_needed(self) -> None:
        expires_at = getattr(self.connection, "token_expires_at", None)
        if expires_at and expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
            return
        try:
            async with httpx.AsyncClient(timeout=settings.MOLONI_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    settings.MOLONI_API_BASE_URL.rstrip("/") + "/grant/",
                    params={
                        "grant_type": "refresh_token",
                        "client_id": settings.MOLONI_CLIENT_ID,
                        "client_secret": settings.MOLONI_CLIENT_SECRET,
                        "refresh_token": decrypt_token(self.connection.refresh_token_ciphertext),
                    },
                )
            response.raise_for_status()
            token = response.json()
            access = token["access_token"]
            refresh = token.get("refresh_token") or decrypt_token(self.connection.refresh_token_ciphertext)
            expires_in = int(token.get("expires_in", 0) or 0)
            if expires_in <= 0:
                raise ValueError("resposta sem validade do token")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise MoloniError("Não foi possível renovar a conexão Moloni. Reconecte a integração.") from exc
        self.token = access
        self.connection.access_token_ciphertext = encrypt_token(access)
        self.connection.refresh_token_ciphertext = encrypt_token(refresh)
        self.connection.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        await self.db.flush()

    async def post(self, endpoint, data):
        await self._refresh_if_needed()
        url = settings.MOLONI_API_BASE_URL.rstrip("/") + "/" + endpoint.lstrip("/") + "/"
        async with httpx.AsyncClient(timeout=settings.MOLONI_TIMEOUT_SECONDS) as client:
            response = await client.post(url, params={"access_token": self.token, "json": "true", "human_errors": "true"}, json=data)
            if response.status_code in (401, 403):
                # Moloni can revoke a token before its locally stored expiry.
                # Force one refresh and retry the same idempotent lookup/write once.
                self.connection.token_expires_at = None
                await self._refresh_if_needed()
                response = await client.post(url, params={"access_token": self.token, "json": "true", "human_errors": "true"}, json=data)
        response.raise_for_status()
        payload = response.json()
        # Alguns endpoints de consulta do Moloni devolvem a lista diretamente,
        # enquanto endpoints de escrita devolvem o envelope {valid: true, ...}.
        if isinstance(payload, list):
            return payload
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
    api = MoloniApi(connection, db)
    link = (await db.execute(select(MoloniCustomerLink).where(MoloniCustomerLink.connection_id == connection.id, MoloniCustomerLink.client_id == client.id))).scalar_one_or_none()
    if link: customer_id = link.moloni_customer_id
    else:
        found = await api.post("customers/getByVat", {"company_id": connection.company_id, "vat": client.tax_id})
        if isinstance(found, list):
            customers = found
        else:
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

