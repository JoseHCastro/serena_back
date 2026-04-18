"""
Reusable FastAPI dependencies.

Centralizes authentication enforcement and role-based access control
so route handlers stay thin and declarative.
"""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token

# Lazy imports to avoid circular dependencies — resolved at call time
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> "User":  # noqa: F821
    """FastAPI dependency that validates the Bearer token and returns the active user.

    Args:
        credentials: The raw Authorization header parsed by HTTPBearer.
        db: The active database session.

    Returns:
        User: The authenticated, active User ORM object.

    Raises:
        UnauthorizedError: If the token is missing, invalid, expired, or the
            user no longer exists / is inactive.
    """
    from app.modules.users.repository import UserRepository

    try:
        payload = decode_token(credentials.credentials)
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if user_id_str is None or token_type != "access":
            raise UnauthorizedError()
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise UnauthorizedError()

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User account is inactive or does not exist.")
    return user


def require_roles(*roles: str):
    """Dependency factory that restricts access to users with specific roles.

    Args:
        *roles: One or more role names that are permitted to access the endpoint.

    Returns:
        Callable: A FastAPI dependency function that enforces the role check.

    Example:
        ```python
        @router.delete("/{id}", dependencies=[Depends(require_roles("admin"))])
        async def delete_user(...):
            ...
        ```
    """

    async def role_checker(
        current_user: Annotated["User", Depends(get_current_user)],  # noqa: F821
    ) -> "User":  # noqa: F821
        """Check that the current user has one of the required roles.

        Args:
            current_user: The authenticated user from get_current_user.

        Returns:
            User: The current user if the role check passes.

        Raises:
            ForbiddenError: If the user's role is not in the allowed list.
        """
        if current_user.role.name not in roles:
            raise ForbiddenError(
                f"This action requires one of the following roles: {', '.join(roles)}."
            )
        return current_user

    return role_checker


# ---------------------------------------------------------------------------
# Type aliases for route handler signatures
# ---------------------------------------------------------------------------

CurrentUser = Annotated["User", Depends(get_current_user)]  # noqa: F821
DbSession = Annotated[AsyncSession, Depends(get_db)]
