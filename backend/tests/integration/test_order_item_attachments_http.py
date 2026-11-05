"""Anexo no comentário do item: envio HTTP real (multipart), download e carteira.

O armazenamento S3 é trocado por um dicionário em memória; todo o restante
(rotas, validação, banco PostgreSQL, permissões) é real.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import order_item_attachments as router_module
from app.core.security import create_access_token
from app.models.order_item_attachment import OrderItemAttachment
from app.models.user import UserRole
from tests.factories import (
    make_client,
    make_price_list,
    make_representative,
    make_user,
    make_user_market,
)
from tests.factories.orders import make_order, make_order_item

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
URL = "/api/v1/order-item-attachments"


@pytest.fixture
def storage(monkeypatch) -> dict[str, bytes]:
    objects: dict[str, bytes] = {}

    async def put(key: str, content: bytes, content_type: str) -> None:
        objects[key] = content

    async def get(key: str) -> bytes:
        return objects[key]

    async def delete(key: str) -> None:
        objects.pop(key, None)

    monkeypatch.setattr(router_module, "put_comment_attachment", put)
    monkeypatch.setattr(router_module, "get_comment_attachment", get)
    monkeypatch.setattr(router_module, "delete_comment_attachment", delete)
    return objects


async def _login(
    db: AsyncSession,
    role: UserRole,
    *,
    rep_id: uuid.UUID | None = None,
):
    user = await make_user(
        db, email=f"anexo-{uuid.uuid4().hex[:10]}@ilya-test.invalid", role=role
    )
    await make_user_market(db, user, market_code="BR", role=role.value, rep_id=rep_id)
    if rep_id is not None:
        user.rep_id = rep_id
        await db.flush()
    token = create_access_token(user.id, role.value, user.auth_version, "BR")
    return user, {"Authorization": f"Bearer {token}"}


async def test_pdf_real_enviado_como_multipart_e_baixado_depois(
    client: AsyncClient, db_session: AsyncSession, storage
) -> None:
    _, headers = await _login(db_session, UserRole.admin)

    response = await client.post(
        URL, headers=headers, files={"file": ("ficha técnica.pdf", PDF_BYTES, "application/pdf")}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(PDF_BYTES)
    assert body["original_filename"].endswith(".pdf")
    assert body["order_item_id"] is None
    assert list(storage.values()) == [PDF_BYTES]

    # Quem enviou consegue abrir o anexo ainda pendente, com o conteúdo original.
    download = await client.get(f"{URL}/{body['id']}", headers=headers)
    assert download.status_code == 200
    assert download.content == PDF_BYTES
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("inline;")


async def test_corpo_json_no_lugar_do_multipart_gera_o_erro_relatado(
    client: AsyncClient, db_session: AsyncSession, storage
) -> None:
    """Reproduz o sintoma: o navegador mandou JSON e o campo `file` sumiu."""
    _, headers = await _login(db_session, UserRole.admin)

    response = await client.post(URL, headers=headers, json={"file": {}})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "file"]
    assert storage == {}


@pytest.mark.parametrize(
    ("filename", "content", "status_code", "mensagem"),
    [
        ("virus.exe", b"MZ....", 422, "Envie uma foto JPG, PNG ou WebP, ou um documento PDF."),
        ("falso.pdf", b"isto nao e pdf", 422, "O arquivo não é um PDF válido."),
    ],
)
async def test_tipo_invalido_recebe_mensagem_amigavel(
    client: AsyncClient,
    db_session: AsyncSession,
    storage,
    filename: str,
    content: bytes,
    status_code: int,
    mensagem: str,
) -> None:
    _, headers = await _login(db_session, UserRole.admin)

    response = await client.post(URL, headers=headers, files={"file": (filename, content, "application/pdf")})

    assert response.status_code == status_code
    assert response.json()["detail"] == mensagem
    assert storage == {}


async def test_pdf_acima_do_limite_e_recusado(
    client: AsyncClient, db_session: AsyncSession, storage, monkeypatch
) -> None:
    monkeypatch.setattr(router_module.settings, "COMMENT_ATTACHMENTS_MAX_MB", 1)
    _, headers = await _login(db_session, UserRole.admin)
    grande = b"%PDF-1.7\n" + b"0" * (1024 * 1024) + b"\n%%EOF\n"

    response = await client.post(URL, headers=headers, files={"file": ("grande.pdf", grande, "application/pdf")})

    assert response.status_code == 413
    assert "1MB" in response.json()["detail"]
    assert storage == {}


async def test_envio_sem_login_e_negado(client: AsyncClient, storage) -> None:
    response = await client.post(URL, files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})

    assert response.status_code == 401
    assert storage == {}


async def test_anexo_salvo_so_abre_para_quem_enxerga_o_pedido(
    client: AsyncClient, db_session: AsyncSession, storage
) -> None:
    price_list = await make_price_list(db_session, market_code="BR")
    rep_dono = await make_representative(db_session, market_code="BR", name="Rep dona")
    rep_outro = await make_representative(db_session, market_code="BR", name="Rep outra")
    cliente = await make_client(db_session, price_list, market_code="BR")
    admin, admin_headers = await _login(db_session, UserRole.admin)
    _, dono_headers = await _login(db_session, UserRole.representante, rep_id=rep_dono.id)
    _, outro_headers = await _login(db_session, UserRole.representante, rep_id=rep_outro.id)

    order = await make_order(db_session, cliente, admin.id)
    order.rep_id = rep_dono.id
    item = await make_order_item(db_session, order)
    enviado = await client.post(
        URL, headers=dono_headers, files={"file": ("ficha.pdf", PDF_BYTES, "application/pdf")}
    )
    assert enviado.status_code == 201, enviado.text
    attachment_id = enviado.json()["id"]

    # Simula o salvamento do pedido, que reivindica o anexo para a linha.
    row = await db_session.get(OrderItemAttachment, uuid.UUID(attachment_id))
    row.order_item_id = item.id
    await db_session.flush()

    assert (await client.get(f"{URL}/{attachment_id}", headers=dono_headers)).content == PDF_BYTES
    assert (await client.get(f"{URL}/{attachment_id}", headers=admin_headers)).status_code == 200
    negado = await client.get(f"{URL}/{attachment_id}", headers=outro_headers)
    assert negado.status_code == 404
    assert negado.json()["detail"] == "Anexo não encontrado."


async def test_anexo_pendente_so_abre_para_quem_enviou(
    client: AsyncClient, db_session: AsyncSession, storage
) -> None:
    _, dono_headers = await _login(db_session, UserRole.admin)
    _, outro_headers = await _login(db_session, UserRole.admin)
    enviado = await client.post(
        URL, headers=dono_headers, files={"file": ("ficha.pdf", PDF_BYTES, "application/pdf")}
    )
    attachment_id = enviado.json()["id"]

    assert (await client.get(f"{URL}/{attachment_id}", headers=dono_headers)).status_code == 200
    assert (await client.get(f"{URL}/{attachment_id}", headers=outro_headers)).status_code == 404
    assert (await client.delete(f"{URL}/{attachment_id}", headers=outro_headers)).status_code == 404
    assert (await client.delete(f"{URL}/{attachment_id}", headers=dono_headers)).status_code == 204
    assert storage == {}
