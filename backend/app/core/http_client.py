"""Clientes HTTP compartilhados para evitar abrir uma conexão a cada request."""

import httpx

from app.core.observability import external_exception, httpx_event_hooks


external_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(5.0, connect=2.0),
    limits=httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    ),
    follow_redirects=False,
    event_hooks=httpx_event_hooks(),
)


async def external_request(method: str, url: str, *, dependency: str, client=None, **kwargs) -> httpx.Response:
    """Chamada pelo cliente compartilhado com dependência em allowlist.

    URL, parâmetros, headers e corpo nunca viram rótulos ou logs.
    """
    extensions = dict(kwargs.pop("extensions", {}))
    extensions["ilya_dependency"] = dependency
    selected_client = client or external_http_client
    try:
        request_method = getattr(selected_client, method.lower())
        return await request_method(url, extensions=extensions, **kwargs)
    except httpx.HTTPError as exc:
        external_exception(exc)
        raise


async def close_http_clients() -> None:
    await external_http_client.aclose()
