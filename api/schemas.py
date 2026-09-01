from typing import Literal

from pydantic import BaseModel, Field


ModelName = Literal[
    "logistic_regression",
    "random_forest",
    "gradient_boosting",
]


class PredictionRequest(BaseModel):

    model: ModelName = Field(
        ...,
        description="Modèle ML utilisé pour la prédiction.",
    )

    bandwidth: float = Field(
        ...,
        ge=0,
        description="Bande passante en Mbit/s.",
    )

    concurrent_users: int = Field(
        ...,
        ge=0,
        description="Nombre d'utilisateurs concurrents.",
    )

    deadline_seconds: float = Field(
        ...,
        gt=0,
        description="Deadline applicative en secondes.",
    )

    interaction_level: int = Field(
        ...,
        ge=0,
        description="Niveau d'interaction du service.",
    )

    jitter: float = Field(
        ...,
        ge=0,
        description="Gigue en millisecondes.",
    )

    latency: float = Field(
        ...,
        ge=0,
        description="Latence en millisecondes.",
    )

    packet_loss: float = Field(
        ...,
        ge=0,
        le=100,
        description="Perte de paquets en pourcentage.",
    )

    resource_size_mb: float = Field(
        ...,
        ge=0,
        description="Taille de la ressource en MB.",
    )

    service_type: str = Field(
        ...,
        min_length=1,
        description="Type de service éducatif.",
    )


class ExplainRequest(PredictionRequest):
    pass


class TrainResponse(BaseModel):

    dataset_size: int
    train_size: int
    test_size: int
    model_version: str | None
    available_models: list[str]


class SaveResponse(BaseModel):

    saved: bool
    model_version: str | None
    path: str
    models: list[str]