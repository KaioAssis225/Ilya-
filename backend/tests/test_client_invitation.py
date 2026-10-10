"""Convites: segredo não persistido, uso único e vínculo ao destinatário."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import httpx
from fastapi import HTTPException, Response
from sqlalchemy.sql import Select

from app.api.routers import auth, users
from app.api.routers.auth import activate_client
from app.core import client_invites
from app.core.client_invites import client_identity_isolated, generate_invite_token, hash_invite_token
from app.core.config import settings
from app.core.security import verify_password
from app.schemas.auth import ActivateClientRequest
from app.models.user import UserRole


class _Result:
    def __init__(self, value):
        self.value = value

    def one_or_none(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _Session:
    def __init__(self, selected):
        self.selected = iter(selected)
        self.commits = 0
        self.updates = 0

    async def execute(self, statement):
        if isinstance(statement, Select):
            return _Result(next(self.selected))
        self.updates += 1
        return _Result(None)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        return None


def _entities(*, expired=False, recipient="titular@example.com"):
    token = generate_invite_token()
    user_id, client_id, invite_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    candidate = SimpleNamespace(id=invite_id, user_id=user_id)
    user = SimpleNamespace(
        id=user_id, must_change_password=True, is_active=False,
        auth_version=1, failed_login_attempts=2, locked_until=None,
        hashed_password="old-placeholder",
    )
    invitation = SimpleNamespace(
        id=invite_id, user_id=user_id, client_id=client_id,
        market_code="BR", token_hash=hash_invite_token(token),
        recipient_email=recipient, sent_at=datetime.now(timezone.utc),
        consumed_at=None, revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 30),
    )
    client = SimpleNamespace(id=client_id, email="titular@example.com")
    return token, candidate, user, invitation, client


def _activate(token, session):
    return asyncio.run(activate_client.__wrapped__(
        request=None,
        body=ActivateClientRequest(token=token, new_password="NovaSenha123"),
        db=session,
    ))


def test_token_is_random_and_only_hash_is_stored():
    first, second = generate_invite_token(), generate_invite_token()
    assert first != second
    assert len(first) >= 32
    assert len(hash_invite_token(first)) == 64
    assert first not in hash_invite_token(first)


def test_graph_delivery_requires_complete_oauth_configuration(monkeypatch):
    values = {
        "MAIL_DELIVERY_PROVIDER": "microsoft_graph",
        "MICROSOFT_GRAPH_CLIENT_ID": "client-id",
        "MICROSOFT_GRAPH_REFRESH_TOKEN": "refresh-token",
        "MICROSOFT_GRAPH_TENANT": "consumers",
        "MICROSOFT_GRAPH_SENDER_EMAIL": "procgh@outlook.com",
        "CLIENT_INVITE_BASE_URL": "https://app.example.com",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    assert client_invites.invitation_delivery_ready()

    monkeypatch.setattr(settings, "MICROSOFT_GRAPH_REFRESH_TOKEN", "")
    assert not client_invites.invitation_delivery_ready()


def test_graph_sends_invitation_as_delegated_outlook_account(monkeypatch):
    for name, value in {
        "MAIL_DELIVERY_PROVIDER": "microsoft_graph",
        "MICROSOFT_GRAPH_CLIENT_ID": "client-id",
        "MICROSOFT_GRAPH_REFRESH_TOKEN": "refresh-token",
        "MICROSOFT_GRAPH_TENANT": "consumers",
        "MICROSOFT_GRAPH_SENDER_EMAIL": "procgh@outlook.com",
        "CLIENT_INVITE_BASE_URL": "https://app.example.com",
    }.items():
        monkeypatch.setattr(settings, name, value)

    calls = []

    class Client:
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            request = httpx.Request("POST", url)
            if url.endswith("/token"):
                return httpx.Response(200, json={"access_token": "access-token"}, request=request)
            return httpx.Response(202, request=request)

    monkeypatch.setattr(client_invites, "external_http_client", Client())
    asyncio.run(client_invites.send_client_invitation(
        "cliente@example.com", "cliente", "secret-token",
    ))

    token_url, token_request = calls[0]
    assert "/consumers/oauth2/v2.0/token" in token_url
    assert token_request["data"]["refresh_token"] == "refresh-token"
    send_url, send_request = calls[1]
    assert send_url == "https://graph.microsoft.com/v1.0/me/sendMail"
    assert send_request["headers"]["Authorization"] == "Bearer access-token"
    message = send_request["json"]["message"]
    assert message["from"]["emailAddress"]["address"] == "procgh@outlook.com"
    assert message["toRecipients"][0]["emailAddress"]["address"] == "cliente@example.com"
    assert "secret-token" in message["body"]["content"]


def test_graph_does_not_fall_back_to_smtp_when_token_exchange_fails(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_DELIVERY_PROVIDER", "microsoft_graph")
    monkeypatch.setattr(settings, "MICROSOFT_GRAPH_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "MICROSOFT_GRAPH_REFRESH_TOKEN", "invalid")
    monkeypatch.setattr(settings, "MICROSOFT_GRAPH_TENANT", "consumers")

    class Client:
        async def post(self, url, **_kwargs):
            return httpx.Response(401, request=httpx.Request("POST", url))

    monkeypatch.setattr(client_invites, "external_http_client", Client())
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client_invites.send_client_invitation(
            "cliente@example.com", "cliente", "secret-token",
        ))


def test_invite_cannot_reset_operator_or_platform_identity():
    identity = SimpleNamespace(id=uuid.uuid4(), role=UserRole.cliente)
    assert asyncio.run(client_identity_isolated(_Session([None, None]), identity))
    assert not asyncio.run(client_identity_isolated(_Session([identity.id, None]), identity))
    assert not asyncio.run(client_identity_isolated(_Session([None, identity.id]), identity))
    identity.role = UserRole.admin
    assert not asyncio.run(client_identity_isolated(_Session([]), identity))


def test_invitation_activates_once_and_revokes_prior_sessions(monkeypatch):
    async def isolated(*_args):
        return True
    monkeypatch.setattr(auth, "client_identity_isolated", isolated)
    token, candidate, user, invitation, client = _entities()
    session = _Session([candidate, user, invitation, user.id, client])
    _activate(token, session)
    assert session.commits == 1
    assert session.updates == 2  # sessões anteriores e outros convites
    assert invitation.consumed_at is not None
    assert user.is_active and not user.must_change_password
    assert user.auth_version == 2
    assert verify_password("NovaSenha123", user.hashed_password)

    replay = _Session([candidate, user, invitation])
    with pytest.raises(HTTPException) as rejected:
        _activate(token, replay)
    assert rejected.value.status_code == 400
    assert replay.commits == 0


def test_expired_or_changed_recipient_cannot_activate(monkeypatch):
    async def isolated(*_args):
        return True
    monkeypatch.setattr(auth, "client_identity_isolated", isolated)
    for expired, recipient in ((True, "titular@example.com"), (False, "outro@example.com")):
        token, candidate, user, invitation, client = _entities(
            expired=expired, recipient=recipient,
        )
        session = _Session([candidate, user, invitation, user.id, client])
        with pytest.raises(HTTPException) as rejected:
            _activate(token, session)
        assert rejected.value.status_code == 400
        assert session.commits == 0
        assert not user.is_active


def test_client_login_records_activity_and_creates_session(monkeypatch):
    user_id, client_id = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(
        id=user_id, role=SimpleNamespace(value="cliente"),
        home_market="BR", auth_version=1,
    )
    access = SimpleNamespace(
        market_code="BR", role="cliente", linked_client_id=client_id,
    )
    touched = []

    async def authenticate(*_args):
        return user

    async def accesses(*_args):
        return [access]

    async def touch(_db, selected_client_id):
        touched.append(selected_client_id)

    class Session:
        def __init__(self):
            self.added = []
            self.commits = 0

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commits += 1

    monkeypatch.setattr(auth, "_authenticate_credentials", authenticate)
    monkeypatch.setattr(auth, "allowed_market_accesses", accesses)
    monkeypatch.setattr(auth, "touch_client_activity", touch)
    session = Session()
    response = Response()
    result = asyncio.run(auth.login.__wrapped__(
        request=None, response=response, payload=None, db=session,
    ))
    assert result.access_token
    assert touched == [client_id]
    assert len(session.added) == 1
    assert session.commits == 1
    assert "ilya_refresh=" in response.headers["set-cookie"]


def test_admin_invite_returns_no_secret_and_records_verified_recipient(monkeypatch):
    client_id, user_id, admin_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    client = SimpleNamespace(
        id=client_id, market_code="BR", email="titular@example.com",
    )
    user = SimpleNamespace(
        id=user_id, username="titular", is_active=False,
        must_change_password=True, auth_version=1,
        client_access_requested_by_user_id=uuid.uuid4(),
    )
    principal = SimpleNamespace(
        code="BR", actor=SimpleNamespace(role=UserRole.admin),
        user=SimpleNamespace(id=admin_id),
    )
    session = _Session([client, user_id, user, None])
    session.added = []
    session.add = session.added.append
    delivered = []

    async def send(recipient, username, token):
        delivered.append((recipient, username, token))

    async def isolated(*_args):
        return True

    monkeypatch.setattr(users, "invitation_delivery_ready", lambda: True)
    monkeypatch.setattr(users, "send_client_invitation", send)
    monkeypatch.setattr(users, "client_identity_isolated", isolated)
    body = users.ClientInviteIssue(
        confirmed_email="titular@example.com",
        verification_method="phone_callback",
    )
    result = asyncio.run(users.issue_client_invitation(
        client_id, body, db=session, principal=principal,
    ))
    assert result == {"status": "sent", "recipient_email": "titular@example.com"}
    assert len(delivered) == 1
    assert delivered[0][:2] == ("titular@example.com", "titular")
    invitation = session.added[0]
    assert invitation.token_hash == hash_invite_token(delivered[0][2])
    assert invitation.verified_by_user_id == admin_id
    assert invitation.sent_at is not None
    assert delivered[0][2] not in str(result)
    assert session.commits == 1


def test_representative_creates_only_inactive_client_account(monkeypatch):
    client_id, rep_id = uuid.uuid4(), uuid.uuid4()
    client = SimpleNamespace(
        id=client_id, name="Cliente Teste", rep_id=rep_id,
        market_code="BR",
    )
    current = SimpleNamespace(
        id=uuid.uuid4(), role=UserRole.representante, rep_id=rep_id,
    )
    session = _Session([client, None])
    session.added = []
    session.add = session.added.append

    async def username(*_args):
        return "cliente-teste"

    async def refresh(user):
        user.id = uuid.uuid4()

    session.refresh = refresh
    monkeypatch.setattr(users, "_resolve_unique_username", username)
    result = asyncio.run(users.create_user_from_client(
        client_id, db=session, current=current,
    ))
    created = session.added[0]
    assert not created.is_active
    assert created.must_change_password
    assert created.client_access_requested_by_user_id == current.id
    assert result.username == "cliente-teste"
    assert "password" not in result.model_dump()
    assert "token" not in result.model_dump()
