"""Limite real de corpo HTTP, inclusive para Transfer-Encoding chunked."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _RequestBodyTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int, max_mb: int) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.max_mb = max_mb

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers={"Connection": "close"},
        )
        await response(scope, receive, send)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_content_length = headers.get(b"content-length")
        if raw_content_length:
            try:
                announced_size = int(raw_content_length)
            except ValueError:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    detail="Content-Length inválido.",
                )
                return
            if announced_size < 0:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    detail="Content-Length inválido.",
                )
                return
            if announced_size > self.max_bytes:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    detail=(
                        "Corpo da requisição excede o limite permitido "
                        f"de {self.max_mb}MB."
                    ),
                )
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            # Depois do início de uma resposta HTTP já não é possível trocar o
            # status por 413; nesse cenário raro, o servidor encerra a resposta.
            if response_started:
                raise
            await self._reject(
                scope,
                receive,
                send,
                status_code=413,
                detail=(
                    "Corpo da requisição excede o limite permitido "
                    f"de {self.max_mb}MB."
                ),
            )
