import uuid
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.routers.privacy import (
    _hold_read,
    approve_retention_review,
    create_legal_hold,
    create_retention_dry_run,
    release_legal_hold,
)
from app.main import app
from app.schemas.retention import (
    LegalHoldCreate,
    LegalHoldRelease,
    RetentionDryRunRequest,
)


def test_legal_hold_exige_motivo_real_e_data_com_fuso():
    subject_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        LegalHoldCreate(
            subject_type="client",
            subject_id=subject_id,
            reason="     ",
        )
    with pytest.raises(ValidationError, match="fuso"):
        LegalHoldCreate(
            subject_type="client",
            subject_id=subject_id,
            reason="Processo judicial ativo",
            expires_at=datetime(2027, 1, 1),
        )


def test_liberacao_de_legal_hold_exige_senha_e_justificativa():
    with pytest.raises(ValidationError):
        LegalHoldRelease(password="", reason="Encerrado")
    with pytest.raises(ValidationError):
        LegalHoldRelease(password="SenhaForte1", reason="   ")


def test_categorias_do_dry_run_nao_podem_repetir():
    with pytest.raises(ValidationError, match="repetidas"):
        RetentionDryRunRequest(categories=["clients", "clients"])


def test_estado_ativo_do_legal_hold_considera_expiracao_e_liberacao():
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid.uuid4(),
        "subject_type": "client",
        "subject_id": uuid.uuid4(),
        "reason": "Garantia em andamento",
        "release_reason": None,
        "created_at": now,
    }
    active = _hold_read(
        SimpleNamespace(
            **base,
            expires_at=now + timedelta(days=1),
            released_at=None,
        ),
        now,
    )
    expired = _hold_read(
        SimpleNamespace(
            **base,
            expires_at=now - timedelta(seconds=1),
            released_at=None,
        ),
        now,
    )
    released = _hold_read(
        SimpleNamespace(
            **base,
            expires_at=None,
            released_at=now,
        ),
        now,
    )
    assert active.active is True
    assert expired.active is False
    assert released.active is False


def test_api_de_retencao_nao_expoe_execucao_ou_exclusao():
    schema = app.openapi()
    privacy_paths = {
        path: operations
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/privacy/")
    }
    assert "/api/v1/privacy/legal-holds" in privacy_paths
    assert "/api/v1/privacy/retention-reviews/dry-run" in privacy_paths
    assert (
        "/api/v1/privacy/retention-reviews/{review_id}/approve"
        in privacy_paths
    )
    assert all("delete" not in operations for operations in privacy_paths.values())
    assert all("execute" not in path for path in privacy_paths)

    approve = privacy_paths[
        "/api/v1/privacy/retention-reviews/{review_id}/approve"
    ]["post"]
    release = privacy_paths[
        "/api/v1/privacy/legal-holds/{hold_id}/release"
    ]["post"]
    assert approve["requestBody"]["required"] is True
    assert release["requestBody"]["required"] is True


def test_endpoints_limitados_recebem_response_para_headers_do_rate_limit():
    for endpoint in (
        create_legal_hold,
        release_legal_hold,
        create_retention_dry_run,
        approve_retention_review,
    ):
        assert "request" in inspect.signature(endpoint).parameters
        assert "response" in inspect.signature(endpoint).parameters
