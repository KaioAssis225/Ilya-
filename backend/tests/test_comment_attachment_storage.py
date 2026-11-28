from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import comment_attachments as storage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "encryption"),
    [
        ("https://storage.googleapis.com", {}),
        ("https://storage.googleapis.com.example.test", {"ServerSideEncryption": "AES256"}),
        ("http://s3:9000", {"ServerSideEncryption": "AES256"}),
    ],
)
async def test_comment_attachment_encryption_is_provider_specific(monkeypatch, endpoint, encryption):
    settings = SimpleNamespace(
        COMMENT_ATTACHMENTS_ENDPOINT=endpoint,
        COMMENT_ATTACHMENTS_BUCKET="qa",
        comment_attachment_storage_configured=lambda: True,
    )
    client = Mock()
    monkeypatch.setattr(storage, "settings", settings)
    monkeypatch.setattr(storage, "_client", lambda: client)

    await storage.put_comment_attachment("qa/anexo.txt", b"ficticio", "text/plain")

    client.put_object.assert_called_once_with(
        Bucket="qa", Key="qa/anexo.txt", Body=b"ficticio", ContentType="text/plain", **encryption
    )
