"""Regras compartilhadas para produtos vendidos por metro quadrado."""

from decimal import Decimal, ROUND_HALF_UP

import unicodedata


_AREA_CATALOG_NAMES = {"tapete", "tapetes"}


def is_area_catalog(name: str | None) -> bool:
    """Identifica os catálogos de tapetes tolerando caixa, espaços e acentos."""
    if name is None:
        return False
    normalized = unicodedata.normalize("NFKD", name.strip().casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return without_accents in _AREA_CATALOG_NAMES


def is_area_product(product: object) -> bool:
    """Retorna se o produto pertence a um catálogo vendido por área."""
    catalog = getattr(product, "catalog", None)
    return is_area_catalog(getattr(catalog, "name", None))


def area_from_dimensions(width_m: Decimal, depth_m: Decimal) -> Decimal:
    """Área cobrada (m²) = L × P, arredondada a 2 casas (meio para cima), mínimo 0,01."""
    area = (width_m * depth_m).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(area, Decimal("0.01"))
