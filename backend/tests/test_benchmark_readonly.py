"""P11: limites do papel técnico, a executar no checkpoint."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from app.api.deps import (
    _enforce_readonly_canary,
    require_dashboard_access,
    require_order_access,
)
from app.api.routers.users import _build_market_links
from app.models.user import UserRole
from app.schemas.auth import UserMarketAccessInput


def _principal(*, market="BR", links=None):
    if links is None:
        links = [SimpleNamespace(
            market_code=market, can_approve_tax=False,
            linked_client_id=None, rep_id=None,
        )]
    actor = SimpleNamespace(role=UserRole.benchmark_readonly, can_view_dashboard=False,
                            linked_id=None, rep_id=None)
    return SimpleNamespace(
        actor=actor, user=SimpleNamespace(role=UserRole.benchmark_readonly,
                                         allowed_market_links=links), code=market,
    )


def _request(method, template):
    return Request({
        "type": "http", "method": method, "path": template,
        "headers": [], "query_string": b"", "route": SimpleNamespace(path=template),
    })


@pytest.mark.parametrize("template", [
    "/api/v1/auth/me", "/api/v1/products", "/api/v1/products/{product_id}",
    "/api/v1/orders", "/api/v1/orders/{id_or_code}",
    "/api/v1/dashboard/overview",
])
def test_only_whitelisted_reads_are_allowed(template):
    _enforce_readonly_canary(_principal(), _request("GET", template))


@pytest.mark.parametrize("method,template", [
    ("POST", "/api/v1/orders"),
    ("PATCH", "/api/v1/products/{product_id}"),
    ("POST", "/api/v1/auth/switch-market"),
    ("DELETE", "/api/v1/auth/me"),
    ("GET", "/api/v1/clients"),
    ("GET", "/api/v1/auth/sessions"),
])
def test_mutations_and_extra_reads_are_forbidden(method, template):
    with pytest.raises(HTTPException) as exc:
        _enforce_readonly_canary(_principal(), _request(method, template))
    assert exc.value.status_code == 403


def test_market_link_must_be_unique_and_without_tax_capability():
    br = SimpleNamespace(market_code="BR", can_approve_tax=False,
                         linked_client_id=None, rep_id=None)
    eu = SimpleNamespace(market_code="EU", can_approve_tax=False,
                         linked_client_id=None, rep_id=None)
    with pytest.raises(HTTPException) as exc:
        _enforce_readonly_canary(_principal(links=[br, eu]), _request("GET", "/api/v1/orders"))
    assert exc.value.status_code == 403
    br.can_approve_tax = True
    with pytest.raises(HTTPException):
        _enforce_readonly_canary(_principal(links=[br]), _request("GET", "/api/v1/orders"))


def test_order_and_dashboard_guards_admit_only_explicit_canary_role():
    actor = _principal().actor
    assert require_order_access(current_user=actor) is actor
    assert require_dashboard_access(current_user=actor) is actor


def test_provisioning_rejects_second_market_and_tax_capability():
    br = UserMarketAccessInput(
        market_code="BR", role=UserRole.benchmark_readonly, status="active",
    )
    eu = UserMarketAccessInput(
        market_code="EU", role=UserRole.benchmark_readonly, status="active",
    )
    links = asyncio.run(_build_market_links([br], None))
    assert len(links) == 1 and links[0].role == "benchmark_readonly"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_build_market_links([br, eu], None))
    assert exc.value.status_code == 422
    br.can_approve_tax = True
    with pytest.raises(HTTPException):
        asyncio.run(_build_market_links([br], None))
