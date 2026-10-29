"""Histórico, download privado e reenvio do PDF do pedido."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, require_order_access
from app.api.price_access import ensure_price_visible, visible_price_scope
from app.api.routers.orders import _can_operate_order, _get_order
from app.core.config import settings
from app.core.limiter import limiter
from app.core.order_documents import OrderDocumentStorageError, get_document
from app.models.client import Client
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.models.order_history import OrderHistory
from app.models.representative import Representative
from app.models.user import User, UserRole
from app.schemas.order_email import (
    OrderEmailDeliveryRead,
    OrderEmailDocumentRead,
    OrderEmailHistoryRead,
    OrderEmailResendRequest,
    OrderEmailTestSendRequest,
)
from app.services.order_email_jobs import (
    normalize_recipient,
    recipient_is_allowed,
)
from app.services.resend_client import sanitize_attachment_filename


router = APIRouter(prefix="/api/v1/orders", tags=["order-emails"])


def _delivery_read(delivery: OrderEmailDelivery) -> OrderEmailDeliveryRead:
    return OrderEmailDeliveryRead(
        id=delivery.id,
        document_id=delivery.document_id,
        recipient_roles=delivery.recipient_roles,
        recipient_email=delivery.recipient_email,
        status=delivery.status,
        attempts=delivery.attempts,
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
        first_attempt_at=delivery.first_attempt_at,
        next_attempt_at=delivery.next_attempt_at,
        accepted_at=delivery.accepted_at,
        delivered_at=delivery.delivered_at,
        last_event_type=delivery.last_event_type,
        last_event_at=delivery.last_event_at,
        last_error=delivery.last_error,
        origin=delivery.origin,
        resend_of_id=delivery.resend_of_id,
        can_resend=(
            settings.ORDER_EMAIL_MODE != "off"
            and delivery.status not in {"pending", "processing"}
        ),
    )


async def _latest_document(
    db: AsyncSession, order_id: uuid.UUID
) -> OrderEmailDocument | None:
    return (
        await db.execute(
            select(OrderEmailDocument)
            .where(OrderEmailDocument.order_id == order_id)
            .order_by(
                OrderEmailDocument.version.desc(),
                OrderEmailDocument.created_at.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("/{order_id}/emails", response_model=OrderEmailHistoryRead)
async def get_order_email_history(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_order_access),
):
    await _get_order(db, str(order_id), current_user)
    document = await _latest_document(db, order_id)
    if document is None:
        # Pedidos finalizados antes da ativação não ganham histórico retroativo.
        return OrderEmailHistoryRead(
            document=None,
            deliveries=[],
            test_send_available=False,
        )
    deliveries = (
        await db.execute(
            select(OrderEmailDelivery)
            .where(OrderEmailDelivery.order_id == order_id)
            .order_by(OrderEmailDelivery.created_at, OrderEmailDelivery.id)
        )
    ).scalars().all()
    return OrderEmailHistoryRead(
        document=OrderEmailDocumentRead.model_validate(
            document, from_attributes=True
        ),
        deliveries=[_delivery_read(row) for row in deliveries],
        test_send_available=(
            current_user.role == UserRole.admin
            and settings.ORDER_EMAIL_MODE == "test"
        ),
    )


@router.get("/{order_id}/email-document")
async def download_order_email_document(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_order_access),
):
    order = await _get_order(db, str(order_id), current_user)
    # O PDF contém preços: ver o pedido não basta quando a tabela comercial
    # deixou de fazer parte do escopo do usuário.
    ensure_price_visible(
        await visible_price_scope(db, current_user, order.market_code),
        order.price_list_code,
    )
    document = await _latest_document(db, order_id)
    if document is None or document.status != "ready" or not document.storage_key:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    try:
        content = await get_document(order.market_code, document.storage_key)
    except OrderDocumentStorageError:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    filename = sanitize_attachment_filename(order.code)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _current_recipient(
    db: AsyncSession,
    order,
    roles: list[str],
) -> tuple[list[str], str | None, str | None, str | None]:
    candidates = []
    if "client" in roles:
        client = (
            await db.execute(
                select(Client).where(
                    Client.id == order.client_id,
                    Client.market_code == order.market_code,
                )
            )
        ).scalar_one()
        email, error = normalize_recipient(client.email)
        candidates.append(("client", email, client.name, error))
    if "representative" in roles and order.rep_id is not None:
        representative = (
            await db.execute(
                select(Representative).where(
                    Representative.id == order.rep_id,
                    Representative.market_code == order.market_code,
                )
            )
        ).scalar_one_or_none()
        if representative is not None:
            email, error = normalize_recipient(representative.email)
            candidates.append(
                ("representative", email, representative.name, error)
            )
    if not candidates:
        return roles, None, None, "missing_recipient"
    selected = next((row for row in candidates if row[1] is not None), candidates[0])
    same_email_roles = [row[0] for row in candidates if row[1] == selected[1]]
    return same_email_roles, selected[1], selected[2], selected[3]


@router.post(
    "/{order_id}/emails/resend",
    response_model=OrderEmailDeliveryRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def resend_order_email(
    request: Request,
    response: Response,
    order_id: uuid.UUID,
    payload: OrderEmailResendRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    order = await _get_order(db, str(order_id), current_user)
    if not _can_operate_order(current_user):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if settings.ORDER_EMAIL_MODE == "off":
        raise HTTPException(status_code=409, detail="Envio de e-mail desativado.")
    original = (
        await db.execute(
            select(OrderEmailDelivery).where(
                OrderEmailDelivery.id == payload.delivery_id,
                OrderEmailDelivery.order_id == order.id,
            )
        )
    ).scalar_one_or_none()
    if original is None:
        raise HTTPException(status_code=404, detail="Entrega não encontrada.")

    roles = list(original.recipient_roles)
    email = original.recipient_email
    name = original.recipient_name
    error = None
    if payload.use_current_address or original.status == "blocked" or not email:
        roles, email, name, error = await _current_recipient(
            db, order, roles
        )
    else:
        email, error = normalize_recipient(email)
    if email:
        active = (
            await db.execute(
                select(OrderEmailDelivery.id).where(
                    OrderEmailDelivery.order_id == order.id,
                    OrderEmailDelivery.status.in_(("pending", "processing")),
                    func.lower(OrderEmailDelivery.recipient_email)
                    == email.lower(),
                )
            )
        ).scalar_one_or_none()
        if active is not None:
            raise HTTPException(
                status_code=409,
                detail="Já existe um envio pendente para este destinatário.",
            )
    delivery_id = uuid.uuid4()
    delivery = OrderEmailDelivery(
        id=delivery_id,
        order_id=order.id,
        market_code=order.market_code,
        document_id=original.document_id,
        recipient_roles=roles,
        recipient_email=email,
        recipient_name=name,
        origin="manual_resend",
        resend_of_id=original.id,
        requested_by_user_id=current_user.id,
        status="blocked" if error else "pending",
        attempts=0,
        idempotency_key=f"order-email/{delivery_id}",
        last_error=error,
    )
    db.add(delivery)
    db.add(
        OrderHistory(
            id=uuid.uuid4(),
            order_id=order.id,
            user_id=current_user.id,
            action="email_resent",
            details=f"delivery_id={delivery.id}",
        )
    )
    await db.commit()
    return _delivery_read(delivery)


@router.post(
    "/{order_id}/emails/test-send",
    response_model=OrderEmailDeliveryRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def test_send_order_email(
    request: Request,
    response: Response,
    order_id: uuid.UUID,
    payload: OrderEmailTestSendRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    order = await _get_order(db, str(order_id), current_user)
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if settings.ORDER_EMAIL_MODE != "test":
        raise HTTPException(
            status_code=409,
            detail="Envio de teste disponível apenas no modo de teste.",
        )
    document = await _latest_document(db, order.id)
    if document is None:
        raise HTTPException(
            status_code=409,
            detail="Pedido sem documento de e-mail.",
        )
    email, error = normalize_recipient(str(payload.recipient_email))
    if error or not email:
        raise HTTPException(status_code=422, detail="E-mail inválido.")
    active = (
        await db.execute(
            select(OrderEmailDelivery.id).where(
                OrderEmailDelivery.order_id == order.id,
                OrderEmailDelivery.status.in_(("pending", "processing")),
                func.lower(OrderEmailDelivery.recipient_email) == email.lower(),
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="Já existe um envio pendente para este destinatário.",
        )

    allowed = recipient_is_allowed(email)
    delivery_id = uuid.uuid4()
    delivery = OrderEmailDelivery(
        id=delivery_id,
        order_id=order.id,
        market_code=order.market_code,
        document_id=document.id,
        recipient_roles=[],
        recipient_email=email,
        recipient_name=None,
        origin="manual_resend",
        resend_of_id=None,
        requested_by_user_id=current_user.id,
        status="pending" if allowed else "skipped",
        attempts=0,
        idempotency_key=f"order-email/{delivery_id}",
        last_error=None if allowed else "not_in_allowlist",
    )
    db.add(delivery)
    db.add(
        OrderHistory(
            id=uuid.uuid4(),
            order_id=order.id,
            user_id=current_user.id,
            action="email_test_sent",
            details=f"delivery_id={delivery.id}",
        )
    )
    await db.commit()
    return _delivery_read(delivery)
