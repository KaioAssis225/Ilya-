import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class OrderItemAttachment(Base, TimestampMixin):
    """Arquivo privado anexado ao comentário de uma linha do orçamento.

    O ``order_item_id`` nasce vazio porque a tela envia os arquivos antes de o
    orçamento existir. Ao salvar, o backend reivindica o upload para a linha.
    """

    __tablename__ = "order_item_attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), nullable=True
    )
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code", ondelete="RESTRICT"), nullable=False
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    order_item: Mapped[Optional["OrderItem"]] = relationship(
        "OrderItem", back_populates="attachments"
    )

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_order_item_attachments_size_positive"),
        Index("ix_order_item_attachments_order_item", "order_item_id"),
        Index(
            "ix_order_item_attachments_pending_owner",
            "uploaded_by_user_id",
            "market_code",
            postgresql_where=text("order_item_id IS NULL"),
        ),
    )


if TYPE_CHECKING:
    from app.models.order import OrderItem
