"""SEC-PRICE-02 — o perfil de faturamento do cliente é resolvido no servidor.

`sanitize_client_update_fields` remove de um PATCH de cliente os campos
comerciais (`price_profile`, `max_discount`) que o papel não pode alterar.
Regressão do achado onde uma conta de portal do cliente-final trocava o próprio
`price_profile` (lojista <-> corporativo) via `PATCH /clients/{proprio_id}`.

Testa a função de autorização diretamente (sem banco), no mesmo estilo de
`test_rbac_authorization.py`.
"""
import uuid
from types import SimpleNamespace

from decimal import Decimal

from app.api.deps import sanitize_client_update_fields
from app.api.routers.clients import sanitize_client_create_fields
from app.models.user import UserRole


def _user(role: UserRole, linked_id=None, rep_id=None) -> SimpleNamespace:
    return SimpleNamespace(role=role, linked_id=linked_id, rep_id=rep_id)


_CLIENT_ID = uuid.uuid4()
CLIENTE_NOVO = _user(UserRole.cliente, linked_id=_CLIENT_ID)
CLIENTE_LEGADO = _user(UserRole.vendedor, linked_id=_CLIENT_ID)  # legado vendedor+linked_id
VENDEDOR_INTERNO = _user(UserRole.vendedor)
REPRESENTANTE = _user(UserRole.representante, rep_id=uuid.uuid4())
ADMIN = _user(UserRole.admin)
CADASTROS = _user(UserRole.cadastros)
PRODUTOS = _user(UserRole.produtos)


def _full_payload() -> dict:
    return {
        "name": "Novo Nome",
        "email": "novo@exemplo.com",
        "price_profile": "corporativo",
        "max_discount": "50.00",
    }


class TestClientePortalNaoAlteraTermosComerciais:
    def test_cliente_novo_nao_muda_price_profile_nem_max_discount(self):
        out = sanitize_client_update_fields(_full_payload(), CLIENTE_NOVO)
        assert "price_profile" not in out  # núcleo do SEC-PRICE-02
        assert "max_discount" not in out
        assert out.get("name") == "Novo Nome"  # dados de contato permanecem

    def test_cliente_legado_vendedor_com_linked_id_tambem_bloqueado(self):
        out = sanitize_client_update_fields(_full_payload(), CLIENTE_LEGADO)
        assert "price_profile" not in out
        assert "max_discount" not in out


class TestRepresentante:
    def test_representante_nao_muda_price_profile_nem_email(self):
        out = sanitize_client_update_fields(_full_payload(), REPRESENTANTE)
        assert "price_profile" not in out
        assert "email" not in out
        assert "max_discount" not in out


class TestOperadoresPrivilegiados:
    def test_admin_mantem_todos_os_campos(self):
        out = sanitize_client_update_fields(_full_payload(), ADMIN)
        assert out.get("price_profile") == "corporativo"
        assert out.get("max_discount") == "50.00"

    def test_cadastros_pode_definir_termos_comerciais(self):
        out = sanitize_client_update_fields(_full_payload(), CADASTROS)
        assert out.get("price_profile") == "corporativo"
        assert out.get("max_discount") == "50.00"

    def test_produtos_pode_definir_termos_comerciais(self):
        out = sanitize_client_update_fields(_full_payload(), PRODUTOS)
        assert out.get("price_profile") == "corporativo"
        assert out.get("max_discount") == "50.00"

    def test_vendedor_interno_define_perfil_mas_nao_max_discount(self):
        # Operador interno mantém o fluxo de definir perfil no cadastro do cliente;
        # max_discount continua restrito a admin/cadastros/produtos.
        out = sanitize_client_update_fields(_full_payload(), VENDEDOR_INTERNO)
        assert out.get("price_profile") == "corporativo"
        assert "max_discount" not in out


class TestCadastroSegueAMesmaRegraDaEdicao:
    """O POST filtrava menos que o PATCH e virava a porta dos fundos.

    Diferente do PATCH, aqui o campo não sai do dict: volta ao default, senão
    `Client(**data)` ficaria sem uma coluna obrigatória.
    """

    def test_representante_nao_nasce_o_cliente_como_corporativo(self):
        out = sanitize_client_create_fields(_full_payload(), REPRESENTANTE)
        assert out["price_profile"] == "lojista"  # núcleo do SEC-PRICE-02
        assert out["max_discount"] == Decimal("0.00")

    def test_conta_de_cliente_final_tambem_bloqueada(self):
        out = sanitize_client_create_fields(_full_payload(), CLIENTE_NOVO)
        assert out["price_profile"] == "lojista"
        assert out["max_discount"] == Decimal("0.00")

    def test_vendedor_interno_define_perfil_mas_nao_teto(self):
        """Mesma assimetria do PATCH, de propósito."""
        out = sanitize_client_create_fields(_full_payload(), VENDEDOR_INTERNO)
        assert out["price_profile"] == "corporativo"
        assert out["max_discount"] == Decimal("0.00")

    def test_papel_comercial_define_os_dois(self):
        for user in (ADMIN, CADASTROS, PRODUTOS):
            out = sanitize_client_create_fields(_full_payload(), user)
            assert out["price_profile"] == "corporativo"
            assert out["max_discount"] == "50.00"
