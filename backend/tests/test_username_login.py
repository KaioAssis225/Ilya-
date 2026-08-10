"""Login escolhido pelo admin (`username`) na criação de usuário.

O login compara o identificador já em minúsculas contra `users.username`
(auth.login), então o schema precisa normalizar e recusar formatos que
seriam impossíveis de digitar ou que se confundiriam com um e-mail.
"""
import pytest
from pydantic import ValidationError

from app.schemas.auth import UserCreate, UserUpdate

BASE = {
    "email": "rep@empresa.com.br",
    "password": "Green@01",
    "full_name": "Fulano de Tal",
    "role": "representante",
}


def _build(**extra):
    return UserCreate(**{**BASE, **extra})


def test_username_ausente_continua_valido():
    """Contas antigas entram só pelo e-mail — comportamento preservado."""
    assert _build().username is None


def test_username_normaliza_para_minusculas():
    assert _build(username="LeandroDeSantos").username == "leandrodesantos"


def test_username_remove_espacos_das_pontas():
    assert _build(username="  cr1representacoes  ").username == "cr1representacoes"


def test_username_vazio_vira_none():
    assert _build(username="   ").username is None


def test_username_aceita_ponto_hifen_e_sublinhado():
    assert _build(username="flp.representacoes-01_br").username == "flp.representacoes-01_br"


@pytest.mark.parametrize(
    "invalido",
    [
        "ab",                      # curto demais
        "com espaco",              # espaço não é digitável no login
        "rep@empresa.com",         # pareceria um e-mail
        "acentuação",              # acento quebraria a digitação
        "rep/barra",
        "x" * 101,                 # acima do limite da coluna (String(100))
    ],
)
def test_username_invalido_e_recusado(invalido):
    with pytest.raises(ValidationError):
        _build(username=invalido)


def test_username_pode_ser_corrigido_pelo_admin():
    update = UserUpdate(username="  FLPRepresentacoes  ")

    assert update.username == "flprepresentacoes"


@pytest.mark.parametrize("invalido", ["", "ab", "com espaco", "rep@empresa.com"])
def test_correcao_de_username_invalida_e_recusada(invalido):
    with pytest.raises(ValidationError):
        UserUpdate(username=invalido)
