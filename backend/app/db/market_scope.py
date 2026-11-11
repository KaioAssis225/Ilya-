"""Barreira transversal de isolamento de mercado para consultas ORM.

Rotas ainda devem validar o mercado na criação, mas esta camada garante que
um ID conhecido de outro mercado não seja materializado por engano (IDOR).
"""
import uuid

from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session, with_loader_criteria

from app.models.client import Client
from app.models.notification import Notification
from app.models.order import Order
from app.models.representative import Representative
from app.models.product import Product
from app.models.catalog import Catalog, ClientCatalog, RepresentativeCatalog
from app.models.optional_category import OptionalCategory
from app.models.optional_color import OptionalColor
from app.models.product_group import ProductGroup
from app.models.product_type import ProductType
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument


MARKET_SCOPED_MODELS = (
    Client,
    Representative,
    Order,
    Notification,
    Product,
    Catalog,
    ClientCatalog,
    RepresentativeCatalog,
    OptionalCategory,
    OptionalColor,
    ProductType,
    ProductGroup,
    OrderEmailDocument,
    OrderEmailDelivery,
)


PROTOTYPE_OWNER_INFO_KEY = "prototype_owner"
INCLUDE_PROTOTYPES_OPTION = "include_prototypes"


def prototype_visibility(execute_state) -> uuid.UUID | bool:
    """Quem pode ver protótipos nesta consulta: `False` (ninguém, o padrão),
    `True` (todos: só contexto de sistema, ex.: PDF de um pedido já autorizado)
    ou o UUID do dono (ele vê os próprios, e mais ninguém).

    A opção por consulta (`execution_options(include_prototypes=...)`) vence o
    `prototype_owner` gravado na sessão pela dependência de rota. Os pontos que
    abrem a visão são poucos e achados com `grep include_prototypes` /
    `prototype_owner`.
    """
    option = execute_state.execution_options.get(INCLUDE_PROTOTYPES_OPTION)
    if option is not None:
        return option
    owner = execute_state.session.info.get(PROTOTYPE_OWNER_INFO_KEY)
    return owner if owner is not None else False


def _prototype_criteria(visibility: uuid.UUID | bool):
    """Critérios por modelo: Product (o próprio protótipo) e, para os grupos de
    opcionais que só existem dentro de um protótipo, `prototype_id`."""
    if visibility is True:
        return []
    if visibility is False:
        return [
            (Product, Product.is_prototype.is_(False)),
            (OptionalCategory, OptionalCategory.prototype_id.is_(None)),
            (OptionalColor, OptionalColor.prototype_id.is_(None)),
        ]
    mine = select(Product.id).where(
        Product.is_prototype.is_(True), Product.created_by_user_id == visibility
    )
    return [
        (Product, or_(Product.is_prototype.is_(False), Product.created_by_user_id == visibility)),
        (OptionalCategory, or_(
            OptionalCategory.prototype_id.is_(None), OptionalCategory.prototype_id.in_(mine)
        )),
        (OptionalColor, or_(
            OptionalColor.prototype_id.is_(None), OptionalColor.prototype_id.in_(mine)
        )),
    ]


@event.listens_for(Session, "do_orm_execute")
def add_prototype_scope(execute_state) -> None:
    """Negação por padrão: nenhum SELECT sobre Product (nem sobre os grupos de
    opcionais de protótipo) devolve protótipo.

    Vale com ou sem mercado ativo e mesmo com `skip_market_scope`: esta barreira
    é de acesso (quem pode ver), não de mercado.
    """
    if not execute_state.is_select:
        return
    statement = execute_state.statement
    for model, criteria in _prototype_criteria(prototype_visibility(execute_state)):
        statement = statement.options(with_loader_criteria(model, criteria, include_aliases=True))
    execute_state.statement = statement


@event.listens_for(Session, "do_orm_execute")
def add_market_scope(execute_state) -> None:
    market = execute_state.session.info.get("active_market")
    if not market or execute_state.execution_options.get("skip_market_scope"):
        return
    if execute_state.is_select:
        statement = execute_state.statement
        for model in MARKET_SCOPED_MODELS:
            # Passe a expressão pronta. Uma lambda com `market=market` usa um
            # argumento padrão que não participa da chave de cache do sistema
            # de lambdas do SQLAlchemy; o primeiro mercado compilado poderia
            # então vazar para sessões posteriores (BR consultando como EU ou
            # vice-versa).
            statement = statement.options(
                with_loader_criteria(
                    model,
                    model.market_code == market,
                    include_aliases=True,
                )
            )
        execute_state.statement = statement
    elif execute_state.is_update or execute_state.is_delete:
        mapper = execute_state.bind_mapper
        entity = mapper.class_ if mapper is not None else None
        if entity in MARKET_SCOPED_MODELS:
            execute_state.statement = execute_state.statement.where(
                entity.market_code == market
            )
