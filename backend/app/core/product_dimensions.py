"""Limite plausível das medidas de produto (altura, largura e profundidade).

As colunas guardam METROS (Numeric(10,2)). Um valor em milímetros digitado ou
importado como metros (ex.: 470 em vez de 0,47) aparece no EU como "470000 mm";
esta constante única barra o erro na entrada (API, CSV e formulário).
"""

from decimal import Decimal
from typing import Optional

MAX_PRODUCT_DIMENSION_M = Decimal("20")

PRODUCT_DIMENSION_LIMIT_MESSAGE = (
    f"Medida acima de {MAX_PRODUCT_DIMENSION_M:f} m — as medidas são em metros "
    "(ex.: 470 mm = 0,47)."
)


def ensure_dimension_within_limit(value: Optional[Decimal]) -> Optional[Decimal]:
    """Devolve o valor ou levanta ValueError se passar de 20 m (20 exato passa)."""
    if value is not None and value > MAX_PRODUCT_DIMENSION_M:
        raise ValueError(PRODUCT_DIMENSION_LIMIT_MESSAGE)
    return value
