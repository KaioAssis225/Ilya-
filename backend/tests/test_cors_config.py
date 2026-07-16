import re

from app.core.config import settings


def test_cors_regex_allows_current_vercel_deployment():
    origin = "https://ilya-atyyjocxe-kaioassis225s-projects.vercel.app"
    assert re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)


def test_cors_regex_allows_stable_production_alias():
    origin = "https://ilya-rust.vercel.app"
    assert re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)


def test_cors_regex_rejects_other_vercel_projects():
    origin = "https://outro-projeto-outra-conta.vercel.app"
    assert not re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)


def test_cors_regex_rejects_insecure_http():
    origin = "http://ilya-atyyjocxe-kaioassis225s-projects.vercel.app"
    assert not re.fullmatch(settings.BACKEND_CORS_ORIGIN_REGEX, origin)
