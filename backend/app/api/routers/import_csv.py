"""Importação massiva de cadastros via CSV (Bloco 63).

Todos os endpoints exigem papel admin. A validação é **tudo-ou-nada**: se qualquer
linha estiver fora do formato, NADA é importado (rollback) e o resumo devolve a
lista de erros para correção — evitando poluição de dados por importação parcial.
"""
import csv
import io
import logging
import re
import unicodedata
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, noload
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db_session, require_roles
from app.models.user import UserRole
from app.models.product import Product
from app.models.product_type import ProductType
from app.models.product_group import ProductGroup
from app.models.optional_color import OptionalColor, product_optionals
from app.models.client import Client
from app.models.representative import Representative
from app.core.config import settings
from app.core.uploads import read_upload_limited

logger = logging.getLogger("ilya.import")
router = APIRouter(prefix="/api/v1/import", tags=["import"])

_ADMIN_CADASTROS = Depends(require_roles(UserRole.admin, UserRole.cadastros))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_ROWS = 50_000
_MAX_CELL_LENGTH = 10_000
_MAX_ERRORS = 500
_QUERY_CHUNK = 5_000
_BULK_INSERT_CHUNK = 10_000
_IMPORT_LOCK_ID = 4_956_921_101


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _read_upload(file: UploadFile) -> bytes:
    return await read_upload_limited(
        file,
        _MAX_UPLOAD_BYTES,
        max_size_label="o limite de 10MB",
    )

def _normalize_key(key: str) -> str:
    """Ignora acentos, espaços, sublinhados e caixa alta nos cabeçalhos do CSV
    (ex.: 'Preço Lojista', 'preco_lojista' e 'PRECO LOJISTA' viram a mesma chave),
    tornando a importação tolerante a variações de formatação da planilha."""
    key = unicodedata.normalize("NFKD", key or "")
    key = "".join(c for c in key if not unicodedata.combining(c))
    return re.sub(r"[\s_]+", "", key.strip().lower())


def _read_rows(content: bytes) -> list[dict]:
    """Decodifica o CSV (UTF-8 com/sem BOM), detecta delimitador (, ou ;) e
    normaliza os cabeçalhos (minúsculas, sem espaços/sublinhados/acentos)."""
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV inválido: salve o arquivo em UTF-8.",
        )
    sample = decoded[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)
    rows: list[dict] = []
    for raw in reader:
        row = {
            _normalize_key(k or ""): (v.strip() if isinstance(v, str) else v)
            for k, v in raw.items()
        }
        if any(isinstance(value, str) and len(value) > _MAX_CELL_LENGTH for value in row.values()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"CSV contém célula acima de {_MAX_CELL_LENGTH} caracteres.",
            )
        if any(v for v in row.values()):
            rows.append(row)
            if len(rows) > _MAX_ROWS:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"CSV excede o limite de {_MAX_ROWS} linhas.",
                )
    return rows


async def _load_rows(file: UploadFile) -> list[dict]:
    content = await _read_upload(file)
    return await run_in_threadpool(_read_rows, content)


async def _load_chunked(
    db: AsyncSession,
    values,
    statement_factory,
) -> list:
    """Evita ultrapassar o limite de parâmetros do asyncpg/PostgreSQL."""
    normalized = list(values)
    loaded: list = []
    for offset in range(0, len(normalized), _QUERY_CHUNK):
        statement = statement_factory(
            normalized[offset:offset + _QUERY_CHUNK]
        )
        loaded.extend((await db.execute(statement)).scalars().all())
    return loaded


def _duplicate_values(values) -> set:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return duplicates


def _unambiguous_lookup(items, key_factory) -> tuple[dict, set]:
    lookup = {}
    ambiguous = set()
    for item in items:
        key = key_factory(item)
        if key in lookup:
            ambiguous.add(key)
        else:
            lookup[key] = item
    for key in ambiguous:
        lookup.pop(key, None)
    return lookup, ambiguous


async def _acquire_import_lock(db: AsyncSession) -> None:
    acquired = (
        await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": _IMPORT_LOCK_ID},
        )
    ).scalar()
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma importação em andamento. Tente novamente em instantes.",
        )
    # As requisições comuns continuam protegidas pelo timeout curto do pool,
    # enquanto uma importação válida recebe um teto próprio e finito.
    await db.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": str(settings.CSV_IMPORT_STATEMENT_TIMEOUT_MS)},
    )


def _record_error(errors: list[dict], row: int, error: Exception) -> None:
    if len(errors) < _MAX_ERRORS:
        errors.append({"row": row, "message": str(error)})
    elif len(errors) == _MAX_ERRORS:
        errors.append(
            {
                "row": 0,
                "message": f"Limite de {_MAX_ERRORS} erros atingido; corrija o arquivo e tente novamente.",
            }
        )


def _first(row: dict, *keys: str) -> Optional[str]:
    for k in keys:
        v = row.get(_normalize_key(k))
        if v not in (None, ""):
            return v
    return None


def _require(row: dict, field: str, *keys: str) -> str:
    v = _first(row, *(keys or (field,)))
    if not v:
        raise ValueError(f"Coluna '{field}' obrigatória e não pode ficar vazia.")
    return v


def _bool(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "sim", "yes", "y", "s", "verdadeiro", "x"}


def _bounded(
    value: Optional[str],
    field: str,
    max_length: int,
    *,
    required: bool = True,
) -> Optional[str]:
    if value in (None, ""):
        if required:
            raise ValueError(
                f"Coluna '{field}' obrigatória e não pode ficar vazia."
            )
        return None
    normalized = str(value).strip()
    if len(normalized) > max_length:
        raise ValueError(
            f"'{field}' excede o limite de {max_length} caracteres."
        )
    return normalized


def _dec(
    v: Optional[str],
    field: str = "valor",
    *,
    min_value: Optional[Decimal] = None,
    max_value: Optional[Decimal] = None,
    default: str = "0",
) -> Decimal:
    s = ("" if v is None else str(v)).strip().replace("R$", "").replace(" ", "")
    if not s:
        d = Decimal(default)
    else:
        if "," in s and "." in s:          # formato pt-BR: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:                       # 1234,56
            s = s.replace(",", ".")
        try:
            d = Decimal(s)
        except Exception:
            raise ValueError(f"'{field}' deve ser numérico (recebido: '{v}').")
    if not d.is_finite():
        raise ValueError(f"'{field}' deve ser um número finito.")
    if min_value is not None and d < min_value:
        raise ValueError(f"'{field}' não pode ser menor que {min_value} (recebido: '{v}').")
    if max_value is not None and d > max_value:
        raise ValueError(f"'{field}' não pode ser maior que {max_value} (recebido: '{v}').")
    return d


def _email(row: dict) -> str:
    email = (
        _bounded(_first(row, "email", "e-mail"), "email", 255) or ""
    ).lower()
    if not _EMAIL_RE.match(email):
        raise ValueError(f"E-mail inválido: '{email or '(vazio)'}'.")
    return email


def _uf(row: dict) -> str:
    state = (_first(row, "state", "uf", "estado") or "").upper()
    if len(state) != 2 or not state.isalpha():
        raise ValueError(f"UF inválida: '{state or '(vazio)'}'. Use 2 letras (ex.: SP).")
    return state


async def _finalize(db: AsyncSession, errors: list[dict]) -> bool:
    """Tudo-ou-nada: só confirma se não houve nenhum erro; caso contrário, desfaz."""
    if errors:
        await db.rollback()
        return False
    try:
        await db.commit()
        return True
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("Falha de banco ao confirmar importação CSV")
        _record_error(
            errors,
            0,
            ValueError(
                "O banco rejeitou um valor do CSV. Verifique duplicidades, "
                "tamanhos e faixas numéricas."
            ),
        )
        return False


def _summary(table: str, processed: int, created: int, updated: int, errors: list[dict], committed: bool) -> dict:
    return {
        "table": table,
        "processed": processed,
        "created": created if committed else 0,
        "updated": updated if committed else 0,
        "errors": errors,
        "committed": committed,
    }


def _address_fields(row: dict) -> dict:
    """Extrai e VALIDA os campos de contato (usado por clientes e representantes).
    Lança ValueError se algo estiver fora do formato."""
    fields = {
        "name": _bounded(_first(row, "name", "nome"), "name", 255),
        "phone": _bounded(
            _first(row, "phone", "telefone", "fone"),
            "phone",
            50,
        ),
        "email": _email(row),
        "cep": _bounded(_first(row, "cep"), "cep", 20),
        "numero": _bounded(
            _first(row, "numero", "número", "number"),
            "numero",
            50,
            required=False,
        ),
        "address": _bounded(
            _first(row, "address", "endereco", "endereço"),
            "address",
            255,
        ),
        "city": _bounded(_first(row, "city", "cidade"), "city", 255),
        "state": _uf(row),
    }
    return fields


# ── Cadastros de apoio ─────────────────────────────────────────────────────────

@router.post("/product-groups")
async def import_product_groups(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, ipi. Upsert por name."""
    rows = await _load_rows(file)
    await _acquire_import_lock(db)
    names = {_first(row, "name", "nome") for row in rows}
    names.discard(None)
    existing = {
        group.name: group
        for group in await _load_chunked(
            db,
            names,
            lambda chunk: select(ProductGroup).where(
                ProductGroup.name.in_(chunk)
            ),
        )
    }
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            name = _bounded(
                _require(row, "name", "name", "nome"),
                "name",
                100,
            )
            ipi = _dec(
                _first(row, "ipi"),
                "ipi",
                min_value=Decimal("0"),
                max_value=Decimal("999.99"),
            )
            g = existing.get(name)
            if g:
                g.ipi = ipi
                is_update = True
            else:
                g = ProductGroup(name=name, ipi=ipi)
                db.add(g)
                is_update = False
            existing[name] = g
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            _record_error(errors, i, e)
    committed = await _finalize(db, errors)
    return _summary("product-groups", len(rows), created, updated, errors, committed)


@router.post("/product-types")
async def import_product_types(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, group (nome do grupo → FK). Upsert por name."""
    rows = await _load_rows(file)
    await _acquire_import_lock(db)
    names = {_first(row, "name", "nome") for row in rows}
    names.discard(None)
    group_names = {_first(row, "group", "grupo") for row in rows}
    group_names.discard(None)
    existing = {
        product_type.name: product_type
        for product_type in await _load_chunked(
            db,
            names,
            lambda chunk: (
                select(ProductType)
                .where(ProductType.name.in_(chunk))
                .options(noload(ProductType.group))
            ),
        )
    }
    groups = {
        group.name: group
        for group in await _load_chunked(
            db,
            group_names,
            lambda chunk: select(ProductGroup).where(
                ProductGroup.name.in_(chunk)
            ),
        )
    }
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            name = _bounded(
                _require(row, "name", "name", "nome"),
                "name",
                50,
            )
            group_name = _bounded(
                _first(row, "group", "grupo"),
                "group",
                100,
                required=False,
            )
            group_id = None
            if group_name:
                grp = groups.get(group_name)
                if not grp:
                    raise ValueError(f"Grupo '{group_name}' não encontrado. Importe os grupos primeiro.")
                group_id = grp.id
            t = existing.get(name)
            if t:
                t.group_id = group_id
                is_update = True
            else:
                t = ProductType(name=name, group_id=group_id)
                db.add(t)
                is_update = False
            existing[name] = t
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            _record_error(errors, i, e)
    committed = await _finalize(db, errors)
    return _summary("product-types", len(rows), created, updated, errors, committed)


@router.post("/optionals")
async def import_optionals(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: category (código), color_name. Upsert por (category, color_name)."""
    rows = await _load_rows(file)
    await _acquire_import_lock(db)
    categories = {
        _first(row, "category", "categoria", "code", "codigo")
        for row in rows
    }
    categories.discard(None)
    existing = {
        (o.category, o.color_name): o
        for o in await _load_chunked(
            db,
            categories,
            lambda chunk: select(OptionalColor).where(
                OptionalColor.category.in_(chunk)
            ),
        )
    }
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            category = _bounded(
                _require(
                    row,
                    "category",
                    "category",
                    "categoria",
                    "code",
                    "codigo",
                ),
                "category",
                50,
            )
            color_name = _bounded(
                _require(
                    row,
                    "color_name",
                    "color_name",
                    "cor",
                    "color",
                ),
                "color_name",
                100,
            )
            key = (category, color_name)
            if key in existing:
                updated += 1  # idempotente
                continue
            o = OptionalColor(category=category, color_name=color_name)
            db.add(o)
            existing[key] = o
            created += 1
        except Exception as e:
            _record_error(errors, i, e)
    committed = await _finalize(db, errors)
    return _summary("optionals", len(rows), created, updated, errors, committed)


@router.post("/representatives")
async def import_representatives(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, phone, email, cep, numero, address, city, state. Upsert por email."""
    rows = await _load_rows(file)
    await _acquire_import_lock(db)
    email_values = [
        value.lower()
        for row in rows
        if (value := _first(row, "email", "e-mail"))
    ]
    emails = set(email_values)
    duplicate_input_emails = _duplicate_values(email_values)
    loaded_existing = await _load_chunked(
        db,
        emails,
        lambda chunk: select(Representative).where(
            func.lower(Representative.email).in_(chunk)
        ),
    )
    existing, ambiguous_existing_emails = _unambiguous_lookup(
        loaded_existing,
        lambda representative: representative.email.lower(),
    )
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            f = _address_fields(row)
            if f["email"] in duplicate_input_emails:
                raise ValueError(
                    f"E-mail '{f['email']}' aparece mais de uma vez no CSV."
                )
            if f["email"] in ambiguous_existing_emails:
                raise ValueError(
                    f"Há mais de um representante cadastrado com o e-mail '{f['email']}'."
                )
            r = existing.get(f["email"])
            if r:
                for k, v in f.items():
                    setattr(r, k, v)
                is_update = True
            else:
                r = Representative(**f)
                db.add(r)
                is_update = False
            existing[f["email"]] = r
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            _record_error(errors, i, e)
    committed = await _finalize(db, errors)
    return _summary("representatives", len(rows), created, updated, errors, committed)


@router.post("/clients")
async def import_clients(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, phone, email, cep, numero, address, city, state, price_profile,
    rep_email (ou rep_name → FK representante). Upsert por email."""
    rows = await _load_rows(file)
    await _acquire_import_lock(db)
    email_values = [
        value.lower()
        for row in rows
        if (value := _first(row, "email", "e-mail"))
    ]
    emails = set(email_values)
    duplicate_input_emails = _duplicate_values(email_values)
    rep_emails = {
        value.lower()
        for row in rows
        if (value := _first(row, "rep_email", "representante_email"))
    }
    rep_names = {
        value.lower()
        for row in rows
        if (value := _first(row, "rep_name", "representante", "rep"))
    }
    loaded_existing = await _load_chunked(
        db,
        emails,
        lambda chunk: select(Client).where(
            func.lower(Client.email).in_(chunk)
        ),
    )
    existing, ambiguous_existing_emails = _unambiguous_lookup(
        loaded_existing,
        lambda client: client.email.lower(),
    )
    reps_by_id = {
        representative.id: representative
        for representative in await _load_chunked(
            db,
            rep_emails,
            lambda chunk: select(Representative).where(
                func.lower(Representative.email).in_(chunk)
            ),
        )
    }
    reps_by_id.update(
        {
            representative.id: representative
            for representative in await _load_chunked(
                db,
                rep_names,
                lambda chunk: select(Representative).where(
                    func.lower(Representative.name).in_(chunk)
                ),
            )
        }
    )
    reps = list(reps_by_id.values())
    reps_by_email, ambiguous_rep_emails = _unambiguous_lookup(
        reps,
        lambda representative: representative.email.lower(),
    )
    reps_by_name, ambiguous_rep_names = _unambiguous_lookup(
        reps,
        lambda representative: representative.name.lower(),
    )
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            f = _address_fields(row)
            if f["email"] in duplicate_input_emails:
                raise ValueError(
                    f"E-mail '{f['email']}' aparece mais de uma vez no CSV."
                )
            if f["email"] in ambiguous_existing_emails:
                raise ValueError(
                    f"Há mais de um cliente cadastrado com o e-mail '{f['email']}'."
                )
            profile = (_first(row, "price_profile", "perfil") or "lojista").lower()
            if profile not in ("lojista", "corporativo"):
                raise ValueError("price_profile deve ser 'lojista' ou 'corporativo'.")
            rep_key = _first(row, "rep_email", "representante_email")
            rep_name = _first(row, "rep_name", "representante", "rep")
            rep_id = None
            if rep_key:
                normalized_rep_email = rep_key.lower()
                if normalized_rep_email in ambiguous_rep_emails:
                    raise ValueError(
                        f"Há mais de um representante com o e-mail '{rep_key}'."
                    )
                rep = reps_by_email.get(normalized_rep_email)
                if not rep:
                    raise ValueError(f"Representante e-mail '{rep_key}' não encontrado.")
                rep_id = rep.id
            elif rep_name:
                normalized_rep_name = rep_name.lower()
                if normalized_rep_name in ambiguous_rep_names:
                    raise ValueError(
                        f"Há mais de um representante com o nome '{rep_name}'; use rep_email."
                    )
                rep = reps_by_name.get(normalized_rep_name)
                if not rep:
                    raise ValueError(f"Representante '{rep_name}' não encontrado.")
                rep_id = rep.id
            c = existing.get(f["email"])
            if c:
                for k, v in f.items():
                    setattr(c, k, v)
                c.price_profile = profile
                c.rep_id = rep_id
                is_update = True
            else:
                c = Client(**f, price_profile=profile, rep_id=rep_id)
                db.add(c)
                is_update = False
            existing[f["email"]] = c
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            _record_error(errors, i, e)
    committed = await _finalize(db, errors)
    return _summary("clients", len(rows), created, updated, errors, committed)


# ── Catálogo de produtos em duas etapas ────────────────────────────────────────

@router.post("/products")
async def import_products(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Etapa 1 — Colunas: product_code, description, type, is_circular,
    altura, largura, profundidade, price_lojista, price_corporativo, observacao.
    Upsert por product_code (SKU)."""
    rows = await _load_rows(file)
    await _acquire_import_lock(db)
    codes = {
        _first(row, "product_code", "sku", "codigo", "código")
        for row in rows
    }
    codes.discard(None)
    existing = {
        product.product_code: product
        for product in await _load_chunked(
            db,
            codes,
            lambda chunk: (
                select(Product)
                .where(Product.product_code.in_(chunk))
                .options(
                    noload(Product.optionals),
                    noload(Product.set_items),
                    noload(Product.components),
                )
            ),
        )
    }
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            code = _bounded(
                _require(
                    row,
                    "product_code",
                    "product_code",
                    "sku",
                    "codigo",
                    "código",
                ),
                "product_code",
                100,
            )
            description = _require(row, "description", "description", "descricao", "descrição")
            is_circular = _bool(_first(row, "is_circular", "circular"))
            numeric_limit = Decimal("99999999.99")
            price_lojista = _dec(
                _require(
                    row,
                    "price_lojista",
                    "price_lojista",
                    "preco_lojista",
                    "preço_lojista",
                ),
                "price_lojista",
                min_value=Decimal("0"),
                max_value=numeric_limit,
            )
            price_corporativo = _dec(
                _require(
                    row,
                    "price_corporativo",
                    "price_corporativo",
                    "preco_corporativo",
                    "preço_corporativo",
                ),
                "price_corporativo",
                min_value=Decimal("0"),
                max_value=numeric_limit,
            )
            fields = dict(
                description=description,
                type=_bounded(
                    _first(row, "type", "tipo") or "Outro",
                    "type",
                    50,
                ),
                is_circular=is_circular,
                altura=_dec(
                    _first(row, "altura", "height"),
                    "altura",
                    min_value=Decimal("0"),
                    max_value=numeric_limit,
                ),
                largura=_dec(
                    _first(row, "largura", "width"),
                    "largura",
                    min_value=Decimal("0"),
                    max_value=numeric_limit,
                ),
                profundidade=(
                    Decimal("0")
                    if is_circular
                    else _dec(
                        _first(row, "profundidade", "depth"),
                        "profundidade",
                        min_value=Decimal("0"),
                        max_value=numeric_limit,
                    )
                ),
                price=price_lojista,  # coluna legada espelha o preço lojista (Bloco 62)
                price_lojista=price_lojista,
                price_corporativo=price_corporativo,
                observacao=_first(row, "observacao", "observação", "obs"),
            )
            p = existing.get(code)
            if p:
                for k, v in fields.items():
                    setattr(p, k, v)
                is_update = True
            else:
                p = Product(product_code=code, **fields)
                db.add(p)
                is_update = False
            existing[code] = p
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            _record_error(errors, i, e)
    committed = await _finalize(db, errors)
    return _summary("products", len(rows), created, updated, errors, committed)


@router.post("/product-optionals")
async def import_product_optionals(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Etapa 2 — Colunas: product_code, category, color_name. Cria os vínculos
    N:N produto↔opcional (idempotente via ON CONFLICT DO NOTHING)."""
    rows = await _load_rows(file)
    await _acquire_import_lock(db)
    codes = {_first(row, "product_code", "sku") for row in rows}
    codes.discard(None)
    categories = {_first(row, "category", "categoria") for row in rows}
    categories.discard(None)
    products = {
        product.product_code: product
        for product in await _load_chunked(
            db,
            codes,
            lambda chunk: (
                select(Product)
                .where(Product.product_code.in_(chunk))
                .options(
                    load_only(Product.id, Product.product_code),
                    noload(Product.optionals),
                    noload(Product.set_items),
                    noload(Product.components),
                )
            ),
        )
    }
    optionals = {
        (o.category, o.color_name): o
        for o in await _load_chunked(
            db,
            categories,
            lambda chunk: (
                select(OptionalColor)
                .where(OptionalColor.category.in_(chunk))
                .options(
                    load_only(
                        OptionalColor.id,
                        OptionalColor.category,
                        OptionalColor.color_name,
                    )
                )
            ),
        )
    }
    links: list[dict] = []
    seen_links: set[tuple] = set()
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            code = _bounded(
                _require(row, "product_code", "product_code", "sku"),
                "product_code",
                100,
            )
            category = _bounded(
                _require(row, "category", "category", "categoria"),
                "category",
                50,
            )
            color_name = _bounded(
                _require(
                    row,
                    "color_name",
                    "color_name",
                    "cor",
                    "color",
                ),
                "color_name",
                100,
            )
            product = products.get(code)
            if not product:
                raise ValueError(f"Produto '{code}' não encontrado. Rode a Etapa 1 primeiro.")
            optional = optionals.get((category, color_name))
            if not optional:
                raise ValueError(f"Opcional '{category}/{color_name}' não encontrado.")
            key = (product.id, optional.id)
            if key not in seen_links:
                seen_links.add(key)
                links.append(
                    {"product_id": product.id, "optional_id": optional.id}
                )
        except Exception as e:
            _record_error(errors, i, e)
    if not errors and links:
        for offset in range(0, len(links), _BULK_INSERT_CHUNK):
            stmt = (
                pg_insert(product_optionals)
                .values(links[offset:offset + _BULK_INSERT_CHUNK])
                .on_conflict_do_nothing()
            )
            await db.execute(stmt)
    committed = await _finalize(db, errors)
    return _summary(
        "product-optionals",
        len(rows),
        len(links),
        0,
        errors,
        committed,
    )
