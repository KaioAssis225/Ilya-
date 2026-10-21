import re

from app.core.config import settings

# Nome de projeto que qualquer conta Vercel pode registrar: o domínio padrão
# de produção de um projeto é `<nome-do-projeto>.vercel.app`, então um padrão
# sobre `*.vercel.app` não prova que o deployment pertence ao time do Ilya.
_SQUATTABLE_PROJECT_ORIGIN = "https://ilya-mantis-kaioassis225s-projects.vercel.app"


def test_cors_regex_allows_stable_production_alias():
    origin = "https://ilya-rust.vercel.app"
    assert re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)


def test_cors_regex_rejects_attacker_registrable_project_name():
    assert not re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, _SQUATTABLE_PROJECT_ORIGIN)


def test_cors_regex_rejects_vercel_deployment_preview():
    # Mesmo formato de um preview legítimo; indistinguível de um nome
    # registrado por terceiros, por isso fora da allowlist padrão.
    origin = "https://ilya-atyyjocxe-kaioassis225s-projects.vercel.app"
    assert not re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)


def test_cors_regex_rejects_vercel_branch_preview():
    origin = (
        "https://ilya-git-fix-seguranca-revisao-in-38f70e-"
        "kaioassis225s-projects.vercel.app"
    )
    assert not re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)


def test_cors_regex_rejects_other_vercel_projects():
    origin = "https://outro-projeto-outra-conta.vercel.app"
    assert not re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)


def test_cors_regex_rejects_insecure_http():
    origin = "http://ilya-rust.vercel.app"
    assert not re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)
