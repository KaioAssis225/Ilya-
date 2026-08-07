"""Limites de auth sob NAT compartilhado (feira/showroom).

Toda a equipe comercial sai pelo mesmo IP público num evento. Se o limite
de renovação de sessão for por IP, poucas renovações simultâneas derrubam
a sessão dos colegas — por isso o /auth/refresh é limitado por sessão.
"""
from types import SimpleNamespace

from app.core.config import settings
from app.core.limiter import rate_limit_key, refresh_rate_limit_key


def _request(cookies=None, headers=None, host="200.100.50.10"):
    return SimpleNamespace(
        cookies=cookies or {},
        headers=headers or {},
        client=SimpleNamespace(host=host),
        scope={"client": (host, 12345), "headers": []},
    )


def test_refresh_de_sessoes_distintas_nao_compartilha_balde():
    """Dois representantes no mesmo Wi-Fi têm chaves diferentes."""
    a = refresh_rate_limit_key(_request(cookies={"ilya_refresh": "token-do-leandro"}))
    b = refresh_rate_limit_key(_request(cookies={"ilya_refresh": "token-da-dayane"}))
    assert a != b
    assert a.startswith("session:") and b.startswith("session:")


def test_refresh_da_mesma_sessao_mantem_a_chave():
    """A mesma sessão continua contida pelo limite."""
    req = _request(cookies={"ilya_refresh": "token-estavel"})
    assert refresh_rate_limit_key(req) == refresh_rate_limit_key(req)


def test_refresh_nao_vaza_o_token_na_chave():
    """A chave vai para o Redis — não pode carregar o refresh token em claro."""
    chave = refresh_rate_limit_key(_request(cookies={"ilya_refresh": "segredo-do-cookie"}))
    assert "segredo-do-cookie" not in chave


def test_refresh_sem_cookie_cai_para_o_ip():
    chave = refresh_rate_limit_key(_request())
    assert chave.startswith("ip:")


def test_login_continua_por_ip():
    """Login é anônimo: sem Authorization, a contenção por IP é o que resta."""
    assert rate_limit_key(_request()).startswith("ip:")


def test_limite_de_login_comporta_uma_equipe_inteira():
    """8 representantes + erros de digitação não podem estourar a janela."""
    quantidade, _, janela = settings.RATE_LIMIT_LOGIN.partition("/")
    assert int(quantidade) >= 20, (
        f"RATE_LIMIT_LOGIN={settings.RATE_LIMIT_LOGIN} bloquearia a equipe "
        "atrás de um único IP em evento"
    )
    assert janela == "15minute"
