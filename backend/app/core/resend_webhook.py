"""Verifica assinaturas Svix do webhook Resend sobre o corpo cru."""
import base64
import binascii
import hashlib
import hmac

from app.core.webhook_signature import MAX_TIMESTAMP_SKEW_SECONDS, timestamp_is_fresh


def verify_resend_signature(
    secret: str,
    svix_id: str,
    svix_timestamp: str,
    body: bytes,
    signatures: str,
) -> bool:
    if not secret.startswith("whsec_") or not svix_id or not signatures:
        return False
    if not timestamp_is_fresh(
        svix_timestamp, max_skew_seconds=MAX_TIMESTAMP_SKEW_SECONDS
    ):
        return False
    try:
        key = base64.b64decode(secret[6:], validate=True)
    except (ValueError, binascii.Error):
        return False
    if not key:
        return False
    signed = (
        svix_id.encode("utf-8")
        + b"."
        + svix_timestamp.encode("utf-8")
        + b"."
        + body
    )
    expected = base64.b64encode(
        hmac.new(key, signed, hashlib.sha256).digest()
    ).decode("ascii")
    for candidate in signatures.split():
        version, separator, value = candidate.partition(",")
        if version == "v1" and separator and hmac.compare_digest(expected, value):
            return True
    return False
