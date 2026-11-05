import asyncio
import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.api.routers.order_item_attachments import (
    _filename,
    _validated_content,
    download_order_item_attachment,
    upload_order_item_attachment,
)
from app.api.routers.orders import _resolve_item_attachments
from app.core.config import settings
from app.models.order import OrderItem
from app.models.order_item_attachment import OrderItemAttachment
from app.schemas.order import OrderItemCreate


def _upload(content: bytes, filename: str) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


def test_pdf_valido_e_aceito_e_nome_e_higienizado():
    content = b"%PDF-1.7\nobjeto de teste\n%%EOF\n"

    validated, extension, content_type = asyncio.run(
        _validated_content(_upload(content, "orcamento\r\nmalicioso.pdf"))
    )

    assert validated == content
    assert extension == "pdf"
    assert content_type == "application/pdf"
    assert _filename("orcamento\r\nmalicioso.pdf", extension) == "orcamento_malicioso.pdf"


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"arquivo comum", "arquivo.pdf"),
        (b"%PDF-1.7\nsem marcador final", "arquivo.pdf"),
        (b"conteudo", "arquivo.exe"),
    ],
)
def test_arquivo_invalido_e_rejeitado(content: bytes, filename: str):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_validated_content(_upload(content, filename)))

    assert exc.value.status_code == 422


def test_schema_rejeita_anexo_duplicado_no_mesmo_item():
    attachment_id = uuid.uuid4()

    with pytest.raises(ValueError, match="não pode ser repetido"):
        OrderItemCreate(
            product_code="TESTE",
            qty=1,
            attachment_ids=[attachment_id, attachment_id],
        )


def test_relacionamento_preserva_anexo_durante_recriacao_da_linha():
    cascade = OrderItem.attachments.property.cascade

    assert "delete" in cascade
    assert "delete-orphan" not in cascade


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class _ResolveSession:
    def __init__(self, values):
        self._values = values

    async def execute(self, _statement):
        return _Result(self._values)


def test_resolucao_aceita_upload_do_usuario_no_mesmo_mercado():
    user_id = uuid.uuid4()
    attachment = OrderItemAttachment(
        id=uuid.uuid4(),
        market_code="EU",
        uploaded_by_user_id=user_id,
        object_key="eu/pending/teste.pdf",
        original_filename="teste.pdf",
        content_type="application/pdf",
        size_bytes=10,
    )
    item = OrderItemCreate(
        product_code="TESTE",
        qty=1,
        attachment_ids=[attachment.id],
    )

    result = asyncio.run(
        _resolve_item_attachments(
            _ResolveSession([attachment]),
            [item],
            SimpleNamespace(id=user_id),
            "EU",
        )
    )

    assert result == {0: [attachment]}


@pytest.mark.parametrize(
    ("market_code", "owner_matches"),
    [("BR", True), ("EU", False)],
)
def test_resolucao_nao_vaza_anexo_de_outro_mercado_ou_usuario(
    market_code: str, owner_matches: bool
):
    user_id = uuid.uuid4()
    attachment = OrderItemAttachment(
        id=uuid.uuid4(),
        market_code=market_code,
        uploaded_by_user_id=user_id if owner_matches else uuid.uuid4(),
        object_key="pending/teste.pdf",
        original_filename="teste.pdf",
        content_type="application/pdf",
        size_bytes=10,
    )
    item = OrderItemCreate(
        product_code="TESTE",
        qty=1,
        attachment_ids=[attachment.id],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            _resolve_item_attachments(
                _ResolveSession([attachment]),
                [item],
                SimpleNamespace(id=user_id),
                "EU",
            )
        )

    assert exc.value.status_code == 422


class _UploadSession:
    def __init__(self, *, fail_commit: bool = False):
        self.added = None
        self.fail_commit = fail_commit
        self.rollback_called = False

    def add(self, value):
        self.added = value

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("database unavailable")

    async def rollback(self):
        self.rollback_called = True

    async def refresh(self, _value):
        return None


def test_upload_grava_prefixo_do_mercado_e_metadados_privados():
    user_id = uuid.uuid4()
    session = _UploadSession()

    with (
        patch(
            "app.api.routers.order_item_attachments._validated_content",
            AsyncMock(return_value=(b"pdf", "pdf", "application/pdf")),
        ),
        patch(
            "app.api.routers.order_item_attachments.put_comment_attachment",
            AsyncMock(),
        ) as put,
    ):
        result = asyncio.run(
            upload_order_item_attachment(
                _upload(b"pdf", "Ficha técnica.pdf"),
                session,
                SimpleNamespace(id=user_id),
                SimpleNamespace(code="EU"),
            )
        )

    assert result is session.added
    assert result.market_code == "EU"
    assert result.order_item_id is None
    assert result.object_key.startswith(f"eu/pending/{user_id}/")
    put.assert_awaited_once_with(result.object_key, b"pdf", "application/pdf")


def test_falha_ao_gravar_metadados_remove_objeto_ja_enviado():
    session = _UploadSession(fail_commit=True)

    with (
        patch(
            "app.api.routers.order_item_attachments._validated_content",
            AsyncMock(return_value=(b"pdf", "pdf", "application/pdf")),
        ),
        patch(
            "app.api.routers.order_item_attachments.put_comment_attachment",
            AsyncMock(),
        ),
        patch(
            "app.api.routers.order_item_attachments.delete_comment_attachment",
            AsyncMock(),
        ) as delete,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                upload_order_item_attachment(
                    _upload(b"pdf", "arquivo.pdf"),
                    session,
                    SimpleNamespace(id=uuid.uuid4()),
                    SimpleNamespace(code="BR"),
                )
            )

    assert exc.value.status_code == 500
    assert session.rollback_called is True
    delete.assert_awaited_once()


class _DownloadSession:
    def __init__(self, attachment):
        self.attachment = attachment

    async def get(self, _model, _identifier):
        return self.attachment


def test_download_pendente_exige_dono_e_retorna_sem_cache():
    user_id = uuid.uuid4()
    attachment = OrderItemAttachment(
        id=uuid.uuid4(),
        market_code="EU",
        uploaded_by_user_id=user_id,
        object_key="eu/pending/teste.pdf",
        original_filename="teste.pdf",
        content_type="application/pdf",
        size_bytes=10,
    )

    with patch(
        "app.api.routers.order_item_attachments.get_comment_attachment",
        AsyncMock(return_value=b"conteudo"),
    ) as read:
        response = asyncio.run(
            download_order_item_attachment(
                attachment.id,
                _DownloadSession(attachment),
                SimpleNamespace(id=user_id),
                SimpleNamespace(code="EU"),
            )
        )

    assert response.body == b"conteudo"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    read.assert_awaited_once_with(attachment.object_key)


def test_download_de_outro_mercado_responde_como_inexistente():
    attachment = OrderItemAttachment(
        id=uuid.uuid4(),
        market_code="BR",
        uploaded_by_user_id=uuid.uuid4(),
        object_key="br/pending/teste.pdf",
        original_filename="teste.pdf",
        content_type="application/pdf",
        size_bytes=10,
    )

    with patch(
        "app.api.routers.order_item_attachments.get_comment_attachment",
        AsyncMock(),
    ) as read:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                download_order_item_attachment(
                    attachment.id,
                    _DownloadSession(attachment),
                    SimpleNamespace(id=attachment.uploaded_by_user_id),
                    SimpleNamespace(code="EU"),
                )
            )

    assert exc.value.status_code == 404
    read.assert_not_awaited()


def test_limites_padrao_do_bucket_sao_coerentes():
    assert settings.COMMENT_ATTACHMENTS_MAX_MB == 10
    assert settings.COMMENT_ATTACHMENTS_MAX_PER_ITEM == 5
