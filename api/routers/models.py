from fastapi import APIRouter, Depends, HTTPException

from api.auth.dependencies import require_admin

from ..model_service import model_service
from ..schemas import SaveResponse, TrainResponse


router = APIRouter(
    prefix="/models",
    tags=["Models"],
)


@router.get(
    "/status",
    summary="Obtenir l'état des modèles",
)
def status():
    return model_service.status()


@router.post(
    "/train",
    response_model=TrainResponse,
    summary="Entraîner un modèle à partir d'un dataset fourni (admin)",
)
def train(
    dataset_path: str | None = None,
    model_names: list[str] | None = None,
    admin: dict = Depends(require_admin),
):
    _ = admin
    try:
        return model_service.train(dataset_path=dataset_path, model_names=model_names)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/load",
    summary="Charger les modèles disponibles en mémoire (admin)",
)
def load_models(admin: dict = Depends(require_admin)):
    _ = admin
    return model_service.status()


@router.post(
    "/reload",
    summary="Recharger les modèles sauvegardés (admin)",
)
def reload_models(admin: dict = Depends(require_admin)):
    _ = admin
    return model_service.status()


@router.post(
    "/save",
    response_model=SaveResponse,
    summary="Sauvegarder la version courante des modèles (admin)",
)
def save(admin: dict = Depends(require_admin)):
    _ = admin
    return model_service.save_models()