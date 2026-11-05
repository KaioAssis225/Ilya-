"""Fotos órfãs do bucket europeu: inventário, quarentena e restauração.

Garantias travadas aqui (bucket simulado, sem rede e sem banco):

- foto referenciada nunca sai, nem a miniatura/variantes dela;
- objeto com menos de 24 h fica;
- nome fora do padrão `<uuid>.<ext>` fica;
- `confirm` errado -> 409 e nada é movido;
- varredura do banco incompleta ou suspeita -> 409;
- o bucket BR nunca é tocado (qualquer chamada nele quebra o teste);
- purge só move para `eu-trash/`; o apagar de vez exige 7+ dias e confirm.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.core import media_orphans as mo
from app.core import uploads as uploads_module
from app.core.config import settings

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=30)


class FakeBucket:
    """Bucket S3 mínimo; paginação de 2 em 2 para exercitar o ContinuationToken."""

    def __init__(self, name: str, *, forbidden: bool = False):
        self.name = name
        self.forbidden = forbidden
        self.objects: dict[str, tuple[bytes, datetime]] = {}
        self.fail_copy_for: set[str] = set()
        self.calls: list[tuple] = []

    def put(self, key: str, modified: datetime = OLD, body: bytes = b"x") -> None:
        self.objects[key] = (body, modified)

    def _check(self, bucket: str) -> None:
        assert not self.forbidden, "o bucket BR foi tocado!"
        assert bucket == self.name, f"bucket errado: {bucket}"

    def list_objects_v2(self, *, Bucket, Prefix, ContinuationToken=None):
        self._check(Bucket)
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start:start + 2]
        truncated = start + 2 < len(keys)
        response = {
            "Contents": [
                {"Key": k, "Size": len(self.objects[k][0]), "LastModified": self.objects[k][1]}
                for k in page
            ],
            "IsTruncated": truncated,
        }
        if truncated:
            response["NextContinuationToken"] = str(start + 2)
        return response

    def copy_object(self, *, Bucket, Key, CopySource):
        self._check(Bucket)
        self._check(CopySource["Bucket"])
        self.calls.append(("copy", CopySource["Key"], Key))
        if CopySource["Key"] in self.fail_copy_for:
            raise ClientError({"Error": {"Code": "InternalError"}}, "CopyObject")
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_object(self, *, Bucket, Key):
        self._check(Bucket)
        self.calls.append(("delete", Key))
        self.objects.pop(Key, None)


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def world(monkeypatch):
    br = FakeBucket("br-uploads", forbidden=True)
    eu = FakeBucket("eu-uploads")
    for name, value in {
        "OBJECT_STORAGE_ENDPOINT": "https://br.example",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "br-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "br-secret",
        "OBJECT_STORAGE_BUCKET": br.name,
        "OBJECT_STORAGE_EU_ENDPOINT": "https://eu.example",
        "OBJECT_STORAGE_EU_ACCESS_KEY_ID": "eu-key",
        "OBJECT_STORAGE_EU_SECRET_ACCESS_KEY": "eu-secret",
        "OBJECT_STORAGE_EU_BUCKET": eu.name,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(uploads_module, "_object_storage_client", lambda: br)
    monkeypatch.setattr(uploads_module, "_eu_object_storage_client", lambda: eu)

    state = SimpleNamespace(
        br=br, eu=eu,
        refs=mo.PhotoReferences(uuids=set(), columns_scanned=40, errors=[]),
    )

    async def fake_scan(_db):
        return state.refs

    monkeypatch.setattr(mo, "scan_photo_references", fake_scan)
    return state


def _photo(bucket: FakeBucket, uid: str, modified: datetime = OLD, *, kind="products") -> list[str]:
    """Original + miniatura (+ variantes, no caso de opcional) de um mesmo UUID."""
    if kind == "products":
        keys = [f"eu-products/{uid}.webp", f"eu-product-thumbnails/{uid}.webp.webp"]
    else:
        keys = [
            f"eu-optionals/{uid}.png",
            f"eu-optional-thumbnails/{uid}.png.webp",
            f"eu-optional-variants/{uid}.png.v1-thumb.webp",
            f"eu-optional-variants/{uid}.png.v1-gallery.webp",
            f"eu-optional-variants/{uid}.png.v1-zoom.webp",
        ]
    for key in keys:
        bucket.put(key, modified)
    return keys


def _inventory(world):
    return asyncio.run(mo.build_inventory(None, now=NOW))


def _quarantine(world, confirm, limit=200, now=NOW):
    return asyncio.run(mo.quarantine_orphans(None, confirm=confirm, limit=limit, now=now))


def test_classifica_referenciada_recente_estranha_e_orfa(world):
    ref, orfa_p, orfa_o, recente = _uid(), _uid(), _uid(), _uid()
    kept_ref = _photo(world.eu, ref)
    orphans = _photo(world.eu, orfa_p) + _photo(world.eu, orfa_o, kind="optionals")
    kept_recent = _photo(world.eu, recente, NOW - timedelta(hours=3))
    world.eu.put("eu-products/arquivo-sem-uuid.webp")
    world.eu.put("eu-products/sub/pasta.webp")
    world.refs.uuids = {ref}

    inventory = _inventory(world)

    assert [o.key for o in inventory.orphans] == sorted(orphans)
    assert {o.key for o in inventory.referenced} == set(kept_ref)
    assert {o.key for o in inventory.recent} == set(kept_recent)
    assert {o.key for o in inventory.unclassified} == {
        "eu-products/arquivo-sem-uuid.webp", "eu-products/sub/pasta.webp",
    }
    payload = mo.inventory_payload(inventory)
    assert payload["orphans"]["objects"] == 7
    assert payload["orphans"]["by_prefix"]["eu-optional-variants"]["objects"] == 3
    assert payload["can_quarantine"] is True
    assert payload["confirm"] == mo.confirm_token(orphans)


def test_miniatura_ou_variante_de_foto_referenciada_nunca_e_orfa(world):
    uid = _uid()
    keys = _photo(world.eu, uid, kind="optionals")
    world.refs.uuids = {uid}
    inventory = _inventory(world)
    assert inventory.orphans == []
    assert {o.key for o in inventory.referenced} == set(keys)


def test_uuid_e_comparado_sem_diferenciar_maiusculas(world):
    uid = _uid()
    _photo(world.eu, uid.upper())
    world.refs.uuids = {uid}
    assert _inventory(world).orphans == []


def test_confirm_errado_da_409_e_nao_move_nada(world):
    _photo(world.eu, _uid())
    world.refs.uuids = {_uid()}
    before = dict(world.eu.objects)
    with pytest.raises(HTTPException) as exc:
        _quarantine(world, "1-0000000000000000")
    assert exc.value.status_code == 409
    assert world.eu.objects == before
    assert world.eu.calls == []


def test_purge_move_para_a_quarentena_sem_apagar_de_vez(world):
    uid_a, uid_b, keep = _uid(), _uid(), _uid()
    orphans = _photo(world.eu, uid_a) + _photo(world.eu, uid_b)
    kept = _photo(world.eu, keep)
    world.refs.uuids = {keep}
    world.br.objects["products/" + uid_a + ".webp"] = (b"br", OLD)  # mesmo UUID, outro bucket

    confirm = mo.inventory_payload(_inventory(world))["confirm"]
    result = _quarantine(world, confirm)

    assert sorted(result["moved"]) == sorted(orphans)
    assert result["failed"] == [] and result["remaining"] == 0
    assert result["quarantine_date"] == "2026-11-10"
    for key in orphans:
        assert key not in world.eu.objects
        assert f"eu-trash/2026-11-10/{key}" in world.eu.objects
    for key in kept:
        assert key in world.eu.objects
    assert "products/" + uid_a + ".webp" in world.br.objects
    deletes = [c[1] for c in world.eu.calls if c[0] == "delete"]
    assert sorted(deletes) == sorted(orphans)


def test_lotes_encadeiam_com_next_confirm(world):
    for _ in range(3):
        _photo(world.eu, _uid())  # 6 objetos órfãos
    world.refs.uuids = {_uid()}
    confirm = mo.inventory_payload(_inventory(world))["confirm"]

    first = _quarantine(world, confirm, limit=4)
    assert len(first["moved"]) == 4 and first["remaining"] == 2
    with pytest.raises(HTTPException) as exc:  # o token antigo deixa de valer
        _quarantine(world, confirm, limit=4)
    assert exc.value.status_code == 409
    second = _quarantine(world, first["next_confirm"], limit=4)
    assert len(second["moved"]) == 2 and second["remaining"] == 0
    assert not [k for k in world.eu.objects if not k.startswith("eu-trash/")]


def test_falha_na_copia_nao_apaga_o_original_e_continua(world):
    keys = _photo(world.eu, _uid())
    world.refs.uuids = {_uid()}
    world.eu.fail_copy_for = {keys[0]}
    confirm = mo.inventory_payload(_inventory(world))["confirm"]
    result = _quarantine(world, confirm)
    assert [f["key"] for f in result["failed"]] == [keys[0]]
    assert keys[0] in world.eu.objects  # original intacto
    assert result["remaining"] == 1
    assert result["next_confirm"] == mo.confirm_token([keys[0]])


def test_varredura_incompleta_bloqueia(world):
    _photo(world.eu, _uid())
    world.refs.uuids = {_uid()}
    world.refs.errors = ["public.order_x.coluna"]
    assert mo.inventory_payload(_inventory(world))["can_quarantine"] is False
    with pytest.raises(HTTPException) as exc:
        _quarantine(world, "qualquer")
    assert exc.value.status_code == 409
    assert world.eu.calls == []


def test_banco_sem_nenhuma_referencia_mas_bucket_cheio_bloqueia(world):
    _photo(world.eu, _uid())
    world.refs.uuids = set()
    inventory = _inventory(world)
    assert inventory.blocked_reason
    with pytest.raises(HTTPException):
        _quarantine(world, mo.confirm_token([o.key for o in inventory.orphans]))
    assert world.eu.calls == []


def test_bucket_eu_igual_ao_br_recusa(world, monkeypatch):
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_BUCKET", world.br.name)
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_ENDPOINT", settings.OBJECT_STORAGE_ENDPOINT)
    with pytest.raises(HTTPException) as exc:
        _inventory(world)
    assert exc.value.status_code == 409


def test_sem_bucket_eu_configurado_recusa(world, monkeypatch):
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_BUCKET", "")
    with pytest.raises(HTTPException) as exc:
        _inventory(world)
    assert exc.value.status_code == 409


def test_quarentena_nunca_e_listada_como_foto(world):
    world.eu.put("eu-trash/2026-11-01/eu-products/" + _uid() + ".webp")
    world.refs.uuids = {_uid()}
    assert _inventory(world).total_objects == 0


def test_restore_devolve_ao_lugar_de_origem(world):
    orphans = _photo(world.eu, _uid())
    world.refs.uuids = {_uid()}
    confirm = mo.inventory_payload(_inventory(world))["confirm"]
    _quarantine(world, confirm)
    result = asyncio.run(mo.restore_quarantine("2026-11-10", limit=200))
    assert sorted(result["restored"]) == sorted(orphans)
    assert result["remaining"] == 0
    assert set(world.eu.objects) == set(orphans)


def test_apagar_quarentena_exige_7_dias_e_confirm(world):
    _photo(world.eu, _uid())
    _photo(world.eu, _uid())
    world.refs.uuids = {_uid()}
    _quarantine(world, mo.inventory_payload(_inventory(world))["confirm"])
    stamp = "2026-11-10"

    status = asyncio.run(mo.quarantine_status(now=NOW + timedelta(days=2)))
    batch = status["batches"][0]
    assert batch["date"] == stamp and batch["objects"] == 4 and batch["can_delete"] is False

    with pytest.raises(HTTPException) as exc:  # jovem demais
        asyncio.run(mo.delete_quarantine(
            stamp, confirm=batch["confirm"], limit=200, now=NOW + timedelta(days=2)))
    assert exc.value.status_code == 409

    later = NOW + timedelta(days=8)
    with pytest.raises(HTTPException) as exc:  # confirm errado
        asyncio.run(mo.delete_quarantine(stamp, confirm="4-0000000000000000", limit=200, now=later))
    assert exc.value.status_code == 409
    assert len(world.eu.objects) == 4

    result = asyncio.run(mo.delete_quarantine(stamp, confirm=batch["confirm"], limit=200, now=later))
    assert len(result["deleted"]) == 4 and result["remaining"] == 0
    assert world.eu.objects == {}


def test_apagar_quarentena_nao_toca_fotos_fora_de_eu_trash(world):
    keep = _uid()
    kept = _photo(world.eu, keep)
    world.refs.uuids = {keep}
    world.eu.put("eu-trash/2026-10-01/eu-products/" + _uid() + ".webp")
    batch = asyncio.run(mo.quarantine_status(now=NOW))["batches"][0]
    asyncio.run(mo.delete_quarantine("2026-10-01", confirm=batch["confirm"], limit=200, now=NOW))
    assert set(world.eu.objects) == set(kept)


def test_data_invalida_na_quarentena(world):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mo.restore_quarantine("../eu-products", limit=1))
    assert exc.value.status_code == 422


def test_chaves_e_prefixos_permitidos():
    assert not mo.is_eu_photo_key("products/abc.webp")
    assert not mo.is_eu_photo_key("order-documents/1/x.pdf")
    assert not mo.is_eu_photo_key("eu-trash/2026-11-01/eu-products/a.webp")
    assert mo.is_eu_photo_key("eu-optional-variants/a")
    uid = _uid()
    assert mo.key_uuid(f"products/{uid}.webp") is None
    assert mo.key_uuid(f"eu-products/{uid}.webp") == uid
    assert mo.key_uuid(f"eu-products/{uid}") is None


def test_rotas_exigem_plataforma_admin():
    """Sem token, as cinco rotas respondem 401 (nenhuma abre sem credencial)."""
    import httpx

    from app.api.deps import get_db_session
    from app.main import app

    async def no_db():
        yield None

    async def chamar() -> list[int]:
        base = "/api/v1/markets/EU/media/orphans"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            respostas = [
                await client.get(base),
                await client.post(base + "/purge", json={"confirm": "0-xxxxxxxx"}),
                await client.get(base + "/quarantine"),
                await client.post(base + "/quarantine/restore", json={"date": "2026-11-01"}),
                await client.post(
                    base + "/quarantine/delete",
                    json={"date": "2026-11-01", "confirm": "0-xxxxxxxx"},
                ),
            ]
        return [r.status_code for r in respostas]

    app.dependency_overrides[get_db_session] = no_db
    try:
        assert asyncio.run(chamar()) == [401] * 5
    finally:
        app.dependency_overrides.pop(get_db_session, None)
