import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.market import BR_MARKET
from app.models.product_group import ProductGroup
from app.models.product_group_audit_event import ProductGroupAuditEvent
from app.models.product_type_fiscal_audit_event import ProductTypeFiscalAuditEvent
from app.models.product_fiscal_assignment_event import ProductFiscalAssignmentEvent
from app.models.product_type import ProductType


FiscalAction = Literal["created", "updated", "deleted"]
FiscalSource = Literal["api", "csv"]


async def group_ipi(db: AsyncSession, group_id: uuid.UUID | None) -> Decimal | None:
    if group_id is None:
        return None
    group = await db.get(ProductGroup, group_id)
    return group.ipi if group is not None else None


async def product_type_fiscal_snapshot(
    db: AsyncSession, type_name: str
) -> tuple[uuid.UUID | None, Decimal | None]:
    group_id = (await db.execute(
        select(ProductType.group_id).where(
            ProductType.market_code == BR_MARKET,
            ProductType.name == type_name,
        )
    )).scalar_one_or_none()
    return group_id, await group_ipi(db, group_id)


def record_product_group_event(
    db: AsyncSession,
    *,
    product_group_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    market_code: str,
    action: FiscalAction,
    source: FiscalSource,
    group_name: str,
    old_ipi: Decimal | None,
    new_ipi: Decimal | None,
) -> ProductGroupAuditEvent:
    """Inclui a evidência fiscal na mesma transação da mudança de IPI."""
    if market_code != BR_MARKET:
        raise ValueError("Eventos de IPI só podem ser registrados no mercado BR.")
    event = ProductGroupAuditEvent(
        product_group_id=product_group_id,
        actor_user_id=actor_user_id,
        market_code=market_code,
        action=action,
        source=source,
        group_name=group_name,
        old_ipi=old_ipi,
        new_ipi=new_ipi,
    )
    db.add(event)
    return event


def record_product_type_fiscal_event(
    db: AsyncSession,
    *,
    product_type_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    market_code: str,
    action: FiscalAction,
    source: FiscalSource,
    old_name: str | None,
    new_name: str | None,
    old_group_id: uuid.UUID | None,
    new_group_id: uuid.UUID | None,
    old_ipi: Decimal | None,
    new_ipi: Decimal | None,
) -> ProductTypeFiscalAuditEvent:
    if market_code != BR_MARKET:
        raise ValueError("Vínculos fiscais de tipos só podem ser registrados no BR.")
    event = ProductTypeFiscalAuditEvent(
        product_type_id=product_type_id,
        actor_user_id=actor_user_id,
        market_code=market_code,
        action=action,
        source=source,
        old_name=old_name,
        new_name=new_name,
        old_group_id=old_group_id,
        new_group_id=new_group_id,
        old_ipi=old_ipi,
        new_ipi=new_ipi,
    )
    db.add(event)
    return event


def record_product_fiscal_assignment(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    market_code: str,
    action: Literal["created", "updated"],
    source: FiscalSource,
    old_type: str | None,
    new_type: str,
    old_group_id: uuid.UUID | None,
    new_group_id: uuid.UUID | None,
    old_ipi: Decimal | None,
    new_ipi: Decimal | None,
) -> ProductFiscalAssignmentEvent:
    if market_code != BR_MARKET:
        raise ValueError("Classificação fiscal de produto só pode ser registrada no BR.")
    event = ProductFiscalAssignmentEvent(
        product_id=product_id,
        actor_user_id=actor_user_id,
        market_code=market_code,
        action=action,
        source=source,
        old_type=old_type,
        new_type=new_type,
        old_group_id=old_group_id,
        new_group_id=new_group_id,
        old_ipi=old_ipi,
        new_ipi=new_ipi,
    )
    db.add(event)
    return event
