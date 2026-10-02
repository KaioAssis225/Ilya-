import uuid
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Catalog(Base):
    """Catálogo/linha comercial do produto (Ilya, IBTW, Cerâmica, Wupa, Tapete…).

    É uma dimensão independente de ProductGroup: grupo carrega o IPI (fiscal) e
    não descreve a linha comercial. Tabela editável pelo usuário para que novos
    catálogos entrem sem alteração de código.
    """

    __tablename__ = "catalogs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code"), nullable=False, default="BR", server_default="BR"
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("market_code", "name", name="uq_catalogs_market_name"),
    )
