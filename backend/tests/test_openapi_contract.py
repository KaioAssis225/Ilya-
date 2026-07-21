from app.core.config import settings
from app.main import app


def test_openapi_schema_can_be_generated_without_unresolved_annotations():
    schema = app.openapi()

    assert "/api/v1/integrations/test-event" in schema["paths"]
    assert "TestEventRequest" in schema["components"]["schemas"]


def test_openapi_http_endpoint_is_disabled_outside_debug_mode():
    if not settings.DEBUG:
        assert app.openapi_url is None
