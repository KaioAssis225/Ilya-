import uuid
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKey, String, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ProductGroup(Base):
    """Grupo de subgrupos (tipos) de produto, por mercado.

    No Brasil o grupo carrega a alíquota de IPI (regra fiscal). Em Portugal o
    grupo só organiza o catálogo: `ipi` é sempre 0 (check no banco) e o pedido
    EU usa o IVA aprovado de `product_markets`, nunca o grupo
    (eu_product_groups_r13_20261008).
    """

    __tablename__ = "product_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code", name="fk_product_groups_market"),
        nullable=False, default="BR", server_default="BR",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ipi: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))

    __table_args__ = (
        UniqueConstraint("market_code", "name", name="uq_product_groups_market_name"),
        UniqueConstraint("id", "market_code", name="uq_product_groups_id_market"),
        CheckConstraint("market_code = 'BR' OR ipi = 0", name="ck_product_groups_eu_sem_ipi"),
    )
