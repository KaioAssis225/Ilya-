import uuid
import enum
from datetime import datetime
from sqlalchemy import String, ForeignKey, Boolean, DateTime, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    vendedor = "vendedor"          # operador interno (sem vínculo de cliente)
    representante = "representante"
    cadastros = "cadastros"
    produtos = "produtos"
    cliente = "cliente"            # conta de portal do cliente-final (linked_id = client_id)
    executivo = "executivo"        # acesso exclusivo ao Dashboard BI (Bloco 95)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="userrole"), nullable=False, default=UserRole.vendedor)
    rep_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("representatives.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bloco 95: admin pode habilitar o Dashboard BI para qualquer role sem alterar
    # as demais permissões. Role `executivo` sempre tem acesso, independente da flag.
    can_view_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
