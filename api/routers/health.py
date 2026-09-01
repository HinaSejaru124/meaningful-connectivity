from fastapi import APIRouter

from ..model_service import model_service


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get(
    "",
    summary="Vérifier l'état de l'API",
)
def health():
    status = model_service.status()
    return {
        "status": "ok",
        "dataset_loaded": status["dataset_loaded"],
        "dataset_available": status["dataset_exists"],
        "models_loaded": status["models_loaded"],
        "active_model": status["active_model"],
        "model_version": status["model_version"],
        "error": status["error"],
    }