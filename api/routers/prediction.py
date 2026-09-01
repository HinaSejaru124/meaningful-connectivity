from fastapi import APIRouter, HTTPException

from ..model_service import model_service
from ..schemas import PredictionRequest


router = APIRouter(
    prefix="/predict",
    tags=["Prediction"],
)


@router.post(
    "",
    summary="Prédire le caractère meaningful d'une session",
)
def predict(request: PredictionRequest):
    try:
        features = request.model_dump(exclude={"model"})
        return model_service.predict(
            model_name=request.model,
            features=features,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc