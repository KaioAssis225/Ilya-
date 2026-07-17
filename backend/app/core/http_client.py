"""Clientes HTTP compartilhados para evitar abrir uma conexão a cada request."""

import httpx


external_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(5.0, connect=2.0),
    limits=httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    ),
    follow_redirects=False,
)


async def close_http_clients() -> None:
    await external_http_client.aclose()
