import uuid
from typing import Optional
from pydantic import BaseModel
from app.models.user import UserRole


class LoginRequest(BaseModel):
    identifier: str  # accepts email or username
    password: str


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

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole = UserRole.vendedor
    rep_id: Optional[uuid.UUID] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    rep_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class UserPasswordReset(BaseModel):
    new_password: str


class ChangePasswordRequest(BaseModel):
    new_password: str
