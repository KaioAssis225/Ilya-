import pytest
from fastapi import HTTPException, status

from app.api.routers.orders import _require_electronic_signatures_enabled
from app.core.config import settings


def test_electronic_signatures_are_blocked_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ELECTRONIC_SIGNATURES_ENABLED", False)

    with pytest.raises(HTTPException) as exc_info:
        _require_electronic_signatures_enabled()

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "assinatura manual" in exc_info.value.detail.lower()


def test_electronic_signatures_can_be_reenabled(monkeypatch):
    monkeypatch.setattr(settings, "ELECTRONIC_SIGNATURES_ENABLED", True)

    _require_electronic_signatures_enabled()
