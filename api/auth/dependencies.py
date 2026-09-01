from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .service import auth_service


bearer_scheme = HTTPBearer(auto_error=False)


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = auth_service.decode_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé. Rôle admin requis.",
        )
    return payload
