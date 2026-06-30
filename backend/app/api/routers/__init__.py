from app.api.routers.products import router as products_router
from app.api.routers.clients import router as clients_router
from app.api.routers.reps import router as reps_router
from app.api.routers.orders import router as orders_router
from app.api.routers.optionals import router as optionals_router
from app.api.routers.product_types import router as product_types_router
from app.api.routers.optional_categories import router as optional_categories_router
from app.api.routers.auth import router as auth_router
from app.api.routers.users import router as users_router
from app.api.routers.notifications import router as notifications_router
from app.api.routers.utils import router as utils_router

__all__ = ["products_router", "clients_router", "reps_router", "orders_router", "optionals_router", "product_types_router", "optional_categories_router", "auth_router", "users_router", "notifications_router", "utils_router"]
