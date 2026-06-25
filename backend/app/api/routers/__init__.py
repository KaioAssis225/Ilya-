from app.api.routers.products import router as products_router
from app.api.routers.clients import router as clients_router
from app.api.routers.reps import router as reps_router
from app.api.routers.orders import router as orders_router
from app.api.routers.auth import router as auth_router

__all__ = ["products_router", "clients_router", "reps_router", "orders_router", "auth_router"]
