"""Adaptador profundo: transforma um pedido EU finalizado em orçamento Moloni."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.moloni_crypto import decrypt_token, encrypt_token
from app.core.observability import external_exception, external_invalid, httpx_event_hooks
from app.models.client import Client
from app.models.moloni import MoloniConnection, MoloniCustomerLink, MoloniExportJob, MoloniProductLink, MoloniTaxMapping
from app.models.order import Order, OrderItem
from app.models.product import Product

class MoloniError(RuntimeError): pass

def _record(payload, endpoint: str = ""):
    """Normaliza respostas de criação do Moloni que podem vir como lista ou objeto."""
    if isinstance(payload, list):
        if not payload:
            suffix = f" ({endpoint})" if endpoint else ""
            raise MoloniError("Moloni devolveu uma lista vazia para uma operação de gravação" + suffix + ".")
        return payload[0]
    return payload

def _entity_id(payload, *keys, endpoint: str = ""):
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if value is not None:
            return int(value)
    suffix = f" ({endpoint})" if endpoint else ""
    raise MoloniError("Moloni não devolveu identificador" + suffix + ": " + str(payload)[:800])


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
            async with httpx.AsyncClient(timeout=settings.MOLONI_TIMEOUT_SECONDS, event_hooks=httpx_event_hooks()) as client:
                response = await client.get(
                    settings.MOLONI_API_BASE_URL.rstrip("/") + "/grant/",
                    params={
                        "grant_type": "refresh_token",
                        "client_id": settings.MOLONI_CLIENT_ID,
                        "client_secret": settings.MOLONI_CLIENT_SECRET,
                        "refresh_token": decrypt_token(self.connection.refresh_token_ciphertext),
                    },
                    extensions={"ilya_dependency": "moloni"},
                )
            response.raise_for_status()
            token = response.json()
            access = token["access_token"]
            refresh = token.get("refresh_token") or decrypt_token(self.connection.refresh_token_ciphertext)
            expires_in = int(token.get("expires_in", 0) or 0)
            if expires_in <= 0:
                raise ValueError("resposta sem validade do token")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, httpx.HTTPError):
                external_exception(exc)
            else:
                external_invalid("moloni")
            raise MoloniError("Não foi possível renovar a conexão Moloni. Reconecte a integração.") from exc
        self.token = access
        self.connection.access_token_ciphertext = encrypt_token(access)
        self.connection.refresh_token_ciphertext = encrypt_token(refresh)
        self.connection.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        await self.db.flush()

    async def post(self, endpoint, data):
        await self._refresh_if_needed()
        url = settings.MOLONI_API_BASE_URL.rstrip("/") + "/" + endpoint.lstrip("/") + "/"
        try:
            async with httpx.AsyncClient(timeout=settings.MOLONI_TIMEOUT_SECONDS, event_hooks=httpx_event_hooks()) as client:
                response = await client.post(url, params={"access_token": self.token, "json": "true", "human_errors": "true"}, json=data, extensions={"ilya_dependency": "moloni"})
                if response.status_code in (401, 403):
                    # Moloni can revoke a token before its locally stored expiry.
                    # Force one refresh and retry the same idempotent lookup/write once.
                    self.connection.token_expires_at = None
                    await self._refresh_if_needed()
                    response = await client.post(url, params={"access_token": self.token, "json": "true", "human_errors": "true"}, json=data, extensions={"ilya_dependency": "moloni"})
        except httpx.HTTPError as exc:
            external_exception(exc)
            raise
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            # A mensagem do httpx traz a URL, e o Moloni exige o access_token
            # na query: repassá-la gravaria o token em texto no last_error.
            raise MoloniError(f"Moloni respondeu HTTP {response.status_code} em {endpoint}.") from None
        try:
            payload = response.json()
        except ValueError:
            external_invalid("moloni")
            raise
        # Alguns endpoints de consulta do Moloni devolvem a lista diretamente,
        # enquanto endpoints de escrita devolvem o envelope {valid: true, ...}.
        if isinstance(payload, list):
            return payload
        if payload.get("valid", True) in (False, 0, "0"):
            raise MoloniError(f"Moloni rejeitou {endpoint}: " + str(payload.get("errors", payload))[:800])
        return payload

async def _resolve_product_category_id(api: MoloniApi, company_id: int, path: str | None = None) -> int:
    """Resolve a nested article category, creating missing levels when needed.

    Without a path, validate the configured fallback category for this account.
    """
    if path:
        parent_id = 0
        for name in path.split(" / "):
            offset = 0
            matches = []
            while True:
                response = await api.post(
                    "productCategories/getAll",
                    {"company_id": company_id, "parent_id": parent_id, "qty": 50, "offset": offset},
                )
                categories = response if isinstance(response, list) else response.get("categories") or response.get("data") or []
                matches.extend(
                    category for category in categories
                    if isinstance(category, dict) and str(category.get("name", "")).casefold() == name.casefold()
                )
                if len(categories) < 50:
                    break
                offset += 50
            if len(matches) > 1:
                raise MoloniError(f"Categoria Moloni ambígua: {path}")
            if matches:
                parent_id = int(matches[0]["category_id"])
            else:
                created = _record(await api.post(
                    "productCategories/insert",
                    {"company_id": company_id, "parent_id": parent_id, "name": name},
                ), "productCategories/insert")
                parent_id = _entity_id(created, "category_id", "id", endpoint="productCategories/insert")
        return parent_id

    configured_id = int(settings.MOLONI_PRODUCT_CATEGORY_ID)
    try:
        category = await api.post(
            "productCategories/getOne",
            {"company_id": company_id, "category_id": configured_id},
        )
        if isinstance(category, dict) and int(category.get("category_id", 0)) == configured_id:
            return configured_id
    except MoloniError:
        pass
    categories = await api.post(
        "productCategories/getAll",
        {"company_id": company_id, "parent_id": 0, "qty": 50, "offset": 0},
    )
    if isinstance(categories, dict):
        categories = categories.get("categories") or categories.get("data") or []
    for category in categories or []:
        category_id = category.get("category_id") if isinstance(category, dict) else None
        if category_id is not None:
            return int(category_id)
    raise MoloniError(
        "Moloni não devolveu categorias de artigos para a empresa "
        f"{company_id}; configure MOLONI_PRODUCT_CATEGORY_ID com um category_id válido."
    )

async def _resolve_salesman_id(api: MoloniApi, company_id: int) -> int:
    """Return a salesman id accepted by the API connection."""
    configured_id = int(settings.MOLONI_SALESMAN_ID or 182219)
    salesmen = await api.post(
        "salesmen/getAll",
        {"company_id": company_id, "qty": 50, "offset": 0},
    )
    if isinstance(salesmen, dict):
        salesmen = salesmen.get("salesmen") or salesmen.get("data") or []
    valid_ids = {
        int(salesman["salesman_id"])
        for salesman in salesmen or []
        if isinstance(salesman, dict) and salesman.get("salesman_id") is not None
    }
    if configured_id in valid_ids:
        return configured_id
    if valid_ids:
        return next(iter(valid_ids))
    raise MoloniError(f"Moloni não devolveu vendedores para a empresa {company_id}.")

async def _resolve_tax_mappings(api: MoloniApi, company_id: int, configured: dict[str, int]) -> dict[str, int]:
    """Validate local tax ids and replace stale ids with account-local taxes."""
    taxes = await api.post("taxes/getAll", {"company_id": company_id, "country_id": 1, "qty": 50, "offset": 0})
    if isinstance(taxes, dict):
        taxes = taxes.get("taxes") or taxes.get("data") or []
    by_rate: dict[Decimal, list[dict]] = {}
    valid_ids: set[int] = set()
    for tax in taxes or []:
        if not isinstance(tax, dict) or tax.get("tax_id") is None or tax.get("value") is None:
            continue
        try:
            rate = Decimal(str(tax["value"]))
        except (InvalidOperation, TypeError):
            continue
        tax_id = int(tax["tax_id"])
        valid_ids.add(tax_id)
        by_rate.setdefault(rate, []).append(tax)
    resolved: dict[str, int] = {}
    for rate_text, configured_id in configured.items():
        if int(configured_id) in valid_ids:
            resolved[rate_text] = int(configured_id)
            continue
        try:
            rate = Decimal(str(rate_text))
        except InvalidOperation as exc:
            raise MoloniError(f"IVA inválido configurado: {rate_text}") from exc
        candidates = by_rate.get(rate, [])
        if candidates:
            active = next((tax for tax in candidates if int(tax.get("active_by_default", 0) or 0) == 1), candidates[0])
            resolved[rate_text] = int(active["tax_id"])
            continue
        raise MoloniError(f"Moloni não devolveu imposto para a taxa {rate_text} na empresa {company_id}.")
    return resolved


def _tax_for_rate(rate: str, mappings: dict[str, int]) -> dict:
    if rate not in mappings:
        raise MoloniError("IVA sem mapeamento Moloni: " + rate)
    value = Decimal(rate)
    if value == 0:
        raise MoloniError("Artigo com IVA zero precisa de motivo de isenção validado antes do envio ao Moloni.")
    return {"tax_id": mappings[rate], "value": float(value), "order": 1, "cumulative": 0}


def _choice_value(choice, locale: str) -> str:
    if choice.custom_text is None:
        return choice.optional_name
    return ("Custom" if locale == "en-GB" else choice.optional_name) + ": " + choice.custom_text


def _line_summary(product_summary: str | None, item: OrderItem, locale: str) -> str:
    choice_lines = [
        f"{(choice.component_name + ' — ') if choice.component_name else ''}{(choice.application_name_en if locale == 'en-GB' and choice.application_name_en else choice.application_name)}: {_choice_value(choice, locale)}"
        for choice in sorted(item.optional_choices, key=lambda row: (row.display_order, str(row.id)))
    ]
    legacy_lines = [f"{category}: {value}" for category, value in item.opt_categories.items()]
    return "\n".join(part for part in [product_summary or "", *legacy_lines, *choice_lines] if part)

async def active_moloni_connection(db: AsyncSession) -> MoloniConnection | None:
    """Conexão ativa única. Com duas ativas o destino dos dados EU seria
    arbitrário (LIMIT 1 sem ordem), então recusa escolher."""
    connections = (await db.execute(select(MoloniConnection).where(MoloniConnection.is_active.is_(True)).limit(2))).scalars().all()
    if len(connections) > 1:
        raise MoloniError("Há mais de uma conexão Moloni ativa; reconecte a empresa correta.")
    return connections[0] if connections else None

async def deliver_job(db: AsyncSession, job: MoloniExportJob) -> int:
    if not _configured(): raise MoloniError("Configuração Moloni incompleta (série, prazo, pagamento, categoria ou unidade).")
    connection = await active_moloni_connection(db)
    if not connection: raise MoloniError("Nenhuma conexão Moloni ativa.")
    order = (await db.execute(select(Order).where(Order.id == job.order_id).options(selectinload(Order.items)))).scalar_one()
    if order.market_code != "EU" or not order.is_finalized: raise MoloniError("Pedido não é um pedido EU finalizado.")
    client = (await db.execute(select(Client).where(Client.id == order.client_id))).scalar_one()
    if not client.tax_id: raise MoloniError("Cliente EU sem NIF/tax_id.")
    api = MoloniApi(connection, db)
    category_ids: dict[str | None, int] = {}
    # Moloni validates this field even when its customer-insert documentation
    # describes salesman_id as optional. Reuse the same configured seller on
    # the customer and estimate so both requests carry a valid integer.
    salesman_id = await _resolve_salesman_id(api, connection.company_id)
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
            created = _record(await api.post("customers/insert", {"company_id": connection.company_id, "vat": client.tax_id, "number": number, "name": client.name, "language_id": settings.MOLONI_LANGUAGE_ID, "address": client.address, "zip_code": client.cep, "city": client.city, "country_id": 1, "email": client.email or "", "phone": client.phone, "salesman_id": salesman_id, "maturity_date_id": settings.MOLONI_MATURITY_DATE_ID, "payment_method_id": settings.MOLONI_PAYMENT_METHOD_ID, "payment_day": 0, "discount": 0, "credit_limit": 0, "delivery_method_id": 0}), "customers/insert")
            customer_id = _entity_id(created, "customer_id", "customerId", "id", endpoint="customers/insert")
        db.add(MoloniCustomerLink(connection_id=connection.id, client_id=client.id, moloni_customer_id=customer_id))
    mappings = {str(rate): int(tax_id) for rate, tax_id in (await db.execute(select(MoloniTaxMapping.vat_rate, MoloniTaxMapping.moloni_tax_id).where(MoloniTaxMapping.connection_id == connection.id))).all()}
    mappings = await _resolve_tax_mappings(api, connection.company_id, mappings)
    products = []
    for index, item in enumerate(order.items):
        product = (await db.execute(select(Product).where(Product.market_code == "EU", Product.product_code == item.product_code))).scalar_one_or_none()
        if not product: raise MoloniError("Produto EU não encontrado: " + item.product_code)
        rate = str(item.ipi_rate)
        tax = _tax_for_rate(rate, mappings)
        plink = (await db.execute(select(MoloniProductLink).where(MoloniProductLink.connection_id == connection.id, MoloniProductLink.product_id == product.id))).scalar_one_or_none()
        if plink: pid = plink.moloni_product_id
        else:
            path = product.article_category_path
            if path not in category_ids:
                category_ids[path] = await _resolve_product_category_id(api, connection.company_id, path)
            article = {
                "company_id": connection.company_id,
                "category_id": category_ids[path],
                "type": 1,
                "name": product.description,
                "summary": product.summary or "",
                "reference": product.product_code,
                "ean": product.ean or "",
                "price": str(product.price_lojista),
                "unit_id": settings.MOLONI_PRODUCT_UNIT_ID,
                "has_stock": 0,
                "stock": 0,
                "taxes": [tax],
            }
            created = _record(await api.post("products/insert", article), "products/insert")
            pid = _entity_id(created, "product_id", "productId", "id", endpoint="products/insert"); db.add(MoloniProductLink(connection_id=connection.id, product_id=product.id, moloni_product_id=pid))
        line_summary = _line_summary(product.summary, item, order.locale)
        products.append({"product_id": pid, "name": item.description, "summary": line_summary, "qty": str(item.qty), "price": str(item.unit_price), "discount": str(item.discount), "order": index + 1, "taxes": [tax]})
    try:
        estimate = {"company_id": connection.company_id, "date": (order.finalized_at or datetime.now(timezone.utc)).date().isoformat(), "expiration_date": date.today().isoformat(), "maturity_date_id": settings.MOLONI_MATURITY_DATE_ID, "document_set_id": settings.MOLONI_DOCUMENT_SET_ID, "customer_id": customer_id, "salesman_id": salesman_id, "your_reference": order.code, "products": products, "notes": order.notes or "", "status": 0}
        response = _record(await api.post("estimates/insert", estimate), "estimates/insert")
    except MoloniError as exc:
        raise MoloniError(f"{exc} (salesman_id={salesman_id})") from exc
    return _entity_id(response, "document_id", "documentId", "id", endpoint="estimates/insert")





