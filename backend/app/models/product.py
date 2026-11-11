import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Sequence, String, Text, Numeric, Boolean, Integer, ForeignKey, ForeignKeyConstraint, Index, Table, Column, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.models.base import Base, TimestampMixin
from app.models.optional_color import product_optionals, OptionalColor
from app.models.catalog import Catalog

product_set_component_optionals = Table(
    "product_set_component_optionals",
    Base.metadata,
    Column("component_id", PGUUID(as_uuid=True), ForeignKey("product_set_components.id", ondelete="CASCADE"), primary_key=True),
    Column("optional_id", PGUUID(as_uuid=True), ForeignKey("optionals.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_product_set_component_optionals_optional_id", "optional_id"),
)


# Numeração dos protótipos (PROT-0001…): `nextval` é atômico, então dois
# cadastros simultâneos nunca recebem o mesmo número. Rollback deixa buraco.
PROTOTYPE_CODE_PREFIX = "PROT-"
prototype_code_seq = Sequence("prototype_code_seq", metadata=Base.metadata)


def format_prototype_code(number: int) -> str:
    return f"{PROTOTYPE_CODE_PREFIX}{number:04d}"


def is_prototype_code(code: str | None) -> bool:
    return (code or "").strip().upper().startswith(PROTOTYPE_CODE_PREFIX)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code"), nullable=False, default="BR", server_default="BR"
    )
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    ean: Mapped[str | None] = mapped_column(String(13), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_category_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="Outro")
    # FK composta com market_code em __table_args__. Obrigatório desde
    # catalog_permissions_r21: o catálogo define aba e permissão de venda.
    catalog_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    area_limit_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    max_area_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    altura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    largura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    profundidade: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price_lojista: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # Valor corporativo anterior, preservado exclusivamente para histórico.
    # Não adicionar este campo aos schemas, endpoints, CSVs ou ao frontend.
    custo_desativado: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price_corporativo: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    all_optionals_categories: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Migration/01: frescor para consumidores externos (leitura cross-database
    # do Ilya Estoque) e desativação sem exclusão física.
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Protótipo (só EU, prototypes_r45): produto reservado a quem tem
    # `user_markets.can_manage_prototypes` e que nunca aparece fora das rotas de
    # protótipo e do orçamento do próprio dono. A negação por padrão fica em
    # `app.db.market_scope` (todo SELECT sobre Product ganha is_prototype = false).
    is_prototype: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    catalog: Mapped["Catalog | None"] = relationship("Catalog", lazy="selectin")
    optionals: Mapped[list["OptionalColor"]] = relationship(
        "OptionalColor", secondary=product_optionals, lazy="selectin"
    )
    # Galeria. `photo_path` continua sendo a foto principal (espelho mantido por
    # `app.core.product_photos`), então quem lê só `photo_path` não muda.
    photos: Mapped[list["ProductPhoto"]] = relationship(
        "ProductPhoto", order_by="ProductPhoto.position, ProductPhoto.created_at",
        cascade="all, delete-orphan", lazy="selectin",
    )
    set_items: Mapped[list["ProductSetItem"]] = relationship(
        "ProductSetItem", foreign_keys="ProductSetItem.set_id",
        cascade="all, delete-orphan", lazy="selectin",
    )
    components: Mapped[list["ProductSetComponent"]] = relationship(
        "ProductSetComponent", foreign_keys="ProductSetComponent.set_id",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        # Produto e catálogo precisam ser do mesmo mercado
        # (market_fk_r7_20261005); catálogo em uso não é excluído (r21).
        ForeignKeyConstraint(
            ["catalog_id", "market_code"],
            ["catalogs.id", "catalogs.market_code"],
            name="fk_products_catalog_same_market",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "NOT area_limit_enabled OR (max_area_m2 IS NOT NULL AND max_area_m2 > 0)",
            name="ck_products_area_limit_requires_max",
        ),
        UniqueConstraint("market_code", "product_code", name="uq_products_market_code"),
        # Protótipo: só EU, sempre com dono e sempre com o prefixo reservado.
        # A recíproca (produto normal não usa PROT-) é regra de aplicação: um
        # CHECK nos dois sentidos poderia quebrar linhas legadas já gravadas.
        CheckConstraint(
            "NOT is_prototype OR market_code = 'EU'",
            name="ck_products_prototype_eu",
        ),
        CheckConstraint(
            "NOT is_prototype OR created_by_user_id IS NOT NULL",
            name="ck_products_prototype_owner",
        ),
        CheckConstraint(
            "NOT is_prototype OR product_code LIKE 'PROT-%'",
            name="ck_products_prototype_code_prefix",
        ),
        Index(
            "ix_products_prototype_owner",
            "created_by_user_id",
            "id",
            postgresql_where=text("is_prototype"),
        ),
        Index("ix_products_market_id", "market_code", "id"),
        Index("ix_products_market_article_category", "market_code", "article_category_path"),
        Index(
            "ix_products_description_prefix_id",
            func.left(description, 512),
            "id",
        ),
        Index("ix_products_type_id", "type", "id"),
        Index("ix_products_price_lojista_id", "price_lojista", "id"),
        Index(
            "ix_products_price_corporativo_id",
            "price_corporativo",
            "id",
        ),
        Index(
            "ix_products_search_trgm",
            "product_code",
            "description",
            postgresql_using="gin",
            postgresql_ops={
                "product_code": "gin_trgm_ops",
                "description": "gin_trgm_ops",
            },
        ),
    )

class ProductPhoto(Base, TimestampMixin):
    """Foto da galeria de um produto. O mercado vem do produto (sem coluna própria).

    Invariante, mantida só por `app.core.product_photos`: com fotos, exatamente
    uma é principal e `products.photo_path` é o caminho dela; sem fotos,
    `photo_path` é NULL.
    """

    __tablename__ = "product_photos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    photo_path: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        UniqueConstraint("product_id", "photo_path", name="uq_product_photos_product_path"),
        Index("ix_product_photos_product_position", "product_id", "position"),
        Index(
            "uq_product_photos_one_primary",
            "product_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )


class ProductSetItem(Base, TimestampMixin):
    __tablename__ = "product_set_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id], lazy="selectin")

    __table_args__ = (
        Index("ix_product_set_items_set_id", "set_id"),
        Index("ix_product_set_items_product_id", "product_id"),
    )


class ProductSetComponent(Base, TimestampMixin):
    __tablename__ = "product_set_components"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    altura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    largura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    profundidade: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    optionals: Mapped[list["OptionalColor"]] = relationship(
        "OptionalColor", secondary=product_set_component_optionals, lazy="selectin"
    )

    __table_args__ = (
        Index("ix_product_set_components_set_id", "set_id"),
    )
