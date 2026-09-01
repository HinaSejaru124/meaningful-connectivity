from fastapi import APIRouter, HTTPException

from api.auth.schemas import LoginRequest, TokenResponse
from api.auth.service import auth_service


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Connexion administrateur et génération d'un JWT",
)
def login(payload: LoginRequest):
    try:
        return auth_service.login(payload)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
