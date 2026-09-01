from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd
import shap

from sklearn.model_selection import train_test_split

from models.config import (
    DATASET_PATH,
    MODEL_DIR,
    RANDOM_STATE,
    TEST_SIZE,
)
from models.data_loader import load_dataset
from models.evaluate import evaluate_model
from models.train import build_models


class ModelService:
    """
    Service centralisé pour :

    - charger les modèles ;
    - entraîner les modèles ;
    - évaluer les modèles ;
    - effectuer des prédictions ;
    - produire des explications SHAP ;
    - sauvegarder les modèles ;
    - recharger les modèles.

    L'API ne contient aucune logique ML.
    Elle délègue cette responsabilité à ce service et aux modules models/.
    """

    def __init__(self):
        self._lock = Lock()

        self.models: dict[str, Any] = {}
        self.metrics: dict[str, dict] = {}

        self.dataset_size: int = 0
        self.train_size: int = 0
        self.test_size: int = 0

        self.trained_at: str | None = None
        self.model_version: str | None = None

        MODEL_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.reload_models()

    # ------------------------------------------------------------------
    # Informations
    # ------------------------------------------------------------------

    @property
    def available_models(self) -> list[str]:
        return sorted(self.models.keys())

    def status(self) -> dict:
        return {
            "dataset": str(DATASET_PATH),
            "dataset_exists": DATASET_PATH.exists(),
            "dataset_size": self.dataset_size,
            "train_size": self.train_size,
            "test_size": self.test_size,
            "available_models": self.available_models,
            "metrics": self.metrics,
            "trained_at": self.trained_at,
            "model_version": self.model_version,
        }

    # ------------------------------------------------------------------
    # Chemins
    # ------------------------------------------------------------------

    def _model_path(self, model_name: str) -> Path:
        return MODEL_DIR / f"{model_name}.pkl"

    def _metadata_path(self) -> Path:
        return MODEL_DIR / "metadata.json"

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------

    def reload_models(self):
        """
        Charge les modèles sauvegardés.

        Si aucun modèle sauvegardé n'existe, entraîne automatiquement
        les modèles à partir du dataset actuel.
        """

        with self._lock:

            loaded = {}

            for model_name in (
                "logistic_regression",
                "random_forest",
                "gradient_boosting",
            ):
                path = self._model_path(model_name)

                if path.exists():

                    try:
                        with path.open("rb") as f:
                            loaded[model_name] = pickle.load(f)

                    except Exception:
                        # Modèle corrompu/incompatible :
                        # il sera reconstruit plus bas.
                        pass

            if loaded:
                self.models = loaded
                self._load_metadata()

                # Si les métadonnées sont absentes/incomplètes,
                # récupérer au moins la taille du dataset.
                try:
                    _, _, df = load_dataset()
                    self.dataset_size = len(df)
                except Exception:
                    pass

                return

            self._train_initial_models()

    # ------------------------------------------------------------------
    # Entraînement
    # ------------------------------------------------------------------

    def _train_initial_models(self):
        """
        Entraîne les trois modèles actuellement définis dans models/.
        """

        X, y, df = load_dataset()

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=y,
        )

        models = build_models()

        trained_models = {}
        metrics = {}

        for name, model in models.items():

            model.fit(
                X_train,
                y_train,
            )

            evaluation = evaluate_model(
                model,
                X_test,
                y_test,
            )

            trained_models[name] = model
            metrics[name] = evaluation

        self.models = trained_models
        self.metrics = metrics

        self.dataset_size = len(df)
        self.train_size = len(X_train)
        self.test_size = len(X_test)

        self.trained_at = datetime.now(
            timezone.utc
        ).isoformat()

        self.model_version = self._generate_version()

        self._save_models()

    def train(self) -> dict:
        """
        Réentraîne tous les modèles à partir du dataset courant.
        """

        with self._lock:
            self._train_initial_models()

        return self.status()

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def _generate_version(self) -> str:
        return datetime.now(
            timezone.utc
        ).strftime("%Y%m%dT%H%M%SZ")

    # ------------------------------------------------------------------
    # Sauvegarde
    # ------------------------------------------------------------------

    def _save_models(self):

        MODEL_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        for model_name, model in self.models.items():

            path = self._model_path(
                model_name
            )

            with path.open("wb") as f:
                pickle.dump(
                    model,
                    f,
                )

        metadata = {
            "model_version": self.model_version,
            "trained_at": self.trained_at,
            "dataset": str(DATASET_PATH),
            "dataset_size": self.dataset_size,
            "train_size": self.train_size,
            "test_size": self.test_size,
            "metrics": self.metrics,
            "models": self.available_models,
        }

        with self._metadata_path().open(
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                metadata,
                f,
                indent=2,
            )

    def save_models(self) -> dict:
        """
        Sauvegarde explicitement la version actuellement chargée.
        """

        with self._lock:
            self._save_models()

        return {
            "saved": True,
            "model_version": self.model_version,
            "path": str(MODEL_DIR),
            "models": self.available_models,
        }

    # ------------------------------------------------------------------
    # Métadonnées
    # ------------------------------------------------------------------

    def _load_metadata(self):

        path = self._metadata_path()

        if not path.exists():
            return

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as f:

                metadata = json.load(f)

            self.model_version = metadata.get(
                "model_version"
            )

            self.trained_at = metadata.get(
                "trained_at"
            )

            self.dataset_size = metadata.get(
                "dataset_size",
                0,
            )

            self.train_size = metadata.get(
                "train_size",
                0,
            )

            self.test_size = metadata.get(
                "test_size",
                0,
            )

            self.metrics = metadata.get(
                "metrics",
                {},
            )

        except Exception:
            pass

    # ------------------------------------------------------------------
    # Validation modèle
    # ------------------------------------------------------------------

    def _get_model(self, model_name: str):

        if model_name not in self.models:

            raise ValueError(
                f"Modèle inconnu : {model_name}. "
                f"Modèles disponibles : "
                f"{', '.join(self.available_models)}"
            )

        return self.models[model_name]

    # ------------------------------------------------------------------
    # Prédiction
    # ------------------------------------------------------------------

    def predict(
        self,
        model_name: str,
        features: dict,
    ) -> dict:

        model = self._get_model(
            model_name
        )

        X = pd.DataFrame(
            [features]
        )

        prediction = int(
            model.predict(X)[0]
        )

        probability = float(
            model.predict_proba(X)[0][1]
        )

        return {
            "model": model_name,
            "prediction": prediction,
            "meaningful": bool(prediction),
            "probability_meaningful": probability,
            "model_version": self.model_version,
        }

    # ------------------------------------------------------------------
    # Explication SHAP
    # ------------------------------------------------------------------

    def explain(
        self,
        model_name: str,
        features: dict,
    ) -> dict:

        model = self._get_model(
            model_name
        )

        X = pd.DataFrame(
            [features]
        )

        # Pipeline sklearn :
        # séparation preprocessing / classifier
        preprocessor = model.named_steps[
            "preprocessor"
        ]

        classifier = model.named_steps[
            "classifier"
        ]

        X_transformed = preprocessor.transform(
            X
        )

        feature_names = (
            preprocessor
            .get_feature_names_out()
            .tolist()
        )

        # --------------------------------------------------------------
        # Sélection automatique de l'explainer
        # --------------------------------------------------------------

        if model_name in {
            "random_forest",
            "gradient_boosting",
        }:

            explainer = shap.TreeExplainer(
                classifier
            )

            shap_values = explainer.shap_values(
                X_transformed
            )

            expected_value = explainer.expected_value

            # SHAP peut retourner :
            #
            # - [n_samples, n_features]
            # - [n_samples, n_features, n_classes]
            #
            # On sélectionne ici la classe positive.

            if hasattr(
                shap_values,
                "ndim",
            ):

                if shap_values.ndim == 3:
                    values = shap_values[
                        0,
                        :,
                        1,
                    ]

                else:
                    values = shap_values[0]

            elif isinstance(
                shap_values,
                list,
            ):

                if len(shap_values) == 2:
                    values = shap_values[1][0]
                else:
                    values = shap_values[0][0]

            else:
                values = shap_values[0]

            if hasattr(
                expected_value,
                "__len__",
            ):

                base_value = float(
                    expected_value[1]
                    if len(expected_value) > 1
                    else expected_value[0]
                )

            else:
                base_value = float(
                    expected_value
                )

        elif model_name == "logistic_regression":

            # Pour le modèle linéaire, LinearExplainer
            # est plus approprié que TreeExplainer.

            explainer = shap.LinearExplainer(
                classifier,
                X_transformed,
            )

            shap_values = explainer(
                X_transformed
            )

            values = shap_values.values[0]

            base_value = float(
                shap_values.base_values[0]
            )

        else:

            raise ValueError(
                f"SHAP non supporté pour : "
                f"{model_name}"
            )

        # --------------------------------------------------------------
        # Résultats
        # --------------------------------------------------------------

        contributions = []

        for name, value in zip(
            feature_names,
            values,
        ):

            contributions.append(
                {
                    "feature": name,
                    "shap_value": float(value),
                    "absolute_shap_value": abs(
                        float(value)
                    ),
                }
            )

        contributions.sort(
            key=lambda item:
                item["absolute_shap_value"],
            reverse=True,
        )

        prediction = self.predict(
            model_name,
            features,
        )

        return {
            "model": model_name,
            "model_version": self.model_version,
            "prediction": prediction,
            "base_value": base_value,
            "features": contributions,
        }


# Instance globale du service.
#
# L'API importe cette instance et ne manipule pas directement
# les modèles sklearn.
model_service = ModelService()