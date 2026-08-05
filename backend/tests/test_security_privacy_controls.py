import asyncio
import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.api.routers.auth import _anonymize_user_fields, _require_reauthentication
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_sign_invitation_token,
    hash_password,
    hash_sign_invitation_token,
    validate_password_strength,
)
from app.core.privacy_audit import record_privacy_event, request_correlation_id
from app.models.privacy_event import PrivacyEvent
from app.core.uploads import read_upload_limited, sanitize_image_upload
from app.models.representative import Representative, anonymize_representative_fields
from app.schemas.auth import ReauthenticationRequest


def _upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def test_access_token_carrega_versao_de_autenticacao():
    token = create_access_token(uuid.uuid4(), "cliente", auth_version=7)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["ver"] == 7


def test_senha_excessivamente_grande_e_rejeitada_antes_do_argon2():
    with pytest.raises(ValueError, match="no máximo 128"):
        validate_password_strength("A1" + "a" * 127)


def test_token_de_convite_e_opaco_e_hash_nao_revela_valor():
    token = generate_sign_invitation_token()
    token_hash = hash_sign_invitation_token(token)
    assert len(token) >= 32
    assert len(token_hash) == 64
    assert token not in token_hash
    assert token_hash == hash_sign_invitation_token(token)


def test_upload_interrompe_quando_ultrapassa_limite():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            read_upload_limited(
                _upload(b"123456", "dados.csv"),
                5,
                max_size_label="5 bytes",
            )
        )
    assert exc.value.status_code == 413


def test_imagem_e_regravada_sem_metadado_exif():
    source = Image.new("RGB", (8, 8), color="white")
    exif = Image.Exif()
    exif[0x010E] = "identificador pessoal de teste"
    raw = io.BytesIO()
    source.save(raw, format="JPEG", exif=exif)

    sanitized, extension = asyncio.run(
        sanitize_image_upload(
            _upload(raw.getvalue(), "foto.jpg"),
            max_bytes=1024 * 1024,
            max_size_label="1MB",
            allowed_extensions=["jpg", "jpeg", "png", "webp"],
        )
    )

    result = Image.open(io.BytesIO(sanitized))
    assert extension == "jpg"
    assert len(result.getexif()) == 0


def test_operacao_irreversivel_exige_senha_atual():
    user = SimpleNamespace(hashed_password=hash_password("SenhaForte1"))

    _require_reauthentication(
        ReauthenticationRequest(password="SenhaForte1"),
        user,
    )

    with pytest.raises(HTTPException) as exc:
        _require_reauthentication(
            ReauthenticationRequest(password="SenhaErrada1"),
            user,
        )
    assert exc.value.status_code == 401


def test_anonimizacao_remove_identificadores_do_usuario():
    original_hash = hash_password("SenhaForte1")
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="titular@example.com",
        username="titular",
        full_name="Nome do Titular",
        hashed_password=original_hash,
        is_active=True,
        must_change_password=True,
        auth_version=3,
    )

    _anonymize_user_fields(user)

    assert user.email == f"anonimizado_{user.id}@excluido.ilya"
    assert user.username is None
    assert user.full_name == "USUÁRIO ANONIMIZADO"
    assert user.hashed_password != original_hash
    assert user.is_active is False
    assert user.must_change_password is False
    assert user.auth_version == 4


def test_anonimizacao_de_representante_preserva_id_e_remove_pii():
    representative = Representative(
        id=uuid.uuid4(),
        name="Representante Original",
        phone="(19) 99999-9999",
        email="rep@example.com",
        cep="13340-600",
        numero="56,5",
        address="Rodovia de Teste",
        city="Indaiatuba",
        state="SP",
    )
    original_id = representative.id

    anonymize_representative_fields(representative)

    assert representative.id == original_id
    assert representative.name == "REPRESENTANTE ANONIMIZADO"
    assert representative.phone == "(00) 00000-0000"
    assert representative.email == f"anonimizado_{original_id}@excluido.ilya"
    assert representative.cep == "00000-000"
    assert representative.numero is None
    assert representative.address == "ENDEREÇO ANONIMIZADO"
    assert representative.city == "NÃO INFORMADO"
    assert representative.state == "EX"


def test_evento_de_privacidade_registra_apenas_metadados_minimos():
    class FakeSession:
        added = None

        def add(self, value):
            self.added = value

    actor_id = uuid.uuid4()
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-123"))
    db = FakeSession()

    event = record_privacy_event(
        db,
        actor_user_id=actor_id,
        subject_type="client",
        subject_id=uuid.uuid4(),
        action="personal_data_anonymized",
        request=request,
        legal_basis="LGPD Art. 18, IV",
        context={"self_service": True},
    )

    assert isinstance(event, PrivacyEvent)
    assert db.added is event
    assert event.actor_user_id == actor_id
    assert event.request_id == "req-123"
    assert event.context == {"self_service": True}
    assert not hasattr(event, "password")
    assert not hasattr(event, "token")


def test_identificador_de_requisicao_invalido_nao_e_auditado():
    request = SimpleNamespace(
        state=SimpleNamespace(request_id="x" * 65)
    )
    assert request_correlation_id(request) is None
