"""Configuração compartilhada da suíte pytest.

Aplica marcadores automaticamente sem alterar a lógica dos testes existentes.

Regras de classificação (em ordem de precedência):
1. Marcador explícito no item (pytestmark ou @pytest.mark.*) → preservado.
2. Caminho contém um segmento "integration" → integration.
3. Arquivo pertence ao conjunto de contratos do baseline P01 → contract.
4. Demais → unit.

Para novos testes de contrato, adicione ``pytestmark = pytest.mark.contract``
ao módulo em vez de editar esta lista; para integração, coloque em
``tests/integration/``.
"""
import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Define env vars mínimas antes de qualquer import de módulo app."""
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-32bytes!!")
    os.environ.setdefault("PASSWORD_PEPPER", "test-pepper-for-pytest")

# Arquivos do baseline que são contrato HTTP/schema mas não adotam ainda a
# convenção de pytestmark. Novos arquivos NÃO precisam entrar aqui.
_LEGACY_CONTRACT_FILES = {
    "test_auth_csrf.py",        # 100% TestClient — CSRF em refresh/logout
    "test_openapi_contract.py", # verifica schema OpenAPI gerado pela app
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if (
            item.get_closest_marker("unit") is not None
            or item.get_closest_marker("contract") is not None
            or item.get_closest_marker("integration") is not None
        ):
            continue  # preserva marcadores explícitos

        path_parts = item.nodeid.replace("\\", "/").split("/")
        filename = path_parts[-1].split("::")[0]

        if "integration" in path_parts[:-1]:
            item.add_marker(pytest.mark.integration)
        elif filename in _LEGACY_CONTRACT_FILES:
            item.add_marker(pytest.mark.contract)
        else:
            item.add_marker(pytest.mark.unit)
