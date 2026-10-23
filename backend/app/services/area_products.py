"""Regras compartilhadas para produtos vendidos por metro quadrado."""

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
