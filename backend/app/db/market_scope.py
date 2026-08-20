"""Barreira transversal de isolamento de mercado para consultas ORM.

Rotas ainda devem validar o mercado na criação, mas esta camada garante que
um ID conhecido de outro mercado não seja materializado por engano (IDOR).
"""
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.models.client import Client
from app.models.notification import Notification
from app.models.order import Order
from app.models.representative import Representative


MARKET_SCOPED_MODELS = (Client, Representative, Order, Notification)


@event.listens_for(Session, "do_orm_execute")
def add_market_scope(execute_state) -> None:
    market = execute_state.session.info.get("active_market")
    if not market or execute_state.execution_options.get("skip_market_scope"):
        return
    if execute_state.is_select:
        statement = execute_state.statement
        for model in MARKET_SCOPED_MODELS:
            statement = statement.options(
                with_loader_criteria(
                    model,
                    lambda entity, market=market: entity.market_code == market,
                    include_aliases=True,
                )
            )
        execute_state.statement = statement
