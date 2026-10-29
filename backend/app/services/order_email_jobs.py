"""Fila transacional do PDF e dos e-mails de pedido."""
import uuid

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.client import Client
from app.models.order import Order, OrderItem
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.models.product import Product
from app.models.representative import Representative
from app.schemas.client import ClientRead
from app.schemas.order import OrderRead
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
    return schema.model_validate(values).model_dump(mode="json")


async def _snapshot_v1(
    db: AsyncSession,
    order: Order,
    client: Client,
    representative: Representative | None,
    client_email: str | None,
    representative_email: str | None,
) -> dict:
    """Congela somente linhas locais do banco.

    A F3 poderá criar ``schema_version=2`` para copiar fotos e acrescentar os
    campos exigidos pelo renderer. Preços continuam vindo exclusivamente dos
    itens do pedido, nunca do catálogo atual.
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
        await db.execute(
            select(Product.product_code, Product.photo_path).where(
                Product.market_code == order.market_code,
                Product.product_code.in_(product_codes),
            )
        )
    ).all()
    photo_by_code = {row.product_code: row.photo_path for row in products}
    return {
        "schema_version": 1,
        "locale": order.locale,
        "order": OrderRead.model_validate(loaded_order).model_dump(
            mode="json", exclude={"history"}
        ),
        "client": _read_schema(ClientRead, client, email=client_email),
        "representative": (
            _read_schema(RepresentativeRead, representative, email=representative_email)
            if representative
            else None
        ),
        "products": [
            {"product_code": code, "photo_path": photo_by_code.get(code)}
            for code in product_codes
        ],
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
    snapshot = await _snapshot_v1(
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
