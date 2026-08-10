import re
import uuid
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.user import UserRole

# O login compara o identificador já em minúsculas contra `users.username`,
# então um username com maiúscula seria impossível de usar. O formato restrito
# também evita que um username se pareça com um e-mail e confunda a busca.
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,100}$")


class LoginRequest(BaseModel):
    identifier: str  # accepts email or username
    password: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Informe o e-mail ou usuário.")
        return normalized


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    username: Optional[str]
    full_name: str
    role: UserRole
    rep_id: uuid.UUID | None
    linked_id: uuid.UUID | None
    is_active: bool
    must_change_password: bool
    max_discount: Decimal = Decimal("0.00")
    can_view_dashboard: bool = False

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    # Login opcional escolhido pelo admin. Sem ele, a conta entra só pelo e-mail
    # (comportamento anterior preservado).
    username: Optional[str] = None
    password: str
    full_name: str
    role: UserRole = UserRole.vendedor
    rep_id: Optional[uuid.UUID] = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError(
                "Usuário deve ter de 3 a 100 caracteres, apenas letras, "
                "números, ponto, hífen ou sublinhado."
            )
        return normalized


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    rep_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None
    can_view_dashboard: Optional[bool] = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized or not _USERNAME_RE.fullmatch(normalized):
            raise ValueError(
                "Usuário deve ter de 3 a 100 caracteres, apenas letras, "
                "números, ponto, hífen ou sublinhado."
            )
        return normalized


class UserPasswordReset(BaseModel):
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str


class ReauthenticationRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class UserCreateResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role: str
    temp_password: str
