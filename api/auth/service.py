import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .schemas import LoginRequest


JWT_SECRET = os.getenv("API_JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = int(os.getenv("API_JWT_TTL_SECONDS", "3600"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")


class AuthService:
    def __init__(self):
        self.username = ADMIN_USERNAME
        self.password_hash = ADMIN_PASSWORD_HASH

    def validate_credentials(self, username: str, password: str) -> bool:
        if username != self.username:
            return False
        if not self.password_hash:
            return password == os.getenv("ADMIN_PASSWORD", "") and bool(os.getenv("ADMIN_PASSWORD"))
        return self._verify_hash(password)

    def _verify_hash(self, password: str) -> bool:
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))
        except Exception:
            return False

    def login(self, payload: LoginRequest) -> dict[str, Any]:
        if not self.validate_credentials(payload.username, payload.password):
            raise ValueError("Identifiants invalides.")
        now = datetime.now(timezone.utc)
        token_payload = {
            "sub": payload.username,
            "role": "admin",
            "exp": now + timedelta(seconds=JWT_TTL_SECONDS),
            "iat": now,
        }
        token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": JWT_TTL_SECONDS,
            "role": "admin",
        }

    def decode_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


auth_service = AuthService()
