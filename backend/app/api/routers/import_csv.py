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
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_roles
from app.models.user import UserRole
from app.models.product import Product
from app.models.product_type import ProductType
from app.models.product_group import ProductGroup
from app.models.optional_color import OptionalColor, product_optionals
from app.models.client import Client
from app.models.representative import Representative
from app.core.uploads import read_upload_limited

logger = logging.getLogger("ilya.import")
router = APIRouter(prefix="/api/v1/import", tags=["import"])

_ADMIN_CADASTROS = Depends(require_roles(UserRole.admin, UserRole.cadastros))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


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
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: list[dict] = []
    for raw in reader:
        row = {
            _normalize_key(k or ""): (v.strip() if isinstance(v, str) else v)
            for k, v in raw.items()
        }
        if any(v for v in row.values()):
            rows.append(row)
    return rows


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


def _dec(v: Optional[str], field: str = "valor", *, min_value: Optional[Decimal] = None, default: str = "0") -> Decimal:
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
    if min_value is not None and d < min_value:
        raise ValueError(f"'{field}' não pode ser menor que {min_value} (recebido: '{v}').")
    return d


def _email(row: dict) -> str:
    email = (_first(row, "email", "e-mail") or "").lower()
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
    await db.commit()
    return True


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
    name = _first(row, "name", "nome")
    if not name:
        raise ValueError("Coluna 'name' obrigatória.")
    fields = {
        "name": name,
        "phone": _first(row, "phone", "telefone", "fone") or "",
        "email": _email(row),
        "cep": _first(row, "cep") or "",
        "numero": _first(row, "numero", "número", "number"),
        "address": _first(row, "address", "endereco", "endereço") or "",
        "city": _first(row, "city", "cidade") or "",
        "state": _uf(row),
    }
    for req in ("phone", "cep", "address", "city"):
        if not fields[req]:
            raise ValueError(f"Coluna '{req}' obrigatória e não pode ficar vazia.")
    return fields


# ── Cadastros de apoio ─────────────────────────────────────────────────────────

@router.post("/product-groups")
async def import_product_groups(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, ipi. Upsert por name."""
    rows = _read_rows(await _read_upload(file))
    existing = {g.name: g for g in (await db.execute(select(ProductGroup))).scalars().all()}
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            name = _require(row, "name", "name", "nome")
            ipi = _dec(_first(row, "ipi"), "ipi", min_value=Decimal("0"))
            async with db.begin_nested():
                g = existing.get(name)
                if g:
                    g.ipi = ipi
                    is_update = True
                else:
                    g = ProductGroup(name=name, ipi=ipi)
                    db.add(g)
                    is_update = False
                await db.flush()
            existing[name] = g
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})
    committed = await _finalize(db, errors)
    return _summary("product-groups", len(rows), created, updated, errors, committed)


@router.post("/product-types")
async def import_product_types(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, group (nome do grupo → FK). Upsert por name."""
    rows = _read_rows(await _read_upload(file))
    existing = {t.name: t for t in (await db.execute(select(ProductType))).scalars().all()}
    groups = {g.name: g for g in (await db.execute(select(ProductGroup))).scalars().all()}
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            name = _require(row, "name", "name", "nome")
            group_name = _first(row, "group", "grupo")
            group_id = None
            if group_name:
                grp = groups.get(group_name)
                if not grp:
                    raise ValueError(f"Grupo '{group_name}' não encontrado. Importe os grupos primeiro.")
                group_id = grp.id
            async with db.begin_nested():
                t = existing.get(name)
                if t:
                    t.group_id = group_id
                    is_update = True
                else:
                    t = ProductType(name=name, group_id=group_id)
                    db.add(t)
                    is_update = False
                await db.flush()
            existing[name] = t
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})
    committed = await _finalize(db, errors)
    return _summary("product-types", len(rows), created, updated, errors, committed)


@router.post("/optionals")
async def import_optionals(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: category (código), color_name. Upsert por (category, color_name)."""
    rows = _read_rows(await _read_upload(file))
    existing = {
        (o.category, o.color_name): o
        for o in (await db.execute(select(OptionalColor))).scalars().all()
    }
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            category = _require(row, "category", "category", "categoria", "code", "codigo")
            color_name = _require(row, "color_name", "color_name", "cor", "color")
            key = (category, color_name)
            if key in existing:
                updated += 1  # idempotente
                continue
            async with db.begin_nested():
                o = OptionalColor(category=category, color_name=color_name)
                db.add(o)
                await db.flush()
            existing[key] = o
            created += 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})
    committed = await _finalize(db, errors)
    return _summary("optionals", len(rows), created, updated, errors, committed)


@router.post("/representatives")
async def import_representatives(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, phone, email, cep, numero, address, city, state. Upsert por email."""
    rows = _read_rows(await _read_upload(file))
    existing = {r.email.lower(): r for r in (await db.execute(select(Representative))).scalars().all()}
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            f = _address_fields(row)
            async with db.begin_nested():
                r = existing.get(f["email"])
                if r:
                    for k, v in f.items():
                        setattr(r, k, v)
                    is_update = True
                else:
                    r = Representative(**f)
                    db.add(r)
                    is_update = False
                await db.flush()
            existing[f["email"]] = r
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})
    committed = await _finalize(db, errors)
    return _summary("representatives", len(rows), created, updated, errors, committed)


@router.post("/clients")
async def import_clients(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Colunas: name, phone, email, cep, numero, address, city, state, price_profile,
    rep_email (ou rep_name → FK representante). Upsert por email."""
    rows = _read_rows(await _read_upload(file))
    existing = {c.email.lower(): c for c in (await db.execute(select(Client))).scalars().all()}
    reps = (await db.execute(select(Representative))).scalars().all()
    reps_by_email = {r.email.lower(): r for r in reps}
    reps_by_name = {r.name.lower(): r for r in reps}
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            f = _address_fields(row)
            profile = (_first(row, "price_profile", "perfil") or "lojista").lower()
            if profile not in ("lojista", "corporativo"):
                raise ValueError("price_profile deve ser 'lojista' ou 'corporativo'.")
            rep_key = _first(row, "rep_email", "representante_email")
            rep_name = _first(row, "rep_name", "representante", "rep")
            rep_id = None
            if rep_key:
                rep = reps_by_email.get(rep_key.lower())
                if not rep:
                    raise ValueError(f"Representante e-mail '{rep_key}' não encontrado.")
                rep_id = rep.id
            elif rep_name:
                rep = reps_by_name.get(rep_name.lower())
                if not rep:
                    raise ValueError(f"Representante '{rep_name}' não encontrado.")
                rep_id = rep.id
            async with db.begin_nested():
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
                await db.flush()
            existing[f["email"]] = c
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})
    committed = await _finalize(db, errors)
    return _summary("clients", len(rows), created, updated, errors, committed)


# ── Catálogo de produtos em duas etapas ────────────────────────────────────────

@router.post("/products")
async def import_products(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Etapa 1 — Colunas: product_code, description, type, is_circular,
    altura, largura, profundidade, price_lojista, price_corporativo, observacao.
    Upsert por product_code (SKU)."""
    rows = _read_rows(await _read_upload(file))
    existing = {p.product_code: p for p in (await db.execute(select(Product))).scalars().all()}
    created = updated = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            code = _require(row, "product_code", "product_code", "sku", "codigo", "código")
            description = _require(row, "description", "description", "descricao", "descrição")
            is_circular = _bool(_first(row, "is_circular", "circular"))
            price_lojista = _dec(_require(row, "price_lojista", "price_lojista", "preco_lojista", "preço_lojista"), "price_lojista", min_value=Decimal("0"))
            price_corporativo = _dec(_require(row, "price_corporativo", "price_corporativo", "preco_corporativo", "preço_corporativo"), "price_corporativo", min_value=Decimal("0"))
            fields = dict(
                description=description,
                type=_first(row, "type", "tipo") or "Outro",
                is_circular=is_circular,
                altura=_dec(_first(row, "altura", "height"), "altura", min_value=Decimal("0")),
                largura=_dec(_first(row, "largura", "width"), "largura", min_value=Decimal("0")),
                profundidade=Decimal("0") if is_circular else _dec(_first(row, "profundidade", "depth"), "profundidade", min_value=Decimal("0")),
                price=price_lojista,  # coluna legada espelha o preço lojista (Bloco 62)
                price_lojista=price_lojista,
                price_corporativo=price_corporativo,
                observacao=_first(row, "observacao", "observação", "obs"),
            )
            async with db.begin_nested():
                p = existing.get(code)
                if p:
                    for k, v in fields.items():
                        setattr(p, k, v)
                    is_update = True
                else:
                    p = Product(product_code=code, **fields)
                    db.add(p)
                    is_update = False
                await db.flush()
            existing[code] = p
            updated += 1 if is_update else 0
            created += 0 if is_update else 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})
    committed = await _finalize(db, errors)
    return _summary("products", len(rows), created, updated, errors, committed)


@router.post("/product-optionals")
async def import_product_optionals(file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session), _: object = _ADMIN_CADASTROS):
    """Etapa 2 — Colunas: product_code, category, color_name. Cria os vínculos
    N:N produto↔opcional (idempotente via ON CONFLICT DO NOTHING)."""
    rows = _read_rows(await _read_upload(file))
    products = {p.product_code: p for p in (await db.execute(select(Product))).scalars().all()}
    optionals = {
        (o.category, o.color_name): o
        for o in (await db.execute(select(OptionalColor))).scalars().all()
    }
    linked = 0
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):
        try:
            code = _require(row, "product_code", "product_code", "sku")
            category = _require(row, "category", "category", "categoria")
            color_name = _require(row, "color_name", "color_name", "cor", "color")
            product = products.get(code)
            if not product:
                raise ValueError(f"Produto '{code}' não encontrado. Rode a Etapa 1 primeiro.")
            optional = optionals.get((category, color_name))
            if not optional:
                raise ValueError(f"Opcional '{category}/{color_name}' não encontrado.")
            async with db.begin_nested():
                stmt = pg_insert(product_optionals).values(
                    product_id=product.id, optional_id=optional.id
                ).on_conflict_do_nothing()
                await db.execute(stmt)
            linked += 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})
    committed = await _finalize(db, errors)
    return _summary("product-optionals", len(rows), linked, 0, errors, committed)
