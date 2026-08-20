import csv
import io
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_roles
from app.core.uploads import read_upload_limited
from app.models.market import Market, PriceList, ProductMarket, ProductPrice
from app.models.product import Product
from app.models.product_group import ProductGroup
from app.models.product_type import ProductType
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/markets", tags=["markets"])
_ADMIN = Depends(require_roles(UserRole.admin))
_IMPORT = Depends(require_roles(UserRole.admin, UserRole.cadastros))
_EU_LISTS = ("lojista", "corporativo", "pvp")


def _decimal_csv(value: str) -> Decimal:
    normalized = value.strip().replace("€", "").replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    return Decimal(normalized)


@router.get("")
async def list_markets(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    return (await db.execute(select(Market).order_by(Market.code))).scalars().all()


@router.post("/EU/activate")
async def activate_europe(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    available = (await db.execute(select(func.count()).select_from(ProductMarket).where(
        ProductMarket.market_code == "EU", ProductMarket.is_available.is_(True)
    ))).scalar_one()
    priced = (await db.execute(
        select(ProductPrice.product_id, func.count(ProductPrice.price_list_id))
        .join(PriceList, PriceList.id == ProductPrice.price_list_id)
        .join(ProductMarket, ProductMarket.product_id == ProductPrice.product_id)
        .where(PriceList.market_code == "EU", ProductMarket.market_code == "EU", ProductMarket.is_available.is_(True))
        .group_by(ProductPrice.product_id)
        .having(func.count(ProductPrice.price_list_id) == 3)
    )).all()
    if available == 0 or len(priced) != available:
        raise HTTPException(409, "Europa não pode ser ativada: há SKU disponível sem as três listas de preço.")
    market = await db.get(Market, "EU")
    market.is_enabled = True
    await db.commit()
    return {"market": "EU", "enabled": True, "products": available, "requires_env_flag": True}


@router.post("/EU/deactivate")
async def deactivate_europe(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    market = await db.get(Market, "EU")
    market.is_enabled = False
    await db.commit()
    return {"market": "EU", "enabled": False}


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

    Colunas: product_code, lojista, corporativo, pvp e opcionalmente vat_rate e
    is_available. Sem vat_rate, copia a taxa já configurada no grupo do produto
    no Ilya. A moeda não é aceita do arquivo: as listas EU são sempre EUR.
    """
    raw = await read_upload_limited(file, 10 * 1024 * 1024, max_size_label="10MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV deve estar em UTF-8.")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    required = {"product_code", *_EU_LISTS}
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
            vat_raw = (row.get("vat_rate") or "").strip()
            vat = _decimal_csv(vat_raw) if vat_raw else None
            if any(value < 0 for value in prices.values()) or (vat is not None and (vat < 0 or vat > 100)):
                raise ValueError
        except (InvalidOperation, ValueError):
            errors.append(f"Linha {line}: preço negativo/inválido ou IVA fora de 0–100.")
            continue
        available = (row.get("is_available") or "true").strip().lower() in {"1", "true", "sim", "yes"}
        parsed.append({"sku": sku, "prices": prices, "vat": vat, "available": available})
    products = (await db.execute(
        select(Product.id, Product.product_code, ProductGroup.ipi)
        .outerjoin(ProductType, ProductType.name == Product.type)
        .outerjoin(ProductGroup, ProductGroup.id == ProductType.group_id)
        .where(Product.product_code.in_(seen))
    )).all()
    product_ids = {sku: product_id for product_id, sku, _ in products}
    inherited_tax = {sku: (ipi if ipi is not None else Decimal("0")) for _, sku, ipi in products}
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
        vat_rate = row["vat"] if row["vat"] is not None else inherited_tax[row["sku"]]
        await db.execute(pg_insert(ProductMarket).values(
            product_id=product_id, market_code="EU", is_available=row["available"], vat_rate=vat_rate
        ).on_conflict_do_update(
            index_elements=[ProductMarket.product_id, ProductMarket.market_code],
            set_={"is_available": row["available"], "vat_rate": vat_rate},
        ))
        for code, amount in row["prices"].items():
            await db.execute(pg_insert(ProductPrice).values(
                product_id=product_id, price_list_id=list_ids[code], amount=amount
            ).on_conflict_do_update(
                index_elements=[ProductPrice.product_id, ProductPrice.price_list_id],
                set_={"amount": amount},
            ))
    await db.commit()
    inherited_count = sum(row["vat"] is None for row in parsed)
    return {
        "market": "EU", "currency": "EUR", "imported": len(parsed), "errors": [],
        "tax_rates_inherited_from_ilya": inherited_count,
    }
