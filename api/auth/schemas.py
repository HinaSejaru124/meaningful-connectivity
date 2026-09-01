from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Nom d'utilisateur administrateur")
    password: str = Field(..., min_length=1, description="Mot de passe administrateur")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    role: str = "admin"
