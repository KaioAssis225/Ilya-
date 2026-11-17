import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ShowroomBox(Base, TimestampMixin):
    """Agrupador EU para peças de showroom, feira ou exposição.

    A tabela de preço pertence à box. Valores monetários não são copiados: as
    leituras resolvem o preço vigente em ``product_prices``.
    """

    __tablename__ = "showroom_boxes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(String(2), nullable=False, default="EU")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price_list_code: Mapped[str] = mapped_column(String(30), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    items: Mapped[list["ShowroomBoxItem"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ShowroomBoxItem.created_at"
    )

    __table_args__ = (
        CheckConstraint("market_code = 'EU'", name="ck_showroom_boxes_eu"),
        ForeignKeyConstraint(
            ["market_code", "price_list_code"],
            ["price_lists.market_code", "price_lists.code"],
            name="fk_showroom_boxes_price_list",
            ondelete="RESTRICT",
        ),
        Index("ix_showroom_boxes_market_updated", "market_code", "updated_at"),
    )


class ShowroomBoxItem(Base, TimestampMixin):
    __tablename__ = "showroom_box_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    box_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("showroom_boxes.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    optional_configuration: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    configuration_key: Mapped[str] = mapped_column(
        String(64), nullable=False, default="base", server_default="base"
    )

    product = relationship("Product", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_showroom_box_items_quantity"),
        UniqueConstraint(
            "box_id", "product_id", "configuration_key",
            name="uq_showroom_box_items_configuration",
        ),
        Index("ix_showroom_box_items_box", "box_id", "created_at"),
    )


class ShowroomTransfer(Base, TimestampMixin):
    """Histórico de uma transferência de peças do Estoque EU.

    Guarda nomes e códigos como snapshot: o registro continua legível depois
    que a box, o orçamento ou o usuário forem apagados (as FKs viram NULL).
    """

    __tablename__ = "showroom_transfers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(String(2), nullable=False, default="EU")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_box_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("showroom_boxes.id", ondelete="SET NULL"), nullable=True
    )
    source_box_name: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(10), nullable=False)
    destination_box_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("showroom_boxes.id", ondelete="SET NULL"), nullable=True
    )
    destination_box_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    destination_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    destination_order_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    optional_configuration: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    __table_args__ = (
        CheckConstraint("market_code = 'EU'", name="ck_showroom_transfers_eu"),
        CheckConstraint("quantity > 0", name="ck_showroom_transfers_quantity"),
        CheckConstraint("destination_type IN ('box', 'order')", name="ck_showroom_transfers_type"),
        Index("ix_showroom_transfers_source", "source_box_id", "created_at"),
        Index("ix_showroom_transfers_destination", "destination_box_id", "created_at"),
        Index("ix_showroom_transfers_order", "destination_order_id"),
    )
