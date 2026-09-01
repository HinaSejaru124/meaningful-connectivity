from fastapi import APIRouter, HTTPException

from ..model_service import model_service
from ..schemas import ExplainRequest


router = APIRouter(
    prefix="/explain",
    tags=["Explainability"],
)


@router.post(
    "",
    summary="Expliquer une prédiction avec SHAP",
)
def explain(request: ExplainRequest):
    try:
        features = request.model_dump(exclude={"model"})
        return model_service.explain(
            model_name=request.model,
            features=features,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc