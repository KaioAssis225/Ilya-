import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.api.routers.clients import _with_metadata
from app.models.client import Client


def test_client_read_includes_creator_name_when_authorized():
    creator_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    client = Client(
        id=uuid.uuid4(),
        name="Cliente teste",
        phone="(11) 99999-9999",
        email=None,
        cep="01001-000",
        numero=None,
        address="Praça da Sé",
        city="São Paulo",
        state="SP",
        price_profile="lojista",
        max_discount=Decimal("0.00"),
        rep_id=None,
        created_by_user_id=creator_id,
    )
    client.created_at = now
    client.updated_at = now

    result = _with_metadata(
        client,
        {},
        {creator_id: "Usuário Criador"},
    )

    assert result.email is None
    assert result.created_by_name == "Usuário Criador"
