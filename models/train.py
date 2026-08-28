from sklearn.ensemble import (
    RandomForestClassifier,
    HistGradientBoostingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from .config import RANDOM_STATE
from .preprocessing import build_preprocessor


def build_models():

    models = {}

    models["logistic_regression"] = Pipeline(
        [
            (
                "preprocessor",
                build_preprocessor(
                    scale_numeric=True
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )

    models["random_forest"] = Pipeline(
        [
            (
                "preprocessor",
                build_preprocessor(
                    scale_numeric=False
                ),
            ),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=300,
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                    class_weight="balanced",
                ),
            ),
        ]
    )

    models["gradient_boosting"] = Pipeline(
        [
            (
                "preprocessor",
                build_preprocessor(
                    scale_numeric=False
                ),
            ),
            (
                "classifier",
                HistGradientBoostingClassifier(
                    max_iter=200,
                    learning_rate=0.05,
                    max_leaf_nodes=15,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )

    return models
