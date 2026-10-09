"""Criptografia simétrica dos tokens persistidos da integração."""
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings

def _fernet() -> Fernet:
    if not settings.MOLONI_TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("MOLONI_TOKEN_ENCRYPTION_KEY não configurada")
    return Fernet(settings.MOLONI_TOKEN_ENCRYPTION_KEY.encode())

def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()

def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Token Moloni inválido ou chave de criptografia rotacionada") from exc
