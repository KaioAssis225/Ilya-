"""Fila transacional do PDF e dos e-mails de pedido."""
import uuid

from email_validator import EmailNotValidError, validate_email
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.client import Client
from app.models.optional_category import OptionalCategory
from app.models.order import Order, OrderItem
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.models.product import Product, ProductSetComponent
from app.models.representative import Representative
from app.schemas.client import ClientRead
from app.schemas.order import OrderRead
from app.schemas.product import ProductSetComponentRead
from app.schemas.representative import RepresentativeRead


def normalize_recipient(value: str | None) -> tuple[str | None, str | None]:
    """Normaliza sem consulta DNS e devolve somente códigos de erro estáveis."""
    if value is None or not value.strip():
        return None, "missing_recipient"
    try:
        normalized = validate_email(
            value.strip(), check_deliverability=False
        ).normalized.lower()
    except EmailNotValidError:
        return None, "invalid_recipient"
    return normalized, None


def recipient_is_allowed(value: str | None, allowlist: str | None = None) -> bool:
    if not value:
        return False
    address = value.strip().lower()
    entries = {
        entry.strip().lower()
        for entry in (settings.ORDER_EMAIL_TEST_ALLOWLIST if allowlist is None else allowlist).split(",")
        if entry.strip()
    }
    if address in entries:
        return True
    _, separator, domain = address.rpartition("@")
    return bool(separator) and f"@{domain}" in entries


def _read_schema(schema, row, *, email: str | None = None) -> dict:
    values = {
        name: getattr(row, name)
        for name in schema.model_fields
        if hasattr(row, name)
    }
    if email is not None or getattr(row, "email", None) is not None:
        values["email"] = email
    return jsonable_encoder(schema.model_validate(values))


async def _snapshot_v2(
    db: AsyncSession,
    order: Order,
    client: Client,
    representative: Representative | None,
    client_email: str | None,
    representative_email: str | None,
) -> dict:
    """Congela somente linhas locais do banco no formato v2.

    Preços continuam vindo exclusivamente dos itens do pedido, nunca do
    catálogo atual. As referências de foto ficam em ``photo_path`` e são
    convertidas para data URL pelo renderer no momento de gerar o PDF.
    """
    loaded_order = (
        await db.execute(
            select(Order)
            .where(Order.id == order.id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.optional_choices),
            )
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    product_codes = sorted({item.product_code for item in loaded_order.items})
    products = (
        (
            await db.execute(
                select(Product)
                .where(
                    Product.market_code == order.market_code,
                    Product.product_code.in_(product_codes),
                )
                .options(
                    selectinload(Product.components).selectinload(
                        ProductSetComponent.optionals
                    ),
                )
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    product_by_code = {row.product_code: row for row in products}
    categories = (
        await db.execute(
            select(OptionalCategory.code, OptionalCategory.name)
            .where(OptionalCategory.market_code == order.market_code)
            .order_by(OptionalCategory.code)
        )
    ).all()
    category_labels = {row.code: row.name for row in categories}

    products_snapshot = []
    for code in product_codes:
        product = product_by_code.get(code)
        components = (
            [
                jsonable_encoder(ProductSetComponentRead.model_validate(component))
                for component in product.components
            ]
            if product is not None
            else []
        )
        products_snapshot.append(
            {
                "product_code": code,
                "type": product.type if product is not None else None,
                "is_set": bool(product.is_set) if product is not None else False,
                "components": components,
                "photo_path": product.photo_path if product is not None else None,
                "thumbnail_url": None,
                "photo_url": None,
            }
        )

    return {
        "schema_version": 2,
        "locale": order.locale,
        "order": jsonable_encoder(
            OrderRead.model_validate(loaded_order), exclude={"history"}
        ),
        "client": _read_schema(ClientRead, client, email=client_email),
        "representative": (
            _read_schema(RepresentativeRead, representative, email=representative_email)
            if representative
            else None
        ),
        "products": products_snapshot,
        "category_labels": category_labels,
    }


async def enqueue_order_emails(
    db: AsyncSession,
    order: Order,
    *,
    requested_by_user_id: uuid.UUID,
) -> None:
    """Cria documento e entregas sem confirmar a transação do chamador."""
    if settings.ORDER_EMAIL_MODE == "off":
        return

    client = (
        await db.execute(
            select(Client).where(
                Client.id == order.client_id,
                Client.market_code == order.market_code,
            )
        )
    ).scalar_one()
    representative = None
    if order.rep_id is not None:
        representative = (
            await db.execute(
                select(Representative).where(
                    Representative.id == order.rep_id,
                    Representative.market_code == order.market_code,
                )
            )
        ).scalar_one_or_none()

    client_email, client_error = normalize_recipient(client.email)
    representative_email, representative_error = normalize_recipient(
        representative.email if representative else None
    )
    snapshot = await _snapshot_v2(
        db,
        order,
        client,
        representative,
        client_email,
        representative_email,
    )
    document_id = uuid.uuid4()
    created_document_id = (
        await db.execute(
            insert(OrderEmailDocument)
            .values(
                id=document_id,
                order_id=order.id,
                market_code=order.market_code,
                version=order.document_version,
                locale=order.locale,
                status="pending",
                attempts=0,
                snapshot=snapshot,
            )
            .on_conflict_do_nothing(
                constraint="uq_order_email_documents_order_version"
            )
            .returning(OrderEmailDocument.id)
        )
    ).scalar_one_or_none()
    if created_document_id is None:
        return

    recipients = [
        {
            "roles": ["client"],
            "email": client_email,
            "name": client.name,
            "error": client_error,
        }
    ]
    if representative is not None:
        if client_email and representative_email == client_email:
            recipients[0]["roles"].append("representative")
        else:
            recipients.append(
                {
                    "roles": ["representative"],
                    "email": representative_email,
                    "name": representative.name,
                    "error": representative_error,
                }
            )

    for recipient in recipients:
        delivery_id = uuid.uuid4()
        blocked = recipient["error"] is not None
        db.add(
            OrderEmailDelivery(
                id=delivery_id,
                order_id=order.id,
                market_code=order.market_code,
                document_id=created_document_id,
                recipient_roles=recipient["roles"],
                recipient_email=recipient["email"],
                recipient_name=recipient["name"],
                origin="finalization",
                requested_by_user_id=requested_by_user_id,
                status="blocked" if blocked else "pending",
                attempts=0,
                idempotency_key=f"order-email/{delivery_id}",
                last_error=recipient["error"],
            )
        )
    await db.flush()
