"""Envio do PDF de pedido por uma conta pessoal Outlook via Microsoft Graph."""
import base64
import hashlib
from email.utils import parseaddr
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.http_client import external_request
from app.services.resend_client import PermanentEmailError, TemporaryEmailError


# O sendMail aceita anexos pequenos inline. Arquivos maiores exigem criar um
# rascunho e uma upload session, que também requer Mail.ReadWrite.
_MAX_INLINE_ATTACHMENT_BYTES = 3 * 1024 * 1024


def microsoft_graph_configured() -> bool:
    return bool(
        settings.MICROSOFT_GRAPH_CLIENT_ID
        and settings.MICROSOFT_GRAPH_REFRESH_TOKEN
        and settings.MICROSOFT_GRAPH_TENANT
        and settings.MICROSOFT_GRAPH_SENDER_EMAIL
    )


def _raise_for_provider_response(response: httpx.Response) -> None:
    if 200 <= response.status_code < 300:
        return
    if response.status_code in {401, 403}:
        raise TemporaryEmailError("provider_auth")
    if response.status_code in {408, 409, 429} or response.status_code >= 500:
        raise TemporaryEmailError("provider_unavailable")
    if 400 <= response.status_code < 500:
        raise PermanentEmailError("provider_rejected")
    raise TemporaryEmailError("provider_invalid_response")


async def _access_token() -> str:
    tenant = quote(settings.MICROSOFT_GRAPH_TENANT.strip(), safe="")
    try:
        response = await external_request(
            "post",
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            dependency="microsoft_graph",
            data={
                "client_id": settings.MICROSOFT_GRAPH_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": settings.MICROSOFT_GRAPH_REFRESH_TOKEN,
                "scope": "offline_access https://graph.microsoft.com/Mail.Send",
            },
            timeout=settings.ORDER_EMAIL_TIMEOUT_SECONDS,
        )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError):
        raise TemporaryEmailError("provider_unavailable")
    _raise_for_provider_response(response)
    try:
        token = response.json().get("access_token")
    except (ValueError, TypeError):
        token = None
    if not isinstance(token, str) or not token:
        raise TemporaryEmailError("provider_invalid_response")
    return token


async def send_email(
    *,
    idempotency_key: str,
    to: str,
    subject: str,
    text: str,
    html: str,
    attachments: list[dict],
) -> str:
    if not idempotency_key or "\r" in idempotency_key or "\n" in idempotency_key:
        raise PermanentEmailError("invalid_idempotency_key")

    encoded_attachments = []
    for attachment in attachments:
        content = attachment.get("content", b"")
        if not isinstance(content, bytes):
            raise PermanentEmailError("invalid_attachment")
        if len(content) >= _MAX_INLINE_ATTACHMENT_BYTES:
            raise PermanentEmailError("attachment_too_large")
        encoded_attachments.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment["filename"],
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(content).decode("ascii"),
            }
        )

    display_name, _ = parseaddr(settings.ORDER_EMAIL_FROM)
    sender = {"address": settings.MICROSOFT_GRAPH_SENDER_EMAIL}
    if display_name:
        sender["name"] = display_name
    message = {
        "from": {"emailAddress": sender},
        "subject": subject,
        "body": {"contentType": "HTML", "content": html},
        "toRecipients": [{"emailAddress": {"address": to}}],
        "internetMessageHeaders": [
            {"name": "X-Ilya-Idempotency-Key", "value": idempotency_key}
        ],
        "attachments": encoded_attachments,
    }
    if settings.ORDER_EMAIL_REPLY_TO:
        message["replyTo"] = [
            {"emailAddress": {"address": settings.ORDER_EMAIL_REPLY_TO}}
        ]

    token = await _access_token()
    try:
        response = await external_request(
            "post",
            "https://graph.microsoft.com/v1.0/me/sendMail",
            dependency="microsoft_graph",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"message": message, "saveToSentItems": True},
            timeout=settings.ORDER_EMAIL_TIMEOUT_SECONDS,
        )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError):
        raise TemporaryEmailError("provider_unavailable")
    _raise_for_provider_response(response)

    # O endpoint responde 202 sem ID. O valor determinístico permite auditar a
    # aceitação no outbox sem fingir que é um identificador fornecido pelo Graph.
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"graph-accepted:{digest}"
