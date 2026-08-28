from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PredictionRequest(BaseModel):
    """
    Données réseau et applicatives nécessaires à une prédiction.

    Toutes les features correspondent aux features utilisées par
    le pipeline ML.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": "gradient_boosting",
                "bandwidth": 5.0,
                "concurrent_users": 3,
                "deadline_seconds": 10.0,
                "interaction_level": 0,
                "jitter": 2.0,
                "latency": 50.0,
                "packet_loss": 1.0,
                "resource_size_mb": 2.5,
                "service_type": "pdf",
            }
        }
    )

    model: str = Field(
        default="gradient_boosting",
        description="Modèle ML utilisé pour la prédiction.",
    )

    bandwidth: float = Field(
        ...,
        gt=0,
        description="Bande passante disponible en Mbit/s.",
    )

    concurrent_users: int = Field(
        ...,
        ge=1,
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
        description="Niveau d'interaction requis par le service.",
    )

    jitter: float = Field(
        ...,
        ge=0,
        description="Gigue réseau en millisecondes.",
    )

    latency: float = Field(
        ...,
        ge=0,
        description="Latence réseau en millisecondes.",
    )

    packet_loss: float = Field(
        ...,
        ge=0,
        le=100,
        description="Taux de perte de paquets en pourcentage.",
    )

    resource_size_mb: float = Field(
        ...,
        gt=0,
        description="Taille de la ressource en mégaoctets.",
    )

    service_type: str = Field(
        ...,
        min_length=1,
        description="Type de service éducatif.",
    )


class PredictionResponse(BaseModel):
    model: str
    prediction: int
    meaningful: bool
    probability_meaningful: float | None


class TrainRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": "gradient_boosting"
            }
        }
    )

    model: str = Field(
        default="gradient_boosting",
        description="Modèle à entraîner.",
    )


class DatasetInfoResponse(BaseModel):
    path: str
    observations: int
    features: list[str]
    target: str
    target_distribution: dict[str, int]