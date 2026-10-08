import asyncio
import hashlib
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.http_client import external_http_client
from app.models.market import UserMarket, UserPlatformPermission
from app.models.user import User, UserRole


async def client_identity_isolated(db: AsyncSession, user: User) -> bool:
    """Um convite de cliente não pode redefinir senha de operador ou plataforma."""
    if user.role not in (UserRole.cliente, UserRole.vendedor):
        return False
    other_market_role = (await db.execute(select(UserMarket.user_id).where(
        UserMarket.user_id == user.id,
        UserMarket.role != UserRole.cliente.value,
        UserMarket.status == "active",
    ).limit(1))).scalar_one_or_none()
    platform_permission = (await db.execute(select(UserPlatformPermission.user_id).where(
        UserPlatformPermission.user_id == user.id,
        UserPlatformPermission.is_active.is_(True),
    ).limit(1))).scalar_one_or_none()
    return other_market_role is None and platform_permission is None


def generate_invite_token() -> str:
    return secrets.token_urlsafe(48)


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invite_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.CLIENT_INVITE_TTL_MINUTES)


def invitation_delivery_ready() -> bool:
    base = urlsplit(settings.CLIENT_INVITE_BASE_URL)
    provider = settings.MAIL_DELIVERY_PROVIDER.strip().lower()
    if provider == "microsoft_graph":
        delivery_configured = bool(
            settings.MICROSOFT_GRAPH_CLIENT_ID
            and settings.MICROSOFT_GRAPH_REFRESH_TOKEN
            and settings.MICROSOFT_GRAPH_TENANT
            and settings.MICROSOFT_GRAPH_SENDER_EMAIL
        )
    elif provider == "smtp":
        delivery_configured = bool(
            settings.SMTP_HOST
            and settings.SMTP_PORT > 0
            and settings.SMTP_USERNAME
            and settings.SMTP_PASSWORD
            and settings.SMTP_FROM_EMAIL
        )
    else:
        return False
    return bool(
        delivery_configured
        and settings.CLIENT_INVITE_TTL_MINUTES > 0
        and (base.scheme == "https" or (settings.DEBUG and base.scheme == "http"))
        and base.netloc
        and not base.query
        and not base.fragment
    )


def _invitation_body(username: str, token: str) -> str:
    link = (
        settings.CLIENT_INVITE_BASE_URL.rstrip("/")
        + "/ativar-conta#token=" + quote(token, safe="")
    )
    return (
        "Um administrador confirmou este endereço para a sua conta Ilya.\n\n"
        f"Usuário: {username}\n"
        f"Defina sua senha pelo link: {link}\n\n"
        f"O convite expira em {settings.CLIENT_INVITE_TTL_MINUTES} minutos e só pode ser usado uma vez.\n"
        "Se você não solicitou acesso, ignore esta mensagem."
    )


def _signature_body(order_code: str, token: str) -> str:
    link = settings.CLIENT_INVITE_BASE_URL.rstrip("/") + "/sign-contract#" + quote(token, safe="")
    return (
        f"O pedido {order_code} aguarda sua assinatura. Revise os termos antes de assinar.\n\n"
        f"Link: {link}\n\nEste link é de uso único e expira em breve. "
        "Se você não reconhece o pedido, ignore esta mensagem."
    )


def _send_smtp(recipient: str, username: str, token: str) -> None:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = "Defina sua senha de acesso ao Ilya"
    message.set_content(_invitation_body(username, token))
    context = ssl.create_default_context()
    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10, context=context) as smtp:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)


async def send_client_invitation(recipient: str, username: str, token: str) -> None:
    if settings.MAIL_DELIVERY_PROVIDER.strip().lower() == "microsoft_graph":
        await _send_graph(
            recipient,
            "Defina sua senha de acesso ao Ilya",
            _invitation_body(username, token),
        )
        return
    await asyncio.to_thread(_send_smtp, recipient, username, token)


def _send_signature_smtp(recipient: str, order_code: str, token: str) -> None:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = "Assinatura do pedido Ilya"
    message.set_content(_signature_body(order_code, token))
    context = ssl.create_default_context()
    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10, context=context) as smtp:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)


async def send_signature_invitation(recipient: str, order_code: str, token: str) -> None:
    if settings.MAIL_DELIVERY_PROVIDER.strip().lower() == "microsoft_graph":
        await _send_graph(
            recipient,
            "Assinatura do pedido Ilya",
            _signature_body(order_code, token),
        )
        return
    await asyncio.to_thread(_send_signature_smtp, recipient, order_code, token)


async def _send_graph(recipient: str, subject: str, body: str) -> None:
    tenant = quote(settings.MICROSOFT_GRAPH_TENANT.strip(), safe="")
    token_response = await external_http_client.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": settings.MICROSOFT_GRAPH_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": settings.MICROSOFT_GRAPH_REFRESH_TOKEN,
            "scope": "offline_access https://graph.microsoft.com/Mail.Send",
        },
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise httpx.HTTPError("Microsoft token response did not include an access token")

    response = await external_http_client.post(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "message": {
                "from": {
                    "emailAddress": {
                        "address": settings.MICROSOFT_GRAPH_SENDER_EMAIL,
                    },
                },
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [
                    {"emailAddress": {"address": recipient}},
                ],
            },
            "saveToSentItems": True,
        },
    )
    response.raise_for_status()
