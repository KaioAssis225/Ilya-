from .markets import market_defaults, require_market
from .users import make_user, make_user_market, make_platform_permission
from .catalog import make_catalog, make_price_list, make_client, make_representative
from .products import (
    make_product_group,
    make_product_type,
    make_product,
    make_product_market,
    make_product_price,
)
from .optionals import make_optional_category, make_optional, make_application

__all__ = [
    # Defaults e helpers de mercado
    "market_defaults",
    "require_market",
    # Usuários e vínculos
    "make_user",
    "make_user_market",
    "make_platform_permission",
    # Catálogo e diretório
    "make_catalog",
    "make_price_list",
    "make_client",
    "make_representative",
    # Produto e dimensões
    "make_product_group",
    "make_product_type",
    "make_product",
    "make_product_market",
    "make_product_price",
    # Opcionais e aplicações independentes
    "make_optional_category",
    "make_optional",
    "make_application",
]
