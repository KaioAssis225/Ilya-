import asyncio
import inspect
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from pydantic import ValidationError
from starlette.requests import Request

from app.api.routers.dashboard import get_overview
from app.api.routers.import_csv import (
    _bounded,
    _dec,
    _duplicate_values,
    _load_chunked,
    _read_rows,
    _unambiguous_lookup,
)
from app.api.routers.orders import (
    _decode_order_cursor,
    _encode_order_cursor,
    _ensure_total_capacity,
    _money,
    _representative_cannot_access_order,
    generate_sign_token,
    sign_with_token,
    verify_sign_token,
)
from app.api.routers.utils import lookup_cep
from app.core.limiter import rate_limit_key
from app.core.request_size import RequestSizeLimitMiddleware
from app.core.search import literal_contains_pattern
from app.core.security import create_access_token
from app.core import uploads as uploads_module
from app.core.config import settings
from app.core.uploads import build_photo_url, sanitize_image_upload
from app.models.user import UserRole
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.order import OrderListRead
from app.schemas.product import ProductBatchRequest
from app.schemas.representative import RepresentativeCreate


def _upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def _contact_payload(state: str) -> dict:
    return {
        "name": "Teste",
        "phone": "11999999999",
        "email": "teste@example.com",
        "cep": "01001-000",
        "address": "Praça da Sé",
        "city": "São Paulo",
        "state": state,
    }


def test_cursor_round_trip_preserva_ordem_total():
    created_at = datetime(2026, 7, 16, 12, 30, tzinfo=timezone.utc)
    entity_id = uuid.uuid4()
    cursor = _encode_order_cursor(created_at, entity_id)
    assert _decode_order_cursor(cursor) == (created_at, entity_id)


def test_cursor_invalido_e_rejeitado():
    with pytest.raises(HTTPException) as exc:
        _decode_order_cursor("nao-e-um-cursor")
    assert exc.value.status_code == 422


def test_schema_de_listagem_nao_transporta_campos_pesados():
    fields = set(OrderListRead.model_fields)
    assert "rep_signature" not in fields
    assert "client_signature" not in fields
    assert "history" not in fields
    assert "notes" not in fields


def test_lote_de_produtos_tem_limite_operacional():
    with pytest.raises(ValidationError):
        ProductBatchRequest(product_codes=[f"SKU-{i}" for i in range(101)])


def test_uf_e_normalizada_na_entrada():
    assert ClientCreate(**_contact_payload(" sp ")).state == "SP"
    assert ClientUpdate(state="rj").state == "RJ"
    assert RepresentativeCreate(**_contact_payload("mg")).state == "MG"


def test_uf_invalida_e_rejeitada():
    with pytest.raises(ValidationError):
        ClientCreate(**_contact_payload("S1"))
    with pytest.raises(ValidationError):
        ClientCreate(**{**_contact_payload("SP"), "state": 1})


def test_csv_exige_utf8():
    with pytest.raises(HTTPException) as exc:
        _read_rows(b"\xff\xfe\xfa")
    assert exc.value.status_code == 422


def test_busca_trata_curingas_como_texto_literal():
    assert literal_contains_pattern("50%_\\") == "%50\\%\\_\\\\%"


def test_csv_valida_limite_textual_e_numerico():
    with pytest.raises(ValueError):
        _bounded("x" * 51, "type", 50)
    with pytest.raises(ValueError):
        _dec("100000000", "price", max_value=Decimal("99999999.99"))
    with pytest.raises(ValueError):
        _dec("NaN", "price")


def test_csv_detecta_chaves_duplicadas_e_nao_escolhe_registro_ambiguo():
    first = {"email": "duplicado@example.com", "id": 1}
    second = {"email": "duplicado@example.com", "id": 2}
    unique = {"email": "unico@example.com", "id": 3}

    assert _duplicate_values(
        ["duplicado@example.com", "duplicado@example.com", "unico@example.com"]
    ) == {"duplicado@example.com"}

    lookup, ambiguous = _unambiguous_lookup(
        [first, second, unique],
        lambda item: item["email"],
    )
    assert ambiguous == {"duplicado@example.com"}
    assert "duplicado@example.com" not in lookup
    assert lookup["unico@example.com"] is unique


def test_calculo_monetario_arredonda_e_rejeita_total_fora_da_coluna():
    assert _money(Decimal("10.005")) == Decimal("10.01")
    _ensure_total_capacity(Decimal("999999999999999999.99"))
    with pytest.raises(HTTPException) as exc:
        _ensure_total_capacity(Decimal("1000000000000000000.00"))
    assert exc.value.status_code == 422


def test_representante_sem_vinculo_nao_acessa_pedido_sem_representante():
    user = SimpleNamespace(
        role=UserRole.representante,
        rep_id=None,
    )
    order = SimpleNamespace(rep_id=None)

    assert _representative_cannot_access_order(user, order)


def test_preload_do_csv_divide_listas_grandes_em_lotes():
    class Scalars:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

    class Result:
        def __init__(self, values):
            self.values = values

        def scalars(self):
            return Scalars(self.values)

    class FakeDb:
        def __init__(self):
            self.sizes: list[int] = []

        async def execute(self, values):
            self.sizes.append(len(values))
            return Result(values)

    db = FakeDb()
    loaded = asyncio.run(
        _load_chunked(db, range(12_001), lambda chunk: chunk)
    )

    assert db.sizes == [5_000, 5_000, 2_001]
    assert len(loaded) == 12_001


def test_limite_de_corpo_cobre_transferencia_em_partes():
    sent: list[dict] = []
    incoming = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )

    async def receive():
        return next(incoming)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": [],
        "client": ("203.0.113.10", 1234),
        "server": ("api.example.com", 443),
    }
    middleware = RequestSizeLimitMiddleware(
        downstream,
        max_bytes=5,
        max_mb=1,
    )

    asyncio.run(middleware(scope, receive, send))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


def test_rate_limit_usa_usuario_autenticado_em_vez_do_ip_compartilhado():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "vendedor")
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", f"Bearer {token}".encode("ascii")),
            ],
            "client": ("203.0.113.10", 1234),
        }
    )

    assert rate_limit_key(request) == f"user:{user_id}"


def test_imagem_grande_e_reduzida_fora_do_event_loop():
    source = Image.new("RGB", (1200, 600), color="white")
    raw = io.BytesIO()
    source.save(raw, format="JPEG")

    sanitized, extension = asyncio.run(
        sanitize_image_upload(
            _upload(raw.getvalue(), "foto.jpg"),
            max_bytes=2 * 1024 * 1024,
            max_size_label="2MB",
            allowed_extensions=["jpg"],
            max_pixels=2_000_000,
            max_dimension=400,
        )
    )

    result = Image.open(io.BytesIO(sanitized))
    assert extension == "jpg"
    assert max(result.size) <= 400


def test_url_de_foto_preserva_arquivo_legado_e_reconhece_objeto():
    assert build_photo_url("app/static/uploads/foto.jpg") == "/static/uploads/foto.jpg"
    assert (
        build_photo_url("object://products/123e4567-e89b-12d3-a456-426614174000.jpg")
        == "/api/v1/media/products/123e4567-e89b-12d3-a456-426614174000.jpg"
    )


def test_estilo_de_url_da_railway_e_normalizado_para_boto():
    assert uploads_module._normalized_addressing_style("virtual-host") == "virtual"
    assert uploads_module._normalized_addressing_style("path") == "path"


def test_upload_em_objeto_e_compensado_em_caso_de_rollback(monkeypatch):
    class FakeObjectStorage:
        def __init__(self):
            self.put: dict | None = None
            self.deleted: dict | None = None

        def put_object(self, **kwargs):
            self.put = kwargs

        def delete_object(self, **kwargs):
            self.deleted = kwargs

    storage = FakeObjectStorage()
    monkeypatch.setattr(settings, "OBJECT_STORAGE_ENDPOINT", "https://storage.example")
    monkeypatch.setattr(settings, "OBJECT_STORAGE_ACCESS_KEY_ID", "access")
    monkeypatch.setattr(settings, "OBJECT_STORAGE_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(settings, "OBJECT_STORAGE_BUCKET", "uploads")
    monkeypatch.setattr(uploads_module, "_object_storage_client", lambda: storage)

    reference = asyncio.run(
        uploads_module.persist_upload(
            b"imagem",
            "app/static/uploads/optionals",
            "webp",
        )
    )

    assert reference.startswith("object://optionals/")
    assert storage.put is not None
    assert storage.put["Bucket"] == "uploads"
    assert storage.put["ContentType"] == "image/webp"

    asyncio.run(uploads_module.delete_upload(reference))
    assert storage.deleted == {
        "Bucket": "uploads",
        "Key": reference.removeprefix("object://"),
    }


@pytest.mark.parametrize(
    "endpoint",
    [
        lookup_cep,
        get_overview,
        generate_sign_token,
        verify_sign_token,
        sign_with_token,
    ],
)
def test_endpoint_limitado_recebe_response_para_injetar_headers(endpoint):
    assert "response" in inspect.signature(endpoint).parameters
