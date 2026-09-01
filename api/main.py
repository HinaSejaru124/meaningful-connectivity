from fastapi import FastAPI

from .routers.auth import router as auth_router
from .routers.health import router as health_router
from .routers.prediction import router as prediction_router
from .routers.explain import router as explain_router
from .routers.models import router as models_router


app = FastAPI(
    title="Meaningful Connectivity API",
    description=(
        "API d'évaluation de la meaningful connectivity "
        "pour les services éducatifs en contexte de faible connectivité. "
        "L'API expose la prédiction ML et son explication par SHAP."
    ),
    version="0.1.0",
)


app.include_router(auth_router)
app.include_router(health_router)
app.include_router(prediction_router)
app.include_router(explain_router)
app.include_router(models_router)


@app.get(
    "/",
    tags=["System"],
    summary="Informations générales sur l'API",
)
def root():

    return {
        "name": "Meaningful Connectivity API",
        "version": "0.1.0",
        "documentation": "/docs",
        "endpoints": {
            "auth": "/auth/login",
            "health": "/health",
            "prediction": "/predict",
            "explainability": "/explain",
            "models": "/models",
        },
    }