"""Conexão OAuth do Moloni, restrita à sessão de plataforma."""
import secrets
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_platform_capability
from app.core.config import settings
from app.core.markets import PlatformPrincipal
from app.core.moloni_crypto import encrypt_token
from app.models.moloni import MoloniConnection, MoloniOAuthState, MoloniExportJob, MoloniTaxMapping
from app.models.order import Order
from app.services.moloni_jobs import enqueue_finalized_eu_order

router = APIRouter(prefix="/api/v1/integrations/moloni", tags=["moloni"])
_ADMIN = Depends(require_platform_capability("platform_admin"))

class ConnectRequest(BaseModel):
    company_id: int = Field(gt=0)


class TaxMappingInput(BaseModel):
    vat_rate: Decimal = Field(ge=0, le=100)
    moloni_tax_id: int = Field(gt=0)


class TaxMappingsRequest(BaseModel):
    mappings: list[TaxMappingInput] = Field(min_length=1, max_length=30)

def _require_oauth_settings() -> None:
    if not all((settings.MOLONI_CLIENT_ID, settings.MOLONI_CLIENT_SECRET, settings.MOLONI_REDIRECT_URI)):
        raise HTTPException(503, "Integração Moloni ainda não foi configurada no ambiente.")

@router.post("/connect", status_code=201)
async def connect(payload: ConnectRequest, db: AsyncSession = Depends(get_db_session), platform: PlatformPrincipal = _ADMIN):
    """Cria estado único e devolve a URL de consentimento do Moloni."""
    _require_oauth_settings()
    state = secrets.token_urlsafe(32)
    db.add(MoloniOAuthState(state=state, company_id=payload.company_id, user_id=platform.user.id, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
    await db.commit()
    return {"authorization_url": "https://api.moloni.pt/v1/authorize/?" + urlencode({"response_type": "code", "client_id": settings.MOLONI_CLIENT_ID, "redirect_uri": settings.MOLONI_REDIRECT_URI, "state": state}), "expires_in_seconds": 600}

@router.get("/callback")
async def callback(code: str = Query(min_length=1), state: str = Query(min_length=20), db: AsyncSession = Depends(get_db_session)):
    """Callback público: a autorização vem do estado opaco, de uso único."""
    row = (await db.execute(select(MoloniOAuthState).where(MoloniOAuthState.state == state).with_for_update())).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not row or row.used_at or row.expires_at <= now:
        raise HTTPException(400, "Autorização Moloni inválida ou expirada.")
    _require_oauth_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.MOLONI_TIMEOUT_SECONDS) as client:
            response = await client.get(settings.MOLONI_API_BASE_URL.rstrip("/") + "/grant/", params={"grant_type": "authorization_code", "client_id": settings.MOLONI_CLIENT_ID, "client_secret": settings.MOLONI_CLIENT_SECRET, "redirect_uri": settings.MOLONI_REDIRECT_URI, "code": code})
        response.raise_for_status(); token = response.json()
        access, refresh = token["access_token"], token["refresh_token"]
    except (httpx.HTTPError, KeyError, TypeError):
        raise HTTPException(502, "Moloni recusou a autorização. Tente conectar novamente.")
    connection = (await db.execute(select(MoloniConnection).where(MoloniConnection.company_id == row.company_id).with_for_update())).scalar_one_or_none()
    expiry = now + timedelta(seconds=int(token.get("expires_in", 0) or 0))
    if connection:
        connection.access_token_ciphertext, connection.refresh_token_ciphertext, connection.token_expires_at, connection.is_active = encrypt_token(access), encrypt_token(refresh), expiry, True
    else:
        db.add(MoloniConnection(company_id=row.company_id, access_token_ciphertext=encrypt_token(access), refresh_token_ciphertext=encrypt_token(refresh), token_expires_at=expiry, connected_by_user_id=row.user_id))
    row.used_at = now
    await db.commit()
    return {"connected": True, "company_id": row.company_id, "message": "Moloni conectado. Configure o mapeamento fiscal antes de liberar o worker."}

@router.get("/status")
async def status(db: AsyncSession = Depends(get_db_session), _: PlatformPrincipal = _ADMIN):
    connection = (await db.execute(select(MoloniConnection).order_by(MoloniConnection.created_at.desc()).limit(1))).scalar_one_or_none()
    jobs = (await db.execute(select(MoloniExportJob.status).order_by(MoloniExportJob.created_at.desc()).limit(50))).scalars().all()
    counts = {key: jobs.count(key) for key in ("pending", "processing", "delivered", "dead_letter")}
    mappings = []
    if connection:
        mappings = list((await db.execute(
            select(MoloniTaxMapping.vat_rate, MoloniTaxMapping.moloni_tax_id)
            .where(MoloniTaxMapping.connection_id == connection.id)
            .order_by(MoloniTaxMapping.vat_rate)
        )).all())
    return {"configured": bool(connection), "active": bool(connection and connection.is_active), "company_id": connection.company_id if connection else None, "jobs": counts, "tax_mappings": [{"vat_rate": str(rate), "moloni_tax_id": tax_id} for rate, tax_id in mappings]}


@router.put("/tax-mappings")
async def save_tax_mappings(payload: TaxMappingsRequest, db: AsyncSession = Depends(get_db_session), _: PlatformPrincipal = _ADMIN):
    """Registra a correspondencia explicita IVA Ilya para imposto Moloni."""
    connection = (await db.execute(select(MoloniConnection).where(MoloniConnection.is_active.is_(True)).limit(1))).scalar_one_or_none()
    if not connection:
        raise HTTPException(422, "Conecte o Moloni antes de configurar impostos.")
    rates = [item.vat_rate for item in payload.mappings]
    if len(set(rates)) != len(rates):
        raise HTTPException(422, "Cada aliquota de IVA deve aparecer uma unica vez.")
    existing = {row.vat_rate: row for row in (await db.execute(
        select(MoloniTaxMapping).where(MoloniTaxMapping.connection_id == connection.id)
    )).scalars()}
    for item in payload.mappings:
        row = existing.get(item.vat_rate)
        if row:
            row.moloni_tax_id = item.moloni_tax_id
        else:
            db.add(MoloniTaxMapping(connection_id=connection.id, vat_rate=item.vat_rate, moloni_tax_id=item.moloni_tax_id))
    await db.commit()
    return {"saved": len(payload.mappings)}

@router.post("/orders/{order_id}/enqueue", status_code=202)
async def enqueue_existing(order_id: str, db: AsyncSession = Depends(get_db_session), _: PlatformPrincipal = _ADMIN):
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order or order.market_code != "EU" or not order.is_finalized:
        raise HTTPException(422, "Somente pedido EU finalizado pode ser exportado.")
    await enqueue_finalized_eu_order(db, order.id)
    await db.commit()
    return {"queued": True, "order_id": str(order.id)}
