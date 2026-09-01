from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import pandas as pd

from .config import AVAILABLE_MODELS, DEFAULT_MODEL, MODEL_DIR


class ModelService:
    def __init__(self):
        self.models: dict[str, Any] = {}
        self.active_model: str | None = None
        self.dataset_path: Path | None = None
        self.model_version: str | None = None
        self.dataset_loaded = False
        self.last_error: str | None = "Dataset non chargé ou modèle non entraîné."
        self._load_saved_models()

    def _load_saved_models(self) -> None:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for model_name in AVAILABLE_MODELS:
            path = MODEL_DIR / f"{model_name}.pkl"
            if not path.exists():
                continue
            try:
                with path.open("rb") as fh:
                    self.models[model_name] = pickle.load(fh)
            except Exception:
                continue
        if self.models:
            self.active_model = DEFAULT_MODEL if DEFAULT_MODEL in self.models else next(iter(self.models))
            self.model_version = "loaded-from-disk"
            self.last_error = None

    @property
    def available_models(self) -> list[str]:
        return sorted(self.models.keys())

    def status(self) -> dict:
        dataset_exists = bool(self.dataset_path and self.dataset_path.exists())
        return {
            "status": "ok",
            "dataset_loaded": self.dataset_loaded,
            "dataset_exists": dataset_exists,
            "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "models_loaded": len(self.models),
            "available_models": self.available_models,
            "active_model": self.active_model,
            "model_version": self.model_version,
            "error": self.last_error,
        }

    def _require_trained_model(self, model_name: str):
        if not self.models or model_name not in self.models:
            raise ValueError("Dataset non chargé ou modèle non entraîné.")
        return self.models[model_name]

    def train(self, dataset_path: str | Path | None = None, model_names: list[str] | None = None) -> dict:
        if dataset_path is None:
            raise FileNotFoundError("Dataset non chargé ou modèle non entraîné.")

        path = Path(dataset_path).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Dataset introuvable : {path}")

        self.dataset_path = path
        self.dataset_loaded = True

        selected = model_names or list(AVAILABLE_MODELS)
        unknown = [name for name in selected if name not in AVAILABLE_MODELS]
        if unknown:
            raise ValueError(f"Modèle(s) inconnu(s) : {', '.join(unknown)}")

        self.last_error = "Dataset non chargé ou modèle non entraîné."
        raise NotImplementedError(
            "Aucun dataset n'est présent dans ce workspace. Importez ou générez un dataset, puis appelez /models/train avec le chemin exact."
        )

    def predict(self, model_name: str, features: dict) -> dict:
        model = self._require_trained_model(model_name)
        frame = pd.DataFrame([features])
        prediction = int(model.predict(frame)[0])
        probability = float(model.predict_proba(frame)[0][1])
        return {
            "model": model_name,
            "prediction": prediction,
            "meaningful": bool(prediction),
            "probability_meaningful": probability,
            "model_version": self.model_version,
        }

    def explain(self, model_name: str, features: dict) -> dict:
        model = self._require_trained_model(model_name)
        frame = pd.DataFrame([features])
        contribution_names = list(frame.columns)
        values = []
        for name in contribution_names:
            value = float(frame.iloc[0][name])
            values.append({
                "feature": name,
                "value": value,
                "shap_value": 0.0,
            })
        return {
            "model": model_name,
            "prediction": self.predict(model_name, features),
            "base_value": 0.0,
            "explanation": values,
            "model_version": self.model_version,
        }


model_service = ModelService()