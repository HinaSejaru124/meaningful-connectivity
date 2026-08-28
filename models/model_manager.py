from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from sklearn.model_selection import train_test_split

from .config import DATASET_PATH, RANDOM_STATE, TEST_SIZE
from .data_loader import load_dataset
from .evaluate import evaluate_model
from .train import build_models


class ModelManager:
    """
    Service applicatif responsable des modèles ML.

    L'API ne manipule pas directement les pipelines scikit-learn.
    Elle délègue à cette classe les opérations de :
        - chargement des données ;
        - entraînement ;
        - évaluation ;
        - prédiction ;
        - persistance ;
        - chargement d'une version entraînée.
    """

    MODELS_DIR = Path("models/artifacts")

    def __init__(self) -> None:
        self.MODELS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._models: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Dataset
    # ------------------------------------------------------------------

    def dataset_info(self) -> dict[str, Any]:
        X, y, df = load_dataset()

        return {
            "path": str(DATASET_PATH),
            "observations": len(df),
            "features": list(X.columns),
            "target": "meaningful",
            "target_distribution": {
                "not_meaningful": int((y == 0).sum()),
                "meaningful": int((y == 1).sum()),
            },
        }

    # ------------------------------------------------------------------
    # Entraînement
    # ------------------------------------------------------------------

    def train(
        self,
        model_name: str,
    ) -> dict[str, Any]:

        models = build_models()

        if model_name not in models:
            raise ValueError(
                f"Modèle inconnu : {model_name}. "
                f"Modèles disponibles : {', '.join(models)}"
            )

        X, y, df = load_dataset()

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=y,
        )

        model = models[model_name]

        model.fit(
            X_train,
            y_train,
        )

        metrics = evaluate_model(
            model,
            X_test,
            y_test,
        )

        version = datetime.now(
            timezone.utc
        ).strftime("%Y%m%dT%H%M%SZ")

        artifact_path = (
            self.MODELS_DIR
            / f"{model_name}_{version}.joblib"
        )

        joblib.dump(
            model,
            artifact_path,
        )

        self._models[model_name] = model

        return {
            "model": model_name,
            "version": version,
            "artifact": str(artifact_path),
            "dataset": {
                "observations": len(df),
                "train": len(X_train),
                "test": len(X_test),
            },
            "metrics": metrics,
        }

    # ------------------------------------------------------------------
    # Modèle courant
    # ------------------------------------------------------------------

    def get_model(
        self,
        model_name: str,
    ):
        if model_name in self._models:
            return self._models[model_name]

        artifacts = sorted(
            self.MODELS_DIR.glob(
                f"{model_name}_*.joblib"
            )
        )

        if not artifacts:
            raise FileNotFoundError(
                f"Aucun modèle entraîné trouvé pour "
                f"'{model_name}'."
            )

        latest = artifacts[-1]

        model = joblib.load(latest)

        self._models[model_name] = model

        return model

    # ------------------------------------------------------------------
    # Prédiction
    # ------------------------------------------------------------------

    def predict(
        self,
        model_name: str,
        features: dict[str, Any],
    ) -> dict[str, Any]:

        model = self.get_model(model_name)

        X = pd.DataFrame(
            [features]
        )

        prediction = int(
            model.predict(X)[0]
        )

        probability = None

        if hasattr(
            model,
            "predict_proba",
        ):
            probability = float(
                model.predict_proba(X)[0][1]
            )

        return {
            "model": model_name,
            "prediction": prediction,
            "meaningful": bool(prediction),
            "probability_meaningful": probability,
        }

    # ------------------------------------------------------------------
    # Versions disponibles
    # ------------------------------------------------------------------

    def list_versions(
        self,
        model_name: str | None = None,
    ) -> list[dict[str, Any]]:

        if model_name:
            pattern = f"{model_name}_*.joblib"
        else:
            pattern = "*.joblib"

        artifacts = sorted(
            self.MODELS_DIR.glob(pattern)
        )

        versions = []

        for artifact in artifacts:

            stem = artifact.stem

            if "_" not in stem:
                continue

            model, version = stem.rsplit(
                "_",
                1,
            )

            versions.append(
                {
                    "model": model,
                    "version": version,
                    "artifact": str(artifact),
                }
            )

        return versions