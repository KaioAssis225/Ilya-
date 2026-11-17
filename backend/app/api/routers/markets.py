import csv
import io
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, not_, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_principal,
    get_db_session,
    get_platform_principal,
    require_platform_capability,
)
from app.core import media_orphans
from app.core.config import settings
from app.core.eu_vat import set_eu_vat_rate
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.core.uploads import copy_upload_to_market, read_upload_limited
from app.core.supplied_fabric import SUPPLIED_FABRIC_CATEGORY, round_money
from app.models.optional_application import ProductOptionalApplication
from app.models.optional_category import OptionalCategory
from app.models.market import (
    Market,
    MarketVatRateEvent,
    PriceList,
    ProductMarket,
    ProductPrice,
    ProductSuppliedFabric,
)
from app.models.product import Product, ProductPhoto
from app.models.optional_color import OptionalColor, product_optionals
from app.models.client import Client
from app.models.representative import Representative
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/markets", tags=["markets"])
_EU_LISTS = ("lojista", "corporativo", "pvp", "arquiteto")


def _decimal_csv(value: str) -> Decimal:
    normalized = value.strip().replace("€", "").replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    return Decimal(normalized)


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
    people_without_country = (await db.execute(
        select(func.count()).select_from(Client).where(
            Client.market_code == "EU",
            or_(Client.country.is_(None), func.trim(Client.country) == ""),
        )
    )).scalar_one() + (await db.execute(
        select(func.count()).select_from(Representative).where(
            Representative.market_code == "EU",
            or_(Representative.country.is_(None), func.trim(Representative.country) == ""),
            Representative.relationship_ended_at.is_(None),
        )
    )).scalar_one()
    if people_without_country:
        raise HTTPException(
            409,
            "Europa não pode ser ativada: há clientes ou representantes sem país informado.",
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
                    SELECT 1 FROM product_optional_applications application
                    JOIN optional_categories category ON category.id = application.category_id
                    WHERE application.product_id = p.id
                      AND (
                        category.market_code <> 'EU'
                        OR (application.component_id IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM product_set_components component
                            WHERE component.id = application.component_id AND component.set_id = p.id
                        ))
                        OR EXISTS (
                            SELECT 1 FROM optional_application_allowed allowed
                            JOIN optionals optional ON optional.id = allowed.optional_id
                            WHERE allowed.application_id = application.id
                              AND (optional.market_code <> 'EU' OR optional.category <> category.code)
                        )
                      )
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
            PriceList.code.in_(_EU_LISTS),
            ProductMarket.market_code == "EU",
            ProductMarket.is_available.is_(True),
        )
        .group_by(ProductPrice.product_id)
        .having(func.count(func.distinct(PriceList.code)) == len(_EU_LISTS))
    )).all()
    # O IVA é uma taxa única do mercado (não mais aprovação por SKU): a Europa
    # só abre com essa taxa configurada, para nunca faturar sem IVA em silêncio.
    vat_rate_configured = (await db.execute(
        select(Market.vat_rate).where(Market.code == "EU")
    )).scalar_one_or_none() is not None
    if available == 0:
        raise HTTPException(409, "Europa não pode ser ativada sem ao menos um SKU disponível.")
    if len(priced) != available:
        raise HTTPException(409, "Europa não pode ser ativada: há SKU disponível sem as três listas de preço.")
    if not vat_rate_configured:
        raise HTTPException(409, "Europa não pode ser ativada: a taxa de IVA do mercado não está configurada.")
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

    # Galeria: fotos extras (e a linha da principal) ainda emprestadas do BR.
    # `products.photo_path` é o espelho da principal e acompanha a linha dela.
    budget = limit - copied - len(failed)
    if budget > 0:
        gallery = (await db.execute(
            select(ProductPhoto, Product)
            .join(Product, Product.id == ProductPhoto.product_id)
            .where(
                Product.market_code == "EU",
                not_(ProductPhoto.photo_path.like(_NOT_YET_EU_PHOTO)),
            )
            .order_by(Product.product_code, ProductPhoto.position)
            .limit(budget)
            .execution_options(skip_market_scope=True)
        )).all()
        for photo, owner in gallery:
            if photo.is_primary and (owner.photo_path or "").startswith("object://eu-"):
                photo.photo_path = owner.photo_path  # principal já copiada acima
                await db.commit()
                continue
            try:
                new_path = await copy_upload_to_market(photo.photo_path, kind="products")
            except Exception as exc:  # um arquivo ruim não interrompe o lote
                failed.append({
                    "kind": "product_photos",
                    "id": str(photo.id),
                    "code": owner.product_code,
                    "error": type(exc).__name__,
                })
                continue
            photo.photo_path = new_path
            if photo.is_primary:
                owner.photo_path = new_path
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
    remaining += (await db.execute(
        select(func.count()).select_from(ProductPhoto)
        .join(Product, Product.id == ProductPhoto.product_id)
        .where(
            Product.market_code == "EU",
            not_(ProductPhoto.photo_path.like(_NOT_YET_EU_PHOTO)),
        )
        .execution_options(skip_market_scope=True)
    )).scalar_one()
    return {"copied": copied, "failed": failed, "remaining": remaining}


class OrphanPurgeRequest(BaseModel):
    confirm: str = Field(min_length=3, max_length=64)
    limit: int = Field(default=media_orphans.DEFAULT_BATCH, ge=1, le=media_orphans.MAX_BATCH)


class QuarantineRestoreRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    limit: int = Field(default=media_orphans.DEFAULT_BATCH, ge=1, le=media_orphans.MAX_BATCH)


class QuarantineDeleteRequest(QuarantineRestoreRequest):
    confirm: str = Field(min_length=3, max_length=64)


@router.get("/EU/media/orphans")
async def inventory_europe_orphan_photos(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Inventário (somente leitura) das fotos do bucket EU que nenhuma linha do
    banco referencia. Não altera nada. `confirm` identifica o conjunto listado."""
    return media_orphans.inventory_payload(await media_orphans.build_inventory(db))


@router.post("/EU/media/orphans/purge")
async def quarantine_europe_orphan_photos(
    body: OrphanPurgeRequest,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Move as órfãs listadas para a quarentena `eu-trash/<data>/` do mesmo bucket
    (nada é apagado). Exige o `confirm` do inventário atual; 409 se o conjunto
    mudou. Em lotes: repita com o `next_confirm` até `remaining` chegar a 0."""
    return await media_orphans.quarantine_orphans(
        db, confirm=body.confirm, limit=body.limit
    )


@router.get("/EU/media/orphans/quarantine")
async def list_europe_orphan_quarantine(
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Lotes em quarentena (data, quantidade, tamanho e se já podem ser apagados)."""
    return await media_orphans.quarantine_status()


@router.post("/EU/media/orphans/quarantine/restore")
async def restore_europe_orphan_quarantine(
    body: QuarantineRestoreRequest,
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Devolve um lote da quarentena ao lugar de origem (desfaz o purge)."""
    return await media_orphans.restore_quarantine(body.date, limit=body.limit)


@router.post("/EU/media/orphans/quarantine/delete")
async def delete_europe_orphan_quarantine(
    body: QuarantineDeleteRequest,
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Apaga DE VEZ um lote da quarentena com 7+ dias. Irreversível."""
    return await media_orphans.delete_quarantine(
        body.date, confirm=body.confirm, limit=body.limit
    )


# ── IVA único do mercado EU ──────────────────────────────────────────────────
# Portugal cobra o IVA uma vez, sobre o total do documento. A taxa é uma só,
# editada aqui (admin do mercado EU) ou na Plataforma (platform_admin), e cada
# mudança fica na trilha `market_vat_rate_events` (quem, quando, de → para).


class EuVatRateRequest(BaseModel):
    vat_rate: Decimal = Field(ge=0, le=100, decimal_places=2)


def _can_edit_eu_vat(principal: MarketPrincipal) -> bool:
    return principal.code == "EU" and principal.access is not None and principal.actor.role == UserRole.admin


async def _eu_vat_rate_view(db: AsyncSession, *, can_edit: bool) -> dict:
    rate = (await db.execute(select(Market.vat_rate).where(Market.code == "EU"))).scalar_one_or_none()
    view: dict = {"market": "EU", "vat_rate": rate, "can_edit": can_edit, "history": []}
    if can_edit:
        rows = (await db.execute(
            select(
                MarketVatRateEvent.created_at,
                MarketVatRateEvent.old_rate,
                MarketVatRateEvent.new_rate,
                User.full_name,
            )
            .outerjoin(User, User.id == MarketVatRateEvent.actor_user_id)
            .where(MarketVatRateEvent.market_code == "EU")
            .order_by(MarketVatRateEvent.created_at.desc())
            .limit(20)
        )).all()
        view["history"] = [
            {"changed_at": at, "old_rate": old, "new_rate": new, "changed_by": name}
            for at, old, new, name in rows
        ]
    return view


@router.get("/EU/vat-rate")
async def get_europe_vat_rate(
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Taxa única vigente. Qualquer usuário do mercado EU a lê (o orçamento mostra
    o IVA); só o admin vê o histórico e pode editar."""
    if principal.code != "EU":
        raise HTTPException(404, "Taxa de IVA disponível apenas no mercado europeu.")
    return await _eu_vat_rate_view(db, can_edit=_can_edit_eu_vat(principal))


@router.put("/EU/vat-rate")
async def update_europe_vat_rate(
    body: EuVatRateRequest,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Altera a taxa única. Só admin do mercado EU; o servidor valida 0–100 com
    duas casas. Documentos já finalizados guardam a taxa que usaram e não mudam."""
    if not _can_edit_eu_vat(principal):
        raise HTTPException(403, "Somente o administrador do mercado europeu altera a taxa de IVA.")
    await set_eu_vat_rate(db, body.vat_rate, principal.user.id)
    await db.commit()
    return await _eu_vat_rate_view(db, can_edit=True)


@router.get("/EU/vat-rate/platform")
async def get_europe_vat_rate_platform(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    return await _eu_vat_rate_view(db, can_edit=True)


@router.put("/EU/vat-rate/platform")
async def update_europe_vat_rate_platform(
    body: EuVatRateRequest,
    db: AsyncSession = Depends(get_db_session),
    platform: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Mesma taxa, editada pela Plataforma (inclusive com o mercado EU fechado)."""
    await set_eu_vat_rate(db, body.vat_rate, platform.user.id)
    await db.commit()
    return await _eu_vat_rate_view(db, can_edit=True)


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

    Colunas: product_code, lojista, corporativo, pvp, arquiteto e opcionalmente
    is_available, description_pt_pt e description_en. O IVA não vem do arquivo:
    é a taxa única do mercado (ver `/EU/vat-rate`); uma coluna `vat_rate`
    antiga no CSV é ignorada e o IVA por produto já gravado fica intacto.
    A importação nunca cria ou copia um produto BR. A
    moeda não é aceita do arquivo: as listas EU são sempre EUR.
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
            if any(value < 0 for value in prices.values()):
                raise ValueError("Preço negativo.")
        except (InvalidOperation, ValueError):
            errors.append(f"Linha {line}: preço negativo ou inválido.")
            continue
        available = (row.get("is_available") or "true").strip().lower() in {"1", "true", "sim", "yes"}
        parsed.append({
            "sku": sku,
            "prices": prices,
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
        errors.append(
            "As listas europeias Lojista, Corporativo, PVP e Arquiteto em EUR "
            "não estão configuradas."
        )
    if errors:
        raise HTTPException(422, {"message": "Importação rejeitada; nenhum dado foi alterado.", "errors": errors[:100]})
    for row in parsed:
        product_id = product_ids[row["sku"]]
        # O IVA por produto não é mais usado: a importação não o grava nem o apaga.
        await db.execute(pg_insert(ProductMarket).values(
            product_id=product_id, market_code="EU", is_available=row["available"],
            description_pt_pt=row["description_pt_pt"], description_en=row["description_en"],
        ).on_conflict_do_update(
            index_elements=[ProductMarket.product_id, ProductMarket.market_code],
            set_={
                "is_available": row["available"],
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
    return {"market": "EU", "currency": "EUR", "imported": len(parsed), "errors": []}


# ── TECIDO FORNECIDO (Portugal) ──────────────────────────────────────────────
# Preços "sem tecido" e metragem linear por produto EU, vindos da planilha da
# fábrica. Importação em CSV, só platform_admin, com simulação (dry-run) como
# padrão: nada é gravado até `dry_run=false`.

_FABRIC_HEADER_ALIASES = {
    "cod": "product_code", "codigo": "product_code", "código": "product_code",
    "product_code": "product_code",
    "pvp": "pvp", "lojista": "lojista", "arquiteto": "arquiteto", "corporativo": "corporativo",
    "mts tecido": "linear_meters", "mts_tecido": "linear_meters",
    "metros": "linear_meters", "linear_meters": "linear_meters",
}
_FABRIC_FIELDS = ("linear_meters", "price_lojista", "price_corporativo", "price_pvp", "price_arquiteto")


def _fabric_csv_rows(raw: bytes) -> tuple[list[dict], list[str]]:
    """Lê o CSV (`;` ou `,`) da planilha. Linhas inválidas viram erro; nada é gravado."""
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV deve estar em UTF-8.")
    first_line = content.splitlines()[0] if content.strip() else ""
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise HTTPException(422, "Arquivo vazio.")
    columns = {
        _FABRIC_HEADER_ALIASES[name.strip().lower()]: index
        for index, name in enumerate(header)
        if name.strip().lower() in _FABRIC_HEADER_ALIASES
    }
    needed = {"product_code", "pvp", "lojista", "arquiteto", "corporativo", "linear_meters"}
    if not needed.issubset(columns):
        raise HTTPException(
            422,
            "Cabeçalho obrigatório: COD, PVP, LOJISTA, ARQUITETO, CORPORATIVO, MTS TECIDO "
            f"(faltando: {', '.join(sorted(needed - set(columns)))}).",
        )
    rows: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line, values in enumerate(reader, start=2):
        if not any(value.strip() for value in values):
            continue

        def cell(name: str) -> str:
            index = columns[name]
            return values[index] if index < len(values) else ""

        sku = cell("product_code").strip().upper()
        if not sku or sku in seen:
            errors.append(f"Linha {line}: código vazio ou repetido ({sku or 'vazio'}).")
            continue
        seen.add(sku)
        try:
            prices = {code: round_money(_decimal_csv(cell(code))) for code in _EU_LISTS}
            meters = round_money(_decimal_csv(cell("linear_meters")))
            if any(value < 0 for value in prices.values()) or meters <= 0:
                raise ValueError("fora do limite")
        except (InvalidOperation, ValueError):
            errors.append(f"Linha {line} ({sku}): preço inválido/negativo ou metragem vazia/zero.")
            continue
        rows.append({
            "sku": sku,
            "linear_meters": meters,
            "price_lojista": prices["lojista"],
            "price_corporativo": prices["corporativo"],
            "price_pvp": prices["pvp"],
            "price_arquiteto": prices["arquiteto"],
        })
    return rows, errors


@router.post("/EU/supplied-fabric/import", status_code=status.HTTP_200_OK)
async def import_europe_supplied_fabric(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="true (padrão) só simula e lista o que mudaria."),
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    """Importa preços sem tecido e metragem (TECIDO FORNECIDO) de produtos EU.

    Colunas: COD, PVP, LOJISTA, ARQUITETO, CORPORATIVO, MTS TECIDO (os nomes da
    planilha). Os preços são arredondados no servidor para 2 casas, ROUND_HALF_UP.
    Linha malformada rejeita o arquivo inteiro. Código que não existe no EU não é
    erro: vai para `unknown_skus` e o resto é importado. Cria ou atualiza; nunca
    apaga um produto que ficou fora do arquivo.
    """
    raw = await read_upload_limited(file, 10 * 1024 * 1024, max_size_label="10MB")
    rows, errors = _fabric_csv_rows(raw)
    if errors:
        raise HTTPException(422, {"message": "Importação rejeitada; nenhum dado foi alterado.", "errors": errors[:100]})
    if not rows:
        raise HTTPException(422, "O arquivo não tem nenhuma linha de dados.")
    skus = {row["sku"] for row in rows}
    products = (await db.execute(
        select(Product.id, Product.product_code)
        .where(Product.market_code == "EU", Product.product_code.in_(skus))
        .execution_options(skip_market_scope=True)
    )).all()
    product_ids = {sku: product_id for product_id, sku in products}
    existing = {
        row.product_id: row
        for row in (await db.execute(
            select(ProductSuppliedFabric).where(ProductSuppliedFabric.product_id.in_(product_ids.values()))
        )).scalars()
    } if product_ids else {}
    with_application = set((await db.execute(
        select(ProductOptionalApplication.product_id)
        .join(OptionalCategory, OptionalCategory.id == ProductOptionalApplication.category_id)
        .where(
            ProductOptionalApplication.product_id.in_(product_ids.values()),
            OptionalCategory.code == SUPPLIED_FABRIC_CATEGORY,
            OptionalCategory.market_code == "EU",
        )
        .execution_options(skip_market_scope=True)
    )).scalars()) if product_ids else set()
    # Seletor antigo: a categoria liga ao produto por um opcional direto
    # (tabela `product_optionals` → `optionals.category`) ou por "permitir todos"
    # (coluna `products.all_optionals_categories`, lista separada por vírgula).
    with_legacy_selector: set[uuid.UUID] = set()
    if product_ids:
        with_legacy_selector |= set((await db.execute(
            select(product_optionals.c.product_id)
            .join(OptionalColor, OptionalColor.id == product_optionals.c.optional_id)
            .where(
                product_optionals.c.product_id.in_(product_ids.values()),
                OptionalColor.category == SUPPLIED_FABRIC_CATEGORY,
                OptionalColor.market_code == "EU",
            )
            .execution_options(skip_market_scope=True)
        )).scalars())
        for free_id, free_categories in (await db.execute(
            select(Product.id, Product.all_optionals_categories)
            .where(Product.id.in_(product_ids.values()), Product.all_optionals_categories.is_not(None))
            .execution_options(skip_market_scope=True)
        )).all():
            if SUPPLIED_FABRIC_CATEGORY in {part.strip() for part in (free_categories or "").split(",")}:
                with_legacy_selector.add(free_id)

    to_create: list[str] = []
    to_update: list[dict] = []
    unchanged: list[str] = []
    via_application: list[str] = []
    via_legacy_selector: list[str] = []
    without_category: list[str] = []
    for row in rows:
        product_id = product_ids.get(row["sku"])
        if product_id is None:
            continue
        # A opção aparece nos dois jeitos de configurar o produto; só some se
        # o produto não tem a categoria em nenhum deles.
        if product_id in with_application:
            via_application.append(row["sku"])
        elif product_id in with_legacy_selector:
            via_legacy_selector.append(row["sku"])
        else:
            without_category.append(row["sku"])
        current = existing.get(product_id)
        if current is None:
            to_create.append(row["sku"])
            continue
        changes = {
            field: {"from": str(getattr(current, field)), "to": str(row[field])}
            for field in _FABRIC_FIELDS if getattr(current, field) != row[field]
        }
        if changes:
            to_update.append({"sku": row["sku"], "changes": changes})
        else:
            unchanged.append(row["sku"])

    applied = 0
    if not dry_run:
        for row in rows:
            product_id = product_ids.get(row["sku"])
            if product_id is None:
                continue
            values = {field: row[field] for field in _FABRIC_FIELDS}
            await db.execute(pg_insert(ProductSuppliedFabric).values(
                product_id=product_id, **values,
            ).on_conflict_do_update(
                index_elements=[ProductSuppliedFabric.product_id],
                set_={**values, "updated_at": func.now()},
            ))
            applied += 1
        await db.commit()
    return {
        "market": "EU", "currency": "EUR", "dry_run": dry_run,
        "rows_in_file": len(rows),
        "to_create": sorted(to_create),
        "to_update": sorted(to_update, key=lambda item: item["sku"]),
        "unchanged": sorted(unchanged),
        "unknown_skus": sorted(skus - set(product_ids)),
        # Como a categoria TECIDOS_IBTW chega ao produto: aplicação, seletor
        # antigo, ou nenhum dos dois (a opção não aparece até configurar).
        "fabric_via_application": sorted(via_application),
        "fabric_via_legacy_selector": sorted(via_legacy_selector),
        "without_fabric_category": sorted(without_category),
        "applied": applied, "errors": [],
    }

