from fastapi import Depends, HTTPException, status
from app.models.user import User, UserRole
from app.api.deps import get_current_user


class RoleChecker:
    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)):
        if current_user.role == UserRole.ADMIN:
            return current_user  # Admin possui bypass total
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operação não permitida para o seu nível de acesso."
            )
        return current_user
