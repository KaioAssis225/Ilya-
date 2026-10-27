"""Builders de opcionais e aplicações independentes para testes de integração (P07).

Sem factory_boy. Respeitam as constraints do banco:
- OptionalCategory: code único por mercado (uq_optional_categories_market_code)
- ProductOptionalApplication: nome não vazio e display_order >= 0

Os relacionamentos `category` e `allowed_optionals` são atribuídos como objetos
para que a instância já nasça carregada no identity map da sessão de teste.
"""
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.optional_application import ProductOptionalApplication
from app.models.optional_category import OptionalCategory
from app.models.optional_color import OptionalColor
from app.models.product import Product


async def make_optional_category(
    db: AsyncSession,
    *,
    market_code: str,
    code: str | None = None,
    name: str | None = None,
) -> OptionalCategory:
    """Cria uma categoria mestre de opcional no mercado especificado."""
    _code = code or f"CAT{uuid.uuid4().hex[:8].upper()}"
    category = OptionalCategory(
        market_code=market_code,
        code=_code,
        name=name or _code.title(),
    )
    db.add(category)
    await db.flush()
    return category


async def make_optional(
    db: AsyncSession,
    category: OptionalCategory,
    *,
    color_name: str,
    market_code: str | None = None,
    brand: str = "ILYA",
) -> OptionalColor:
    """Cria uma opção (cor/acabamento) da categoria.

    `market_code` pode divergir do mercado da categoria só para montar o caso
    ISO-21 de opção estrangeira com o mesmo código de categoria.
    """
    optional = OptionalColor(
        market_code=market_code or category.market_code,
        category=category.code,
        color_name=color_name,
        brand=brand,
    )
    db.add(optional)
    await db.flush()
    return optional


async def make_application(
    db: AsyncSession,
    product: Product,
    category: OptionalCategory,
    *,
    name: str,
    name_en: str | None = None,
    required: bool = False,
    allow_repeat: bool = True,
    allow_all: bool = False,
    allowed: Sequence[OptionalColor] = (),
    display_order: int = 0,
) -> ProductOptionalApplication:
    """Cria uma aplicação independente da categoria no produto."""
    application = ProductOptionalApplication(
        id=uuid.uuid4(),
        product_id=product.id,
        component_id=None,
        category_id=category.id,
        category=category,
        name=name,
        name_en=name_en,
        required=required,
        display_order=display_order,
        allow_all=allow_all,
        allow_repeat=allow_repeat,
        allowed_optionals=[] if allow_all else list(allowed),
    )
    db.add(application)
    await db.flush()
    return application
