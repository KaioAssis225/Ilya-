import asyncio
import io
import uuid

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_sign_invitation_token,
    hash_sign_invitation_token,
    validate_password_strength,
)
from app.core.uploads import read_upload_limited, sanitize_image_upload


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
