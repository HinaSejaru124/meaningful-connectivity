from fastapi import FastAPI, HTTPException

from .schemas import (
    DatasetInfoResponse,
    PredictionRequest,
    PredictionResponse,
    TrainRequest,
)
from .service import APIService


app = FastAPI(
    title="Meaningful Connectivity API",
    description=(
        "API d'évaluation de la meaningful connectivity "
        "pour les services éducatifs."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "System",
            "description": "État et informations générales de l'API.",
        },
        {
            "name": "Dataset",
            "description": "Informations relatives au dataset utilisé.",
        },
        {
            "name": "Models",
            "description": "Informations et gestion des modèles ML.",
        },
        {
            "name": "Training",
            "description": "Entraînement et génération de versions de modèles.",
        },
        {
            "name": "Prediction",
            "description": "Classification de nouvelles sessions.",
        },
    ],
)

service = APIService()


# ============================================================================
# System
# ============================================================================


@app.get(
    "/health",
    tags=["System"],
)
def health():
    return {
        "status": "ok",
        "service": "meaningful-connectivity-api",
    }


# ============================================================================
# Dataset
# ============================================================================


@app.get(
    "/dataset",
    response_model=DatasetInfoResponse,
    tags=["Dataset"],
)
def dataset_info():

    try:
        return service.dataset_info()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


# ============================================================================
# Models
# ============================================================================


@app.get(
    "/models",
    tags=["Models"],
)
def list_models():

    return {
        "models": [
            "logistic_regression",
            "random_forest",
            "gradient_boosting",
        ]
    }


# ============================================================================
# Training
# ============================================================================


@app.post(
    "/models/train",
    tags=["Training"],
)
def train_model(
    request: TrainRequest,
):

    try:
        return service.train(
            request.model
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


# ============================================================================
# Model versions
# ============================================================================


@app.get(
    "/models/versions",
    tags=["Models"],
)
def list_model_versions(
    model: str | None = None,
):

    try:
        return {
            "versions": service.list_versions(
                model
            )
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


# ============================================================================
# Prediction
# ============================================================================


@app.post(
    "/predict",
    response_model=PredictionResponse,
    tags=["Prediction"],
)
def predict(
    request: PredictionRequest,
):

    features = request.model_dump(
        exclude={"model"}
    )

    try:

        return service.predict(
            request.model,
            features,
        )

    except FileNotFoundError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc