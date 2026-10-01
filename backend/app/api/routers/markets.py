import csv
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_principal,
    get_db_session,
    get_platform_principal,
    require_platform_capability,
    require_roles,
)
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.core.uploads import read_upload_limited
from app.models.market import (
    Market,
    PriceList,
    ProductMarket,
    ProductPrice,
    UserMarket,
    VAT_APPROVED,
    VAT_PENDING,
    VAT_REJECTED,
    VAT_SOURCE_IMPORT,
)
from app.models.product import Product
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/markets", tags=["markets"])
_ADMIN = Depends(require_roles(UserRole.admin))
_IMPORT = Depends(require_roles(UserRole.admin, UserRole.cadastros))
_EU_LISTS = ("lojista", "corporativo", "pvp")


class VatDecisionRequest(BaseModel):
    status: Literal["pending", "approved", "rejected"]
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)


async def _apply_vat_decision(
    db: AsyncSession,
    product_id: uuid.UUID,
    body: VatDecisionRequest,
    approver_user_id: uuid.UUID,
) -> ProductMarket:
    product_market = await db.get(ProductMarket, (product_id, "EU"))
    eu_product = (await db.execute(select(Product.id).where(
        Product.id == product_id,
        Product.market_code == "EU",
    ))).scalar_one_or_none()
    if product_market is None or eu_product is None:
        raise HTTPException(404, "Produto não vinculado ao mercado EU.")
    if body.status == VAT_APPROVED:
        if body.vat_rate is None:
            raise HTTPException(422, "A aprovação exige uma taxa de IVA explícita.")
        product_market.vat_rate = body.vat_rate
        product_market.vat_status = VAT_APPROVED
        product_market.approved_by_user_id = approver_user_id
        product_market.approved_at = datetime.now(timezone.utc)
    else:
        if body.vat_rate is not None:
            product_market.vat_rate = body.vat_rate
        product_market.vat_status = body.status
        product_market.approved_by_user_id = None
        product_market.approved_at = None
    await db.commit()
    return product_market


def _vat_response(product_market: ProductMarket) -> dict:
    return {
        "product_id": product_market.product_id,
        "market": "EU",
        "vat_rate": product_market.vat_rate,
        "vat_status": product_market.vat_status,
        "approved_by_user_id": product_market.approved_by_user_id,
        "approved_at": product_market.approved_at,
    }


def _decimal_csv(value: str) -> Decimal:
    normalized = value.strip().replace("€", "").replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    return Decimal(normalized)


def _parse_required_vat(raw: str | None) -> Decimal:
    """IVA tem de vir explícito por linha; 0 é válido, vazio não.

    Diferente do IPI brasileiro, não há herança do grupo do produto: cada linha
    importada declara a própria taxa. Vazio ou fora de 0–100 levanta ValueError
    para a linha ser rejeitada (e, com ela, o lote inteiro).
    """
    value = (raw or "").strip()
    if not value:
        raise ValueError("IVA (vat_rate) obrigatório por linha.")
    vat = _decimal_csv(value)
    if vat < 0 or vat > 100:
        raise ValueError("IVA fora de 0–100.")
    return vat


@router.get("")
async def list_markets(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    return (await db.execute(select(Market).order_by(Market.code))).scalars().all()


@router.post("/EU/activate")
async def activate_europe(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("activate_market")),
):
    available = (await db.execute(
        select(func.count()).select_from(ProductMarket)
        .join(Product, Product.id == ProductMarket.product_id)
        .where(
            Product.market_code == "EU",
            ProductMarket.market_code == "EU",
            ProductMarket.is_available.is_(True),
        )
    )).scalar_one()
    priced = (await db.execute(
        select(ProductPrice.product_id, func.count(ProductPrice.price_list_id))
        .join(PriceList, PriceList.id == ProductPrice.price_list_id)
        .join(ProductMarket, ProductMarket.product_id == ProductPrice.product_id)
        .join(Product, Product.id == ProductMarket.product_id)
        .where(
            Product.market_code == "EU",
            PriceList.market_code == "EU",
            ProductMarket.market_code == "EU",
            ProductMarket.is_available.is_(True),
        )
        .group_by(ProductPrice.product_id)
        .having(func.count(ProductPrice.price_list_id) == 3)
    )).all()
    # IVA sem aprovação humana não fatura. Enquanto o fluxo de aprovação (RBAC
    # P2) não existe, nenhum SKU chega a `approved` e a Europa fica — de
    # propósito — não habilitável. Aprovação manual continua pendente.
    unapproved_vat = (await db.execute(
        select(func.count()).select_from(ProductMarket)
        .join(Product, Product.id == ProductMarket.product_id)
        .where(
            Product.market_code == "EU",
            ProductMarket.market_code == "EU",
            ProductMarket.is_available.is_(True),
            or_(ProductMarket.vat_status != VAT_APPROVED, ProductMarket.vat_rate.is_(None)),
        )
    )).scalar_one()
    if len(priced) != available:
        raise HTTPException(409, "Europa não pode ser ativada: há SKU disponível sem as três listas de preço.")
    if unapproved_vat:
        raise HTTPException(409, "Europa não pode ser ativada: há SKU disponível sem IVA aprovado.")
    market = await db.get(Market, "EU")
    market.is_enabled = True
    await db.commit()
    return {"market": "EU", "enabled": True, "products": available, "requires_env_flag": True}


@router.post("/EU/deactivate")
async def deactivate_europe(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("activate_market")),
):
    market = await db.get(Market, "EU")
    market.is_enabled = False
    await db.commit()
    return {"market": "EU", "enabled": False}


@router.put("/EU/products/{product_id}/vat")
async def decide_europe_vat(
    product_id: uuid.UUID,
    body: VatDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Registra uma decisão fiscal individual, sem inferência ou aprovação em lote."""
    if principal.code != "EU" or not principal.access or not principal.access.can_approve_tax:
        raise HTTPException(403, "Permissão fiscal não concedida neste mercado.")
    return _vat_response(await _apply_vat_decision(
        db, product_id, body, principal.user.id
    ))


@router.put("/EU/products/{product_id}/vat/platform")
async def decide_europe_vat_before_activation(
    product_id: uuid.UUID,
    body: VatDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
    platform: PlatformPrincipal = Depends(get_platform_principal),
):
    """Aprovação preparatória enquanto EU ainda está globalmente desabilitado."""
    access = await db.get(UserMarket, (platform.user.id, "EU"))
    if access is None or access.status != "active" or not access.can_approve_tax:
        raise HTTPException(403, "Permissão fiscal não concedida no mercado EU.")
    return _vat_response(await _apply_vat_decision(
        db, product_id, body, platform.user.id
    ))


@router.get("/price-comparison")
async def price_comparison(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    rows = (await db.execute(
        select(Product.product_code, PriceList.market_code, PriceList.code, PriceList.currency, ProductPrice.amount)
        .join(ProductPrice, ProductPrice.product_id == Product.id)
        .join(PriceList, PriceList.id == ProductPrice.price_list_id)
        .order_by(Product.product_code, PriceList.market_code, PriceList.code)
    )).all()
    result: dict[str, dict[str, dict[str, str]]] = {}
    for sku, market, code, currency, amount in rows:
        result.setdefault(sku, {}).setdefault(market, {})[code] = f"{amount:.2f} {currency}"
    return result


@router.post("/EU/import", status_code=status.HTTP_200_OK)
async def import_europe_catalog(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    _: User = _IMPORT,
):
    """Importação atômica do subconjunto europeu.

    Colunas: product_code, lojista, corporativo, pvp, vat_rate e opcionalmente
    is_available, description_pt_pt e description_en. O vat_rate é obrigatório e
    explícito por linha (inclusive 0) — não há herança do IPI do grupo do Ilya.
    Toda taxa importada nasce `pending` e limpa qualquer aprovação anterior. A
    moeda não é aceita do arquivo: as listas EU são sempre EUR.
    """
    raw = await read_upload_limited(file, 10 * 1024 * 1024, max_size_label="10MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV deve estar em UTF-8.")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    required = {"product_code", *_EU_LISTS, "vat_rate"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(422, f"Cabeçalho obrigatório: {';'.join(sorted(required))}.")
    parsed: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for line, row in enumerate(reader, start=2):
        sku = (row.get("product_code") or "").strip().upper()
        if not sku or sku in seen:
            errors.append(f"Linha {line}: SKU vazio ou duplicado ({sku or 'vazio'}).")
            continue
        seen.add(sku)
        try:
            prices = {code: _decimal_csv(row.get(code) or "") for code in _EU_LISTS}
            if any(value < 0 for value in prices.values()):
                raise ValueError("Preço negativo.")
            vat = _parse_required_vat(row.get("vat_rate"))
        except (InvalidOperation, ValueError):
            errors.append(f"Linha {line}: preço negativo/inválido ou vat_rate ausente/fora de 0–100.")
            continue
        available = (row.get("is_available") or "true").strip().lower() in {"1", "true", "sim", "yes"}
        parsed.append({
            "sku": sku,
            "prices": prices,
            "vat": vat,
            "available": available,
            "description_pt_pt": (row.get("description_pt_pt") or "").strip() or None,
            "description_en": (row.get("description_en") or "").strip() or None,
        })
    products = (await db.execute(
        select(Product.id, Product.product_code)
        .where(Product.product_code.in_(seen))
    )).all()
    product_ids = {sku: product_id for product_id, sku in products}
    missing = sorted(seen - set(product_ids))
    if missing:
        errors.append("SKUs inexistentes: " + ", ".join(missing[:50]))
    lists = (await db.execute(select(PriceList).where(PriceList.market_code == "EU"))).scalars().all()
    list_ids = {item.code: item.id for item in lists if item.currency == "EUR"}
    if set(list_ids) != set(_EU_LISTS):
        errors.append("As listas europeias Lojista, Corporativo e PVP em EUR não estão configuradas.")
    if errors:
        raise HTTPException(422, {"message": "Importação rejeitada; nenhum dado foi alterado.", "errors": errors[:100]})
    for row in parsed:
        product_id = product_ids[row["sku"]]
        # A taxa importada volta a `pending` e zera a aprovação anterior: uma
        # nova taxa nunca herda a chancela da anterior.
        vat_fields = {
            "vat_rate": row["vat"],
            "vat_status": VAT_PENDING,
            "vat_source": VAT_SOURCE_IMPORT,
            "approved_by_user_id": None,
            "approved_at": None,
        }
        await db.execute(pg_insert(ProductMarket).values(
            product_id=product_id, market_code="EU", is_available=row["available"],
            description_pt_pt=row["description_pt_pt"], description_en=row["description_en"],
            **vat_fields,
        ).on_conflict_do_update(
            index_elements=[ProductMarket.product_id, ProductMarket.market_code],
            set_={
                "is_available": row["available"],
                **vat_fields,
                **({"description_pt_pt": row["description_pt_pt"]} if row["description_pt_pt"] else {}),
                **({"description_en": row["description_en"]} if row["description_en"] else {}),
            },
        ))
        for code, amount in row["prices"].items():
            await db.execute(pg_insert(ProductPrice).values(
                product_id=product_id, price_list_id=list_ids[code], amount=amount
            ).on_conflict_do_update(
                index_elements=[ProductPrice.product_id, ProductPrice.price_list_id],
                set_={"amount": amount},
            ))
    await db.commit()
    # Toda taxa importada entra pendente de aprovação manual (ainda sem fluxo
    # próprio — RBAC P2): a Europa só fatura/ativa depois que alguém aprovar.
    return {
        "market": "EU", "currency": "EUR", "imported": len(parsed), "errors": [],
        "pending_vat_approval": len(parsed),
    }
