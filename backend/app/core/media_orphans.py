"""Fotos órfãs do bucket europeu: inventário e quarentena.

Órfã = objeto do bucket EU (prefixos `eu-*` de fotos) cujo identificador (o UUID
do nome do arquivo) NÃO aparece em NENHUMA coluna de NENHUMA tabela do banco.
Original, miniatura e variantes de um mesmo arquivo compartilham o UUID, então
todos ficam protegidos enquanto o original estiver referenciado.

Princípios (na dúvida, não apaga):

* a busca de referências varre TODAS as colunas de texto/JSON do banco, não uma
  lista fixa de tabelas -- pega `photo_path` de produtos e opcionais, mas também
  os snapshots de pedido/e-mail e qualquer coluna criada no futuro;
* qualquer coluna que não puder ser lida deixa a varredura "incompleta" e bloqueia
  a quarentena;
* objetos com menos de 24 h ficam de fora (upload pode estar em andamento);
* nome fora do padrão `<uuid>.<ext>` nunca é tocado;
* nada é apagado de imediato: o objeto vai para `eu-trash/<data>/<chave>` no mesmo
  bucket EU e só some de vez numa segunda chamada, 7+ dias depois;
* só o cliente/bucket EU é usado; chave fora dos prefixos permitidos é recusada.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core import uploads
from app.core.config import settings

logger = logging.getLogger("ilya.media_orphans")

EU_PHOTO_PREFIXES = (
    "eu-products",
    "eu-product-thumbnails",
    "eu-optionals",
    "eu-optional-thumbnails",
    "eu-optional-variants",
)
QUARANTINE_ROOT = "eu-trash"
GRACE_PERIOD = timedelta(hours=24)
QUARANTINE_MIN_AGE = timedelta(days=7)
DEFAULT_BATCH = 200
MAX_BATCH = 500
SAMPLE_SIZE = 20
SCAN_TIMEOUT_MS = 300_000

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_KEY_NAME_RE = re.compile(rf"^({_UUID})\.[A-Za-z0-9][A-Za-z0-9.\-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Aceita a barra crua, escapada (`\/`, JSON) ou codificada (`%2F`, URL).
_REFERENCE_PATTERN = (
    # `(?i)`: na dúvida, citação em maiúsculas também protege a foto.
    r"(?i)eu-(?:products|product-thumbnails|optionals|optional-thumbnails|optional-variants)"
    rf"(?:/|\\/|%2[fF])({_UUID})"
)
# Tipos que não conseguem guardar uma chave de arquivo. Todo o resto é varrido.
_SKIPPED_TYPES = (
    "bool", "int2", "int4", "int8", "float4", "float8", "numeric", "money", "uuid",
    "date", "time", "timetz", "timestamp", "timestamptz", "interval", "bytea", "oid",
)
_COLUMNS_SQL = text(
    """
    SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid AND c.relkind IN ('r', 'p') AND NOT c.relispartition
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    WHERE a.attnum > 0 AND NOT a.attisdropped
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg\\_toast%' AND n.nspname NOT LIKE 'pg\\_temp%'
      AND t.typname::text <> ALL(CAST(:skipped AS text[]))
    ORDER BY n.nspname, c.relname, a.attnum
    """
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    modified: datetime


@dataclass
class PhotoReferences:
    uuids: set[str] = field(default_factory=set)
    columns_scanned: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class Inventory:
    referenced: list[StoredObject]
    recent: list[StoredObject]
    unclassified: list[StoredObject]
    orphans: list[StoredObject]
    references: PhotoReferences

    @property
    def total_objects(self) -> int:
        return (
            len(self.referenced) + len(self.recent)
            + len(self.unclassified) + len(self.orphans)
        )

    @property
    def blocked_reason(self) -> str | None:
        refs = self.references
        if refs.errors:
            return (
                "A varredura do banco ficou incompleta (colunas não lidas: "
                + ", ".join(refs.errors[:5]) + "). Por segurança nada será movido."
            )
        if refs.columns_scanned == 0:
            return "Nenhuma coluna do banco foi varrida. Por segurança nada será movido."
        if not refs.uuids and self.total_objects:
            return (
                "O banco não referencia nenhuma foto EU, mas o bucket tem objetos. "
                "Isso é suspeito; por segurança nada será movido."
            )
        return None


def key_uuid(key: str) -> str | None:
    """UUID do nome do arquivo (`<prefixo>/<uuid>.<ext>...`), ou None."""
    prefix, separator, name = key.partition("/")
    if not separator or prefix not in EU_PHOTO_PREFIXES or "/" in name:
        return None
    match = _KEY_NAME_RE.match(name)
    return match.group(1).lower() if match else None


def is_eu_photo_key(key: str) -> bool:
    return key.partition("/")[0] in EU_PHOTO_PREFIXES


def confirm_token(keys: list[str]) -> str:
    """`<quantidade>-<hash>` do conjunto exato de chaves."""
    ordered = sorted(keys)
    digest = hashlib.sha256("\n".join(ordered).encode("utf-8")).hexdigest()[:16]
    return f"{len(ordered)}-{digest}"


def classify(
    objects: list[StoredObject], references: PhotoReferences, now: datetime
) -> Inventory:
    inventory = Inventory([], [], [], [], references)
    for obj in sorted(objects, key=lambda o: o.key):
        uid = key_uuid(obj.key)
        if uid is None:
            inventory.unclassified.append(obj)
        elif uid in references.uuids:
            inventory.referenced.append(obj)
        elif now - obj.modified < GRACE_PERIOD:
            inventory.recent.append(obj)
        else:
            inventory.orphans.append(obj)
    return inventory


# --------------------------------------------------------------------------- #
# Armazenamento (somente o bucket EU)
# --------------------------------------------------------------------------- #

def eu_storage():
    """(cliente, bucket) do mercado europeu; 409 se não for seguro operar."""
    if not settings.eu_object_storage_configured():
        raise HTTPException(409, "Bucket de fotos do mercado europeu não configurado.")
    if (
        settings.OBJECT_STORAGE_EU_BUCKET == settings.OBJECT_STORAGE_BUCKET
        and settings.OBJECT_STORAGE_EU_ENDPOINT == settings.OBJECT_STORAGE_ENDPOINT
    ):
        raise HTTPException(
            409,
            "O bucket EU é o mesmo do Brasil. Por segurança a limpeza de órfãs não opera assim.",
        )
    return uploads._eu_object_storage_client(), settings.OBJECT_STORAGE_EU_BUCKET


def _list_prefix(client, bucket: str, prefix: str) -> list[StoredObject]:
    found: list[StoredObject] = []
    token = None
    while True:
        params = {"Bucket": bucket, "Prefix": prefix}
        if token:
            params["ContinuationToken"] = token
        response = client.list_objects_v2(**params)
        for item in response.get("Contents", []):
            if item["Key"].startswith(prefix):
                modified = item["LastModified"]
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=timezone.utc)
                found.append(StoredObject(item["Key"], int(item["Size"]), modified))
        if not response.get("IsTruncated"):
            return found
        token = response["NextContinuationToken"]


def list_photo_objects(client, bucket: str) -> list[StoredObject]:
    objects: list[StoredObject] = []
    for prefix in EU_PHOTO_PREFIXES:
        objects.extend(_list_prefix(client, bucket, prefix + "/"))
    return objects


# --------------------------------------------------------------------------- #
# Referências no banco
# --------------------------------------------------------------------------- #

async def scan_photo_references(db: AsyncSession) -> PhotoReferences:
    """UUIDs de fotos EU citados em qualquer coluna textual/JSON do banco."""
    references = PhotoReferences()
    await db.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": str(SCAN_TIMEOUT_MS)},
    )
    columns = (await db.execute(_COLUMNS_SQL, {"skipped": list(_SKIPPED_TYPES)})).all()
    for schema_name, table_name, column_name in columns:
        label = f"{schema_name}.{table_name}.{column_name}"
        statement = text(
            f"SELECT DISTINCT lower(m[1]) FROM {_quote(schema_name)}.{_quote(table_name)} AS t, "
            f"LATERAL regexp_matches(t.{_quote(column_name)}::text, :pattern, 'g') AS m"
        )
        try:
            async with db.begin_nested():
                rows = (await db.execute(statement, {"pattern": _REFERENCE_PATTERN})).all()
        except Exception as exc:  # noqa: BLE001 - qualquer falha deixa a varredura incompleta
            logger.warning("Varredura de %s falhou: %s", label, type(exc).__name__)
            references.errors.append(label)
            continue
        references.columns_scanned += 1
        references.uuids.update(row[0] for row in rows)
    return references


# --------------------------------------------------------------------------- #
# Apagar a foto antiga só se ninguém mais a usa
# --------------------------------------------------------------------------- #

_ANY_UUID_RE = re.compile(_UUID)
# Uma referência a foto tem pelo menos o UUID (36); coluna varchar menor não cabe.
_MIN_REFERENCE_COLUMN_LENGTH = 36
_REFERENCE_CHECK_TIMEOUT_MS = 10_000
_PRIORITY_TABLES = ("products", "product_photos", "optional_colors")
_REFERENCE_COLUMNS_SQL = text(
    """
    SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid AND c.relkind IN ('r', 'p') AND NOT c.relispartition
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    WHERE a.attnum > 0 AND NOT a.attisdropped
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg\\_toast%' AND n.nspname NOT LIKE 'pg\\_temp%'
      AND t.typname::text <> ALL(CAST(:skipped AS text[]))
      AND NOT (t.typname IN ('varchar', 'bpchar') AND a.atttypmod > 0
               AND a.atttypmod - 4 < :min_length)
    ORDER BY n.nspname, c.relname, a.attnum
    """
)


def upload_identity(path: str | None) -> str | None:
    """Trecho que identifica o arquivo nas colunas do banco: o UUID do nome
    (`object://eu-products/<uuid>.webp`, `/app/uploads/<uuid>.jpg`) ou, sem UUID,
    o nome do arquivo. None quando não há como identificar com segurança."""
    if not path:
        return None
    base = re.split(r"[\\/]", path.rstrip("/\\"))[-1]
    match = _ANY_UUID_RE.search(base)
    if match:
        return match.group(0).lower()
    return base if len(base) >= 8 else None


def _like_pattern(identity: str) -> str:
    escaped = identity.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def is_upload_referenced(db: AsyncSession, path: str | None) -> bool:
    """True se QUALQUER coluna textual/JSON do banco cita o arquivo.

    Barato o bastante para uma troca de foto: busca o UUID de um único arquivo,
    pula colunas curtas demais para guardar uma chave e para na primeira citação.
    Falha de qualquer natureza (timeout, permissão, identidade ausente) conta
    como "referenciado": na dúvida, o arquivo fica."""
    identity = upload_identity(path)
    if identity is None:
        return True
    pattern = _like_pattern(identity)
    try:
        await db.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(_REFERENCE_CHECK_TIMEOUT_MS)},
        )
        columns = (await db.execute(_REFERENCE_COLUMNS_SQL, {
            "skipped": list(_SKIPPED_TYPES), "min_length": _MIN_REFERENCE_COLUMN_LENGTH,
        })).all()
        columns.sort(key=lambda row: (row[1] not in _PRIORITY_TABLES,))
        for schema_name, table_name, column_name in columns:
            statement = text(
                f"SELECT 1 FROM {_quote(schema_name)}.{_quote(table_name)} AS t "
                f"WHERE t.{_quote(column_name)}::text ILIKE :pattern ESCAPE '\\' LIMIT 1"
            )
            async with db.begin_nested():
                found = (await db.execute(statement, {"pattern": pattern})).first()
            if found is not None:
                logger.info("Foto %s ainda é usada em %s.%s; mantida.",
                            identity, table_name, column_name)
                return True
        return False
    except Exception as exc:  # noqa: BLE001 - na dúvida, o arquivo fica
        logger.warning("Checagem de uso da foto %s falhou (%s); arquivo mantido.",
                       identity, type(exc).__name__)
        return True


async def delete_upload_if_unreferenced(
    db: AsyncSession, path: str | None, *, market: str | None = None
) -> bool:
    """Apaga o arquivo antigo (e miniatura/variantes) só se nenhuma outra linha
    do banco o usa. Chame DEPOIS do commit que trocou/removeu a referência.
    Devolve True se apagou. Arquivo mantido fica para a limpeza de órfãs."""
    if not path:
        return False
    if market is not None and not uploads.upload_belongs_to_market(path, market):
        return False
    referenced = await is_upload_referenced(db, path)
    try:
        await db.commit()  # encerra a transação da checagem (timeout local)
    except Exception:  # noqa: BLE001
        await db.rollback()
    if referenced:
        return False
    await uploads.delete_upload(path)
    return True


async def build_inventory(db: AsyncSession, *, now: datetime | None = None) -> Inventory:
    client, bucket = eu_storage()
    objects = await run_in_threadpool(list_photo_objects, client, bucket)
    references = await scan_photo_references(db)
    return classify(objects, references, now or datetime.now(timezone.utc))


def _totals(objects: list[StoredObject]) -> dict:
    return {"objects": len(objects), "bytes": sum(o.size for o in objects)}


def inventory_payload(inventory: Inventory) -> dict:
    orphans = inventory.orphans
    by_prefix: dict[str, dict] = {}
    for prefix in EU_PHOTO_PREFIXES:
        group = [o for o in orphans if o.key.startswith(prefix + "/")]
        by_prefix[prefix] = _totals(group)
    keys = [o.key for o in orphans]
    blocked = inventory.blocked_reason
    return {
        "scan": {
            "complete": not inventory.references.errors and inventory.references.columns_scanned > 0,
            "columns_scanned": inventory.references.columns_scanned,
            "unreadable_columns": inventory.references.errors,
            "referenced_photo_ids": len(inventory.references.uuids),
        },
        "bucket": {
            "total": {"objects": inventory.total_objects},
            "referenced": _totals(inventory.referenced),
            "kept_recent_24h": _totals(inventory.recent),
            "kept_unrecognized_name": _totals(inventory.unclassified),
        },
        "orphans": {
            **_totals(orphans),
            "by_prefix": by_prefix,
            "sample": keys[:SAMPLE_SIZE],
            "keys": keys,
        },
        "can_quarantine": blocked is None,
        "blocked_reason": blocked,
        "confirm": confirm_token(keys),
        "grace_hours": int(GRACE_PERIOD.total_seconds() // 3600),
    }


# --------------------------------------------------------------------------- #
# Quarentena
# --------------------------------------------------------------------------- #

def _quarantine_prefix(stamp: str) -> str:
    return f"{QUARANTINE_ROOT}/{stamp}/"


def _parse_stamp(raw: str) -> date:
    if not _DATE_RE.match(raw):
        raise HTTPException(422, "Data inválida; use AAAA-MM-DD.")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(422, "Data inválida; use AAAA-MM-DD.") from None


def _move_object(client, bucket: str, source: str, destination: str) -> None:
    client.copy_object(
        Bucket=bucket, Key=destination, CopySource={"Bucket": bucket, "Key": source}
    )
    client.delete_object(Bucket=bucket, Key=source)


def _move_batch(client, bucket: str, moves: list[tuple[str, str]]) -> tuple[list[str], list[dict]]:
    moved: list[str] = []
    failed: list[dict] = []
    for source, destination in moves:
        try:
            _move_object(client, bucket, source, destination)
        except (BotoCoreError, ClientError) as exc:
            failed.append({"key": source, "error": type(exc).__name__})
            logger.warning("Falha ao mover %s: %s", source, type(exc).__name__)
            continue
        moved.append(source)
        logger.info("Objeto movido: %s -> %s", source, destination)
    return moved, failed


async def quarantine_orphans(
    db: AsyncSession, *, confirm: str, limit: int, now: datetime | None = None
) -> dict:
    """Move até `limit` órfãs para a quarentena. `confirm` precisa ser exatamente
    o token do conjunto atual; o retorno traz o token do que sobrar."""
    now = now or datetime.now(timezone.utc)
    inventory = await build_inventory(db, now=now)
    if inventory.blocked_reason:
        raise HTTPException(409, inventory.blocked_reason)
    keys = [o.key for o in inventory.orphans]
    if confirm != confirm_token(keys):
        raise HTTPException(
            409,
            "O conjunto de órfãs mudou desde o inventário. Rode o inventário de novo.",
        )
    batch = keys[: max(1, min(limit, MAX_BATCH))]
    if not all(is_eu_photo_key(key) for key in batch):  # defesa extra
        raise HTTPException(409, "Chave fora dos prefixos EU; nada foi movido.")
    client, bucket = eu_storage()
    stamp = now.date().isoformat()
    moves = [(key, _quarantine_prefix(stamp) + key) for key in batch]
    moved, failed = await run_in_threadpool(_move_batch, client, bucket, moves)
    logger.info("Quarentena EU %s: %d movidas, %d falhas", stamp, len(moved), len(failed))
    moved_set = set(moved)
    left = [key for key in keys if key not in moved_set]
    return {
        "quarantine_date": stamp,
        "moved": moved,
        "failed": failed,
        "remaining": len(left),
        "next_confirm": confirm_token(left),
    }


def _group_quarantine(objects: list[StoredObject]) -> dict[str, list[StoredObject]]:
    batches: dict[str, list[StoredObject]] = {}
    for obj in objects:
        parts = obj.key.split("/", 2)
        if len(parts) == 3 and _DATE_RE.match(parts[1]) and is_eu_photo_key(parts[2]):
            batches.setdefault(parts[1], []).append(obj)
    return batches


async def quarantine_status(*, now: datetime | None = None) -> dict:
    client, bucket = eu_storage()
    objects = await run_in_threadpool(_list_prefix, client, bucket, QUARANTINE_ROOT + "/")
    today = (now or datetime.now(timezone.utc)).date()
    result = []
    for stamp, group in sorted(_group_quarantine(objects).items()):
        age_days = (today - date.fromisoformat(stamp)).days
        result.append({
            "date": stamp,
            **_totals(group),
            "age_days": age_days,
            "can_delete": age_days >= QUARANTINE_MIN_AGE.days,
            "confirm": confirm_token([o.key for o in group]),
        })
    return {"min_age_days": QUARANTINE_MIN_AGE.days, "batches": result}


async def _quarantine_batch(stamp_raw: str) -> tuple[object, str, str, list[StoredObject]]:
    stamp = _parse_stamp(stamp_raw).isoformat()
    client, bucket = eu_storage()
    objects = await run_in_threadpool(_list_prefix, client, bucket, _quarantine_prefix(stamp))
    return client, bucket, stamp, _group_quarantine(objects).get(stamp, [])


async def restore_quarantine(stamp_raw: str, *, limit: int) -> dict:
    """Devolve ao lugar de origem os objetos de um lote de quarentena."""
    client, bucket, stamp, group = await _quarantine_batch(stamp_raw)
    prefix = _quarantine_prefix(stamp)
    batch = [o.key for o in group][: max(1, min(limit, MAX_BATCH))]
    moves = [(key, key[len(prefix):]) for key in batch]
    moved, failed = await run_in_threadpool(_move_batch, client, bucket, moves)
    logger.info("Quarentena EU %s restaurada: %d objetos, %d falhas", stamp, len(moved), len(failed))
    return {
        "date": stamp,
        "restored": [key[len(prefix):] for key in moved],
        "failed": failed,
        "remaining": len(group) - len(moved),
    }


def _delete_batch(client, bucket: str, keys: list[str]) -> tuple[list[str], list[dict]]:
    deleted: list[str] = []
    failed: list[dict] = []
    for key in keys:
        if not key.startswith(QUARANTINE_ROOT + "/"):  # defesa extra
            failed.append({"key": key, "error": "FORA_DA_QUARENTENA"})
            continue
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            failed.append({"key": key, "error": type(exc).__name__})
            continue
        deleted.append(key)
        logger.info("Quarentena EU apagada de vez: %s", key)
    return deleted, failed


async def delete_quarantine(
    stamp_raw: str, *, confirm: str, limit: int, now: datetime | None = None
) -> dict:
    """Apaga de vez um lote de quarentena com 7+ dias. Irreversível."""
    now = now or datetime.now(timezone.utc)
    client, bucket, stamp, group = await _quarantine_batch(stamp_raw)
    age_days = (now.date() - date.fromisoformat(stamp)).days
    if age_days < QUARANTINE_MIN_AGE.days:
        raise HTTPException(
            409,
            f"Este lote tem {age_days} dia(s); só pode ser apagado de vez com "
            f"{QUARANTINE_MIN_AGE.days}+ dias.",
        )
    keys = [o.key for o in group]
    if not keys:
        raise HTTPException(404, "Lote de quarentena vazio ou inexistente.")
    if confirm != confirm_token(keys):
        raise HTTPException(
            409, "O lote mudou desde a consulta. Consulte a quarentena de novo."
        )
    batch = keys[: max(1, min(limit, MAX_BATCH))]
    deleted, failed = await run_in_threadpool(_delete_batch, client, bucket, batch)
    deleted_set = set(deleted)
    left = [key for key in keys if key not in deleted_set]
    return {
        "date": stamp,
        "deleted": deleted,
        "failed": failed,
        "remaining": len(left),
        "next_confirm": confirm_token(left),
    }
