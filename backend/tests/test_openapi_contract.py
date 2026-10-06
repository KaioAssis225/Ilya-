from app.core.config import settings
from app.main import app


def test_openapi_schema_can_be_generated_without_unresolved_annotations():
    schema = app.openapi()

    assert "/api/v1/integrations/test-event" in schema["paths"]
    assert "TestEventRequest" in schema["components"]["schemas"]


def test_openapi_exposes_separate_platform_session_endpoints():
    schema = app.openapi()
    assert "/api/v1/platform/auth/login" in schema["paths"]
    assert "/api/v1/platform/auth/refresh" in schema["paths"]
    assert "/api/v1/platform/auth/logout" in schema["paths"]
    assert "/api/v1/platform/auth/me" in schema["paths"]


def test_openapi_exposes_platform_preparation_and_access_management():
    schema = app.openapi()
    assert "/api/v1/products/platform/EU" in schema["paths"]
    assert "/api/v1/products/platform/EU/{product_id}" in schema["paths"]
    assert "/api/v1/products/platform/EU/{product_id}/upload-photo" in schema["paths"]
    assert "/api/v1/users/{user_id}/platform-permissions" in schema["paths"]


def test_openapi_http_endpoint_is_disabled_outside_debug_mode():
    if not settings.DEBUG:
        assert app.openapi_url is None


def test_irreversible_privacy_actions_require_password_body():
    schema = app.openapi()

    delete_operation = schema["paths"]["/api/v1/auth/me"]["delete"]
    anonymize_operation = schema["paths"]["/api/v1/auth/anonymize"]["post"]

    assert "requestBody" in delete_operation
    assert delete_operation["requestBody"]["required"] is True
    assert "requestBody" in anonymize_operation
    assert anonymize_operation["requestBody"]["required"] is True


def test_admin_can_anonymize_client_and_representative_records():
    schema = app.openapi()
    assert "/api/v1/clients/{client_id}/anonymize" in schema["paths"]
    assert (
        "/api/v1/representatives/{rep_id}/anonymize"
        in schema["paths"]
    )
