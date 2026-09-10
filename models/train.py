from sklearn.base import clone
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_score
from sklearn.pipeline import Pipeline

from .config import FEATURES, RANDOM_STATE, TARGET
from .evaluate import evaluate_model
from .preprocessing import build_preprocessor


def build_grouped_split(df, test_size=0.2, random_state=42):
    """Split session-aware while keeping every session entirely on one side."""

    required_columns = {"session_id", TARGET} | set(FEATURES)
    missing = sorted(required_columns - set(df.columns))
    if missing:
        raise ValueError(
            "Colonnes manquantes pour le split groupé : " + ", ".join(missing)
        )

    X = df[list(FEATURES)].copy()
    y = df[TARGET].astype(int)
    groups = df["session_id"]

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=test_size,
        random_state=random_state,
    )

    train_idx, test_idx = next(splitter.split(X, y, groups=groups))

    X_train = X.iloc[train_idx].copy()
    X_test = X.iloc[test_idx].copy()
    y_train = y.iloc[train_idx].copy()
    y_test = y.iloc[test_idx].copy()

    train_sessions = df.iloc[train_idx]["session_id"].tolist()
    test_sessions = df.iloc[test_idx]["session_id"].tolist()

    if set(train_sessions).intersection(test_sessions):
        raise AssertionError(
            "Fuite de session détectée : des session_id sont présents dans train et test."
        )

    if "session_id" in X_train.columns or "session_id" in X_test.columns:
        raise ValueError("session_id ne doit pas figurer dans les features ML.")

    return X_train, X_test, y_train, y_test, train_sessions, test_sessions


def build_models():

    models = {}

    models["logistic_regression"] = Pipeline(
        [
            (
                "preprocessor",
                build_preprocessor(scale_numeric=True),
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
                build_preprocessor(scale_numeric=False),
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
                build_preprocessor(scale_numeric=False),
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


def select_model_with_grouped_cv(X_train, y_train, train_sessions):
    """Choix du modèle par validation croisée groupée sur TRAIN uniquement."""

    n_sessions = len(set(train_sessions))
    n_splits = min(5, max(2, n_sessions))
    if n_sessions < 2:
        raise ValueError("Il faut au moins 2 sessions dans le train pour la CV groupée.")

    cv = GroupKFold(n_splits=n_splits)
    model_candidates = build_models()
    results = []

    for model_name, model in model_candidates.items():
        scores = cross_val_score(
            model,
            X_train,
            y_train,
            groups=train_sessions,
            cv=cv,
            scoring="roc_auc",
        )

        results.append(
            {
                "model": model_name,
                "cv_roc_auc_mean": float(scores.mean()),
                "cv_roc_auc_std": float(scores.std()),
                "cv_scores": [float(s) for s in scores],
            }
        )

    best = max(results, key=lambda item: item["cv_roc_auc_mean"])
    final_model = clone(model_candidates[best["model"]])

    return {
        "results": results,
        "best_model_name": best["model"],
        "best_model": final_model,
    }


def run_grouped_experiment(df, test_size=0.2, random_state=42):
    """Pipeline complet: split groupé, sélection interne, entraînement final, test final."""

    X_train, X_test, y_train, y_test, train_sessions, test_sessions = build_grouped_split(
        df,
        test_size=test_size,
        random_state=random_state,
    )

    selection = select_model_with_grouped_cv(X_train, y_train, train_sessions)
    selected_model = selection["best_model"]
    selected_model.fit(X_train, y_train)
    final_metrics = evaluate_model(selected_model, X_test, y_test)

    session_summary = {
        "total_observations": int(len(df)),
        "n_sessions": int(df["session_id"].nunique()),
        "train_sessions": int(len(set(train_sessions))),
        "test_sessions": int(len(set(test_sessions))),
        "train_observations": int(len(X_train)),
        "test_observations": int(len(X_test)),
        "train_target_distribution": {
            "not_meaningful": int((y_train == 0).sum()),
            "meaningful": int((y_train == 1).sum()),
        },
        "test_target_distribution": {
            "not_meaningful": int((y_test == 0).sum()),
            "meaningful": int((y_test == 1).sum()),
        },
    }

    return {
        "train": {
            "X": X_train,
            "y": y_train,
            "sessions": train_sessions,
        },
        "test": {
            "X": X_test,
            "y": y_test,
            "sessions": test_sessions,
        },
        "selection": selection,
        "final_model": selected_model,
        "final_metrics": final_metrics,
        "session_summary": session_summary,
    }
