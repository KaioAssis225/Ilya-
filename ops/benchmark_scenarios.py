"""Catálogo fechado de leituras do benchmark Ilya (P11).

O mercado é escolhido pelo token, nunca por um parâmetro de URL. Códigos de
fixtures são configurados no ambiente de homologação e não entram no relatório.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    route_template: str
    path: str
    expected_status: int = 200
    requires_auth: bool = True


@dataclass(frozen=True)
class FixtureScenario:
    name: str
    route_template: str
    collection_path: str
    code_field: str
    code_env: str
    detail_path: str


PUBLIC_SCENARIOS = (
    BenchmarkScenario("health_live", "GET /health/live", "/api/v1/health/live", requires_auth=False),
    BenchmarkScenario("health_ready", "GET /health/ready", "/api/v1/health/ready", requires_auth=False),
)

AUTH_SCENARIOS = (
    BenchmarkScenario("auth_me", "GET /auth/me", "/api/v1/auth/me"),
)

COMMERCIAL_SCENARIOS = (
    BenchmarkScenario("products_list_no_total", "GET /products", "/api/v1/products?limit=20&include_total=false"),
    BenchmarkScenario("products_list_with_total", "GET /products", "/api/v1/products?limit=20&include_total=true"),
    BenchmarkScenario("orders_list", "GET /orders", "/api/v1/orders?limit=20"),
    BenchmarkScenario("dashboard_overview", "GET /dashboard/overview", "/api/v1/dashboard/overview?ranking_limit=5"),
)

FIXTURE_SCENARIOS = (
    FixtureScenario("product_detail", "GET /products/{product_id}",
                    "/api/v1/products", "product_code", "ILYA_BENCHMARK_PRODUCT_CODE",
                    "/api/v1/products/{fixture_id}"),
    FixtureScenario("order_detail", "GET /orders/{id_or_code}",
                    "/api/v1/orders", "code", "ILYA_BENCHMARK_ORDER_CODE",
                    "/api/v1/orders/{fixture_id}"),
)


def select_scenarios(*, authenticated: bool, commercial: bool = False) -> tuple[BenchmarkScenario, ...]:
    if commercial and not authenticated:
        raise ValueError("Cenários comerciais exigem autenticação técnica.")
    return PUBLIC_SCENARIOS + (AUTH_SCENARIOS if authenticated else ()) + (
        COMMERCIAL_SCENARIOS if commercial else ()
    )
