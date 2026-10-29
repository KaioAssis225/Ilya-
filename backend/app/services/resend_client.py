"""Cliente HTTP mínimo do Resend, sem SDK e sem dados sensíveis em erros."""
import base64
import html as html_module
import re

import httpx

from app.core.config import settings
from app.core.http_client import external_request


_MAX_ATTACHMENT_BYTES = 35 * 1024 * 1024


class EmailDeliveryError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class TemporaryEmailError(EmailDeliveryError):
    pass


class PermanentEmailError(EmailDeliveryError):
    pass


def sanitize_attachment_filename(order_code: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", order_code).strip("._")
    return f"{safe or 'pedido'}.pdf"


def build_order_email(snapshot: dict, pdf: bytes) -> dict:
    order = snapshot["order"]
    locale = str(snapshot.get("locale") or order.get("locale") or "pt-BR")
    portuguese = locale.lower().startswith("pt-")
    brand = "IBTW Living" if order.get("market_code") == "EU" else "Ilya"
    code = str(order["code"])
    if portuguese:
        subject = f"{brand} | Pedido {code}"
        text = (
            f"Obrigado pelo seu pedido. Segue em anexo o PDF do pedido {code}. "
            "Para falar conosco, responda a este e-mail."
        )
    else:
        subject = f"{brand} | Order {code}"
        text = (
            f"Thank you for your order. The PDF for order {code} is attached. "
            "Reply to this email to contact our commercial team."
        )
    return {
        "subject": subject,
        "text": text,
        "html": f"<p>{html_module.escape(text)}</p>",
        "attachments": [
            {"filename": sanitize_attachment_filename(code), "content": pdf}
        ],
    }


async def send_email(
    *,
    idempotency_key: str,
    to: str,
    subject: str,
    text: str,
    html: str,
    attachments: list[dict],
) -> str:
    encoded_attachments = []
    for attachment in attachments:
        content = attachment.get("content", b"")
        if not isinstance(content, bytes):
            raise PermanentEmailError("invalid_attachment")
        if len(content) > _MAX_ATTACHMENT_BYTES:
            raise PermanentEmailError("attachment_too_large")
        encoded_attachments.append(
            {
                "filename": attachment["filename"],
                "content": base64.b64encode(content).decode("ascii"),
            }
        )
    payload = {
        "from": settings.ORDER_EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "text": text,
        "html": html,
        "attachments": encoded_attachments,
    }
    if settings.ORDER_EMAIL_REPLY_TO:
        payload["reply_to"] = settings.ORDER_EMAIL_REPLY_TO
    try:
        response = await external_request(
            "post",
            f"{settings.RESEND_API_BASE_URL.rstrip('/')}/emails",
            dependency="resend",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Idempotency-Key": idempotency_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.ORDER_EMAIL_TIMEOUT_SECONDS,
        )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError):
        raise TemporaryEmailError("provider_unavailable")

    if 200 <= response.status_code < 300:
        try:
            message_id = response.json().get("id")
        except (ValueError, TypeError):
            message_id = None
        if isinstance(message_id, str) and message_id:
            return message_id
        raise TemporaryEmailError("provider_invalid_response")
    if response.status_code in {401, 403}:
        raise TemporaryEmailError("provider_auth")
    if response.status_code in {409, 429} or response.status_code >= 500:
        raise TemporaryEmailError("provider_unavailable")
    if 400 <= response.status_code < 500:
        raise PermanentEmailError("provider_rejected")
    raise TemporaryEmailError("provider_invalid_response")
