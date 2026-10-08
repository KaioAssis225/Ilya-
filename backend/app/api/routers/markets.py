import csv
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, not_, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_principal,
    get_db_session,
    get_platform_principal,
    require_platform_capability,
)
from app.core.config import settings
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.core.uploads import copy_upload_to_market, read_upload_limited
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
from app.models.product_group import ProductGroup
from app.models.product_type import ProductType
from app.api.routers.product_groups import product_type_key
from app.models.optional_color import OptionalColor
from app.models.client import Client
from app.models.representative import Representative

router = APIRouter(prefix="/api/v1/markets", tags=["markets"])
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
    _: PlatformPrincipal = Depends(get_platform_principal),
):
    return (await db.execute(select(Market).order_by(Market.code))).scalars().all()


@router.post("/EU/activate")
async def activate_europe(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("activate_market")),
):
    launch_country = settings.EU_LAUNCH_COUNTRY.strip().upper()
    out_of_scope_people = (await db.execute(
        select(func.count()).select_from(Client).where(
            Client.market_code == "EU",
            or_(Client.country.is_(None), func.upper(Client.country) != launch_country),
        )
    )).scalar_one() + (await db.execute(
        select(func.count()).select_from(Representative).where(
            Representative.market_code == "EU",
            or_(Representative.country.is_(None), func.upper(Representative.country) != launch_country),
            Representative.relationship_ended_at.is_(None),
        )
    )).scalar_one()
    if out_of_scope_people:
        raise HTTPException(
            409,
            f"Europa não pode ser ativada: a primeira liberação aceita somente o país {launch_country}.",
        )
    invalid_dimensions = (await db.execute(text(r"""
        SELECT EXISTS (
            SELECT 1
            FROM products p
            JOIN product_markets pm
              ON pm.product_id = p.id
             AND pm.market_code = 'EU'
             AND pm.is_available = true
            LEFT JOIN product_types pt
              ON pt.market_code = 'EU' AND pt.name = p.type
            LEFT JOIN catalogs c
              ON c.id = p.catalog_id AND c.market_code = 'EU'
            WHERE p.market_code = 'EU'
              AND (
                (pt.id IS NULL AND p.type <> 'Outro')
                OR (p.catalog_id IS NOT NULL AND c.id IS NULL)
                OR EXISTS (
                    SELECT 1
                    FROM product_optionals po
                    JOIN optionals o ON o.id = po.optional_id
                    WHERE po.product_id = p.id AND o.market_code <> 'EU'
                )
                OR EXISTS (
                    SELECT 1
                    FROM product_set_components component
                    JOIN product_set_component_optionals link
                      ON link.component_id = component.id
                    JOIN optionals o ON o.id = link.optional_id
                    WHERE component.set_id = p.id AND o.market_code <> 'EU'
                )
                OR EXISTS (
                    SELECT 1
                    FROM regexp_split_to_table(
                        coalesce(p.all_optionals_categories, ''), '\\s*,\\s*'
                    ) AS category_code
                    WHERE category_code <> ''
                      AND NOT EXISTS (
                          SELECT 1 FROM optional_categories oc
                          WHERE oc.market_code = 'EU' AND oc.code = category_code
                      )
                )
              )
        )
    """))).scalar_one()
    if invalid_dimensions:
        raise HTTPException(
            409,
            "Europa não pode ser ativada: catálogo, tipo ou opcionais de produto não estão isolados no mercado EU.",
        )
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
    # IVA sem aprovação humana não fatura. A ativação só aceita taxas que
    # passaram pelo fluxo nominal de aprovação fiscal do mercado EU.
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
    if available == 0:
        raise HTTPException(409, "Europa não pode ser ativada sem ao menos um SKU disponível.")
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


# Referência que ainda não mora no bucket europeu. Produtos e opcionais EU
# copiados do catálogo BR nascem apontando para a foto brasileira; esta rota
# leva cada arquivo para o bucket do EU e troca a referência.
_NOT_YET_EU_PHOTO = "object://eu-%"


@router.post("/EU/media/sync")
async def sync_europe_media(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Copia para o bucket europeu as fotos que produtos e opcionais EU ainda
    emprestam do catálogo brasileiro.

    Lote pequeno por chamada, para caber no tempo de uma requisição; quem chama
    repete até `remaining` chegar a zero. Cada item é gravado sozinho, então uma
    falha no meio não desfaz o que já foi copiado, e repetir é seguro: o que já
    está no bucket europeu não volta a ser selecionado. A origem nunca é
    apagada -- ela segue sendo a foto do produto brasileiro.
    """
    if not settings.eu_object_storage_configured():
        raise HTTPException(409, "Bucket de fotos do mercado europeu não configurado.")

    copied = 0
    failed: list[dict] = []
    for kind, model, code_column in (
        ("products", Product, Product.product_code),
        ("optionals", OptionalColor, OptionalColor.color_name),
    ):
        budget = limit - copied - len(failed)
        if budget <= 0:
            break
        rows = (await db.execute(
            select(model)
            .where(
                model.market_code == "EU",
                model.photo_path.is_not(None),
                not_(model.photo_path.like(_NOT_YET_EU_PHOTO)),
            )
            .order_by(code_column)
            .limit(budget)
            .execution_options(skip_market_scope=True)
        )).scalars().all()
        for row in rows:
            label = getattr(row, "product_code", None) or getattr(row, "color_name", "")
            try:
                new_path = await copy_upload_to_market(row.photo_path, kind=kind)
            except Exception as exc:  # um arquivo ruim não interrompe o lote
                failed.append({
                    "kind": kind,
                    "id": str(row.id),
                    "code": label,
                    "error": type(exc).__name__,
                })
                continue
            row.photo_path = new_path
            await db.commit()
            copied += 1

    remaining = 0
    for model in (Product, OptionalColor):
        remaining += (await db.execute(
            select(func.count()).select_from(model)
            .where(
                model.market_code == "EU",
                model.photo_path.is_not(None),
                not_(model.photo_path.like(_NOT_YET_EU_PHOTO)),
            )
            .execution_options(skip_market_scope=True)
        )).scalar_one()
    return {"copied": copied, "failed": failed, "remaining": remaining}


@router.put("/EU/products/{product_id}/vat")
async def decide_europe_vat(
    product_id: uuid.UUID,
    body: VatDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Registra uma decisão fiscal individual (sem inferência). A aprovação em
    lote existe só pelo grupo EU — ver approve_europe_group_vat."""
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
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
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
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Importação atômica sobre produtos EU já cadastrados manualmente.

    Colunas: product_code, lojista, corporativo, pvp, vat_rate e opcionalmente
    is_available, description_pt_pt e description_en. O vat_rate é obrigatório e
    explícito por linha (inclusive 0) — não há herança do IPI do grupo do Ilya.
    A importação nunca cria ou copia um produto BR. Toda taxa importada nasce
    `pending` e limpa qualquer aprovação anterior. A
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
        .where(
            Product.market_code == "EU",
            Product.product_code.in_(seen),
        )
        .execution_options(skip_market_scope=True)
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


# ── IVA em lote pelo grupo (Portugal) ────────────────────────────────────────
# Decisão de 08/10/2026: além da decisão individual acima, quem tem permissão
# fiscal no vínculo EU pode aplicar e aprovar uma taxa em todos os produtos dos
# subgrupos de um grupo EU (botão Editar do grupo). Cada produto continua
# registrando quem aprovou e quando; o pedido segue lendo só product_markets.


class GroupVatRequest(BaseModel):
    vat_rate: Decimal = Field(ge=0, le=100, decimal_places=2)


@router.put("/EU/groups/{group_id}/vat")
async def approve_europe_group_vat(
    group_id: uuid.UUID,
    body: GroupVatRequest,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Aplica e aprova o IVA em todos os produtos disponíveis do grupo EU."""
    if principal.code != "EU" or not principal.access or not principal.access.can_approve_tax:
        raise HTTPException(403, "Permissão fiscal não concedida neste mercado.")
    group = await db.get(ProductGroup, group_id)
    if group is None or group.market_code != "EU":
        raise HTTPException(404, "Grupo não encontrado.")
    type_keys = select(product_type_key(ProductType.name)).where(
        ProductType.group_id == group_id,
        ProductType.market_code == "EU",
    )
    product_ids = select(Product.id).where(
        Product.market_code == "EU",
        Product.is_active.is_(True),
        product_type_key(Product.type).in_(type_keys),
    )
    result = await db.execute(
        update(ProductMarket)
        .where(
            ProductMarket.market_code == "EU",
            ProductMarket.is_available.is_(True),
            ProductMarket.product_id.in_(product_ids),
        )
        .values(
            vat_rate=body.vat_rate,
            vat_status=VAT_APPROVED,
            approved_by_user_id=principal.user.id,
            approved_at=datetime.now(timezone.utc),
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {"group_id": group_id, "vat_rate": body.vat_rate, "approved_products": result.rowcount}
