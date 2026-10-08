import asyncio
import hashlib
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote, urlsplit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_PORT > 0
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
        and settings.SMTP_FROM_EMAIL
        and settings.CLIENT_INVITE_TTL_MINUTES > 0
        and (base.scheme == "https" or (settings.DEBUG and base.scheme == "http"))
        and base.netloc
        and not base.query
        and not base.fragment
    )


def _send_smtp(recipient: str, username: str, token: str) -> None:
    link = (
        settings.CLIENT_INVITE_BASE_URL.rstrip("/")
        + "/ativar-conta#token=" + quote(token, safe="")
    )
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = "Defina sua senha de acesso ao Ilya"
    message.set_content(
        "Um administrador confirmou este endereço para a sua conta Ilya.\n\n"
        f"Usuário: {username}\n"
        f"Defina sua senha pelo link: {link}\n\n"
        f"O convite expira em {settings.CLIENT_INVITE_TTL_MINUTES} minutos e só pode ser usado uma vez.\n"
        "Se você não solicitou acesso, ignore esta mensagem."
    )
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
    await asyncio.to_thread(_send_smtp, recipient, username, token)


def _send_signature_smtp(recipient: str, order_code: str, token: str) -> None:
    link = settings.CLIENT_INVITE_BASE_URL.rstrip("/") + "/sign-contract#" + quote(token, safe="")
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = "Assinatura do pedido Ilya"
    message.set_content(
        f"O pedido {order_code} aguarda sua assinatura. Revise os termos antes de assinar.\n\n"
        f"Link: {link}\n\nEste link é de uso único e expira em breve. "
        "Se você não reconhece o pedido, ignore esta mensagem."
    )
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
    await asyncio.to_thread(_send_signature_smtp, recipient, order_code, token)
