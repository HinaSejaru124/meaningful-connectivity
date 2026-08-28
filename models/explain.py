"""
MEANINGFUL CONNECTIVITY — SHAP EXPLAINABILITY
==============================================

Analyse explicable des modèles de classification.

Modèles :
    - Logistic Regression
    - Random Forest
    - HistGradientBoosting

SHAP :
    - LinearExplainer pour Logistic Regression
    - TreeExplainer pour les modèles à arbres

La classe expliquée est toujours :
    meaningful = 1

Le prétraitement est exactement celui utilisé pendant
l'entraînement des modèles.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import (
    RandomForestClassifier,
    HistGradientBoostingClassifier,
)

from .config import (
    DATASET_PATH,
    RANDOM_STATE,
    TEST_SIZE,
)
from .data_loader import load_dataset
from .train import build_models


# ============================================================================
# CONFIGURATION
# ============================================================================

OUTPUT_DIR = Path("models/explanations")

# Première observation du jeu de test pour l'explication locale.
LOCAL_INDEX = 0


# ============================================================================
# UTILITAIRES
# ============================================================================

def get_feature_names(preprocessor):
    """
    Récupère les noms des features après transformation sklearn.
    """

    return list(
        preprocessor.get_feature_names_out()
    )


def clean_feature_name(name):
    """
    Supprime les préfixes ajoutés par ColumnTransformer.

    Exemple :
        numeric__bandwidth
            -> bandwidth

        categorical__service_type_pdf
            -> service_type_pdf
    """

    if "__" in name:
        name = name.split(
            "__",
            1,
        )[1]

    return name


def normalize_feature_names(feature_names):
    return [
        clean_feature_name(name)
        for name in feature_names
    ]


# ============================================================================
# CONSTRUCTION DE L'EXPLAINER
# ============================================================================

def build_explainer(
    classifier,
    X_train_transformed,
):
    """
    Construit l'explainer SHAP approprié au modèle.

    LogisticRegression :
        LinearExplainer

    RandomForestClassifier :
        TreeExplainer

    HistGradientBoostingClassifier :
        TreeExplainer
    """

    if isinstance(
        classifier,
        LogisticRegression,
    ):
        print(
            "Explainer : LinearExplainer"
        )

        return shap.LinearExplainer(
            classifier,
            X_train_transformed,
        )

    if isinstance(
        classifier,
        (
            RandomForestClassifier,
            HistGradientBoostingClassifier,
        ),
    ):
        print(
            "Explainer : TreeExplainer"
        )

        return shap.TreeExplainer(
            classifier,
        )

    raise TypeError(
        "Modèle non supporté par l'analyse SHAP : "
        f"{type(classifier)}"
    )


# ============================================================================
# CALCUL SHAP
# ============================================================================

def build_shap_explanation(
    model,
    X_train,
    X_test,
):
    """
    Transforme les données puis calcule les valeurs SHAP.

    Le pipeline sklearn est :

        données brutes
             ↓
        preprocessing
             ↓
        classifier

    SHAP est appliqué au classifier sur les données transformées.
    """

    preprocessor = model.named_steps[
        "preprocessor"
    ]

    classifier = model.named_steps[
        "classifier"
    ]

    # ------------------------------------------------------------------------
    # Transformation
    # ------------------------------------------------------------------------

    X_train_transformed = (
        preprocessor.transform(
            X_train
        )
    )

    X_test_transformed = (
        preprocessor.transform(
            X_test
        )
    )

    feature_names = normalize_feature_names(
        get_feature_names(
            preprocessor
        )
    )

    print(
        f"Train transformé : "
        f"{X_train_transformed.shape}"
    )

    print(
        f"Test transformé  : "
        f"{X_test_transformed.shape}"
    )

    # ------------------------------------------------------------------------
    # Explainer adapté au modèle
    # ------------------------------------------------------------------------

    explainer = build_explainer(
        classifier,
        X_train_transformed,
    )

    # ------------------------------------------------------------------------
    # Valeurs SHAP
    # ------------------------------------------------------------------------

    raw_shap_values = explainer.shap_values(
        X_test_transformed
    )

    return (
        explainer,
        raw_shap_values,
        X_train_transformed,
        X_test_transformed,
        feature_names,
    )


# ============================================================================
# NORMALISATION DES VALEURS SHAP
# ============================================================================

def extract_positive_class_shap_values(
    shap_values,
    n_samples,
    n_features,
):
    """
    Normalise les différentes structures possibles retournées
    par SHAP.

    Objectif :
        obtenir systématiquement

            (n_samples, n_features)

    pour la classe :

        meaningful = 1
    """

    # ------------------------------------------------------------------------
    # Liste de matrices
    #
    # Anciennes versions de SHAP :
    #
    # [
    #     classe_0,
    #     classe_1
    # ]
    # ------------------------------------------------------------------------

    if isinstance(
        shap_values,
        list,
    ):

        if len(shap_values) >= 2:

            values = np.asarray(
                shap_values[1]
            )

        elif len(shap_values) == 1:

            values = np.asarray(
                shap_values[0]
            )

        else:

            raise ValueError(
                "SHAP a retourné une liste vide."
            )

        if values.ndim != 2:

            raise ValueError(
                "Structure SHAP inattendue : "
                f"{values.shape}"
            )

        return values

    values = np.asarray(
        shap_values
    )

    # ------------------------------------------------------------------------
    # Cas standard :
    #
    # (n_samples, n_features)
    # ------------------------------------------------------------------------

    if values.ndim == 2:

        expected_shape = (
            n_samples,
            n_features,
        )

        if values.shape != expected_shape:

            raise ValueError(
                "Dimensions SHAP inattendues : "
                f"{values.shape}. "
                f"Attendu : {expected_shape}"
            )

        return values

    # ------------------------------------------------------------------------
    # Cas multi-output :
    #
    # (n_samples, n_features, n_classes)
    # ------------------------------------------------------------------------

    if values.ndim == 3:

        if values.shape[0] != n_samples:

            raise ValueError(
                "Nombre d'observations SHAP incohérent : "
                f"{values.shape}"
            )

        if values.shape[1] != n_features:

            raise ValueError(
                "Nombre de features SHAP incohérent : "
                f"{values.shape}"
            )

        # Classe positive.
        if values.shape[2] >= 2:

            return values[:, :, 1]

        return values[:, :, 0]

    raise ValueError(
        "Structure SHAP non supportée : "
        f"shape={values.shape}"
    )


# ============================================================================
# VALEUR DE BASE
# ============================================================================

def extract_positive_class_base_value(
    explainer,
):
    """
    Récupère la valeur de base correspondant à la classe meaningful = 1.
    """

    expected_value = (
        explainer.expected_value
    )

    # Tableau / liste
    if isinstance(
        expected_value,
        (list, tuple, np.ndarray),
    ):

        values = np.asarray(
            expected_value
        ).reshape(-1)

        if len(values) >= 2:

            return float(
                values[1]
            )

        if len(values) == 1:

            return float(
                values[0]
            )

        raise ValueError(
            "expected_value SHAP est vide."
        )

    return float(
        expected_value
    )


# ============================================================================
# SUMMARY PLOT
# ============================================================================

def save_summary_plot(
    shap_values,
    X_test_transformed,
    feature_names,
    model_name,
):
    """
    Produit le summary plot SHAP.

    Il permet d'observer :
        - l'importance globale ;
        - la dispersion des contributions ;
        - le sens de l'influence des variables.
    """

    plt.figure()

    shap.summary_plot(
        shap_values,
        X_test_transformed,
        feature_names=feature_names,
        show=False,
    )

    plt.title(
        f"SHAP Summary — {model_name}"
    )

    plt.tight_layout()

    output_path = (
        OUTPUT_DIR
        / f"{model_name}_summary.png"
    )

    plt.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Graphique sauvegardé : "
        f"{output_path}"
    )


# ============================================================================
# IMPORTANCE GLOBALE
# ============================================================================

def save_importance_plot(
    shap_values,
    feature_names,
    model_name,
):
    """
    Calcule et représente :

        mean(|SHAP|)

    pour chaque feature.
    """

    mean_abs_shap = np.mean(
        np.abs(
            shap_values
        ),
        axis=0,
    )

    importance = pd.DataFrame(
        {
            "feature": feature_names,
            "mean_abs_shap": mean_abs_shap,
        }
    )

    importance = (
        importance
        .sort_values(
            "mean_abs_shap",
            ascending=True,
        )
    )

    plt.figure(
        figsize=(10, 6)
    )

    plt.barh(
        importance["feature"],
        importance["mean_abs_shap"],
    )

    plt.xlabel(
        "Mean absolute SHAP value"
    )

    plt.ylabel(
        "Feature"
    )

    plt.title(
        f"Global Feature Importance — "
        f"{model_name}"
    )

    plt.tight_layout()

    output_path = (
        OUTPUT_DIR
        / f"{model_name}_importance.png"
    )

    plt.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Graphique sauvegardé : "
        f"{output_path}"
    )

    return importance


# ============================================================================
# EXPLICATION LOCALE
# ============================================================================

def save_local_explanation(
    explainer,
    shap_values,
    X_test_transformed,
    feature_names,
    X_test,
    model,
    model_name,
):
    """
    Produit une explication locale pour une observation.

    Le waterfall reçoit explicitement UNE observation
    et UNE classe.
    """

    if len(
        X_test_transformed
    ) == 0:

        raise ValueError(
            "Le jeu de test est vide."
        )

    index = min(
        LOCAL_INDEX,
        len(X_test_transformed) - 1,
    )

    # ------------------------------------------------------------------------
    # SHAP de la classe meaningful = 1
    # ------------------------------------------------------------------------

    positive_values = (
        extract_positive_class_shap_values(
            shap_values,
            n_samples=len(
                X_test_transformed
            ),
            n_features=len(
                feature_names
            ),
        )
    )

    sample_shap = (
        positive_values[index]
    )

    # ------------------------------------------------------------------------
    # Valeur de base
    # ------------------------------------------------------------------------

    base_value = (
        extract_positive_class_base_value(
            explainer
        )
    )

    # ------------------------------------------------------------------------
    # Observation transformée
    # ------------------------------------------------------------------------

    sample = np.asarray(
        X_test_transformed[index]
    )

    # ------------------------------------------------------------------------
    # Explication SHAP explicite
    # ------------------------------------------------------------------------

    explanation = shap.Explanation(
        values=sample_shap,
        base_values=base_value,
        data=sample,
        feature_names=feature_names,
    )

    # ------------------------------------------------------------------------
    # Waterfall
    # ------------------------------------------------------------------------

    shap.plots.waterfall(
        explanation,
        max_display=len(
            feature_names
        ),
        show=False,
    )

    plt.title(
        f"Local SHAP Explanation — "
        f"{model_name} — "
        f"Test sample {index}"
    )

    plt.tight_layout()

    output_path = (
        OUTPUT_DIR
        / f"{model_name}_waterfall.png"
    )

    plt.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Graphique sauvegardé : "
        f"{output_path}"
    )

    # ------------------------------------------------------------------------
    # Prédiction
    # ------------------------------------------------------------------------

    original_sample = X_test.iloc[
        [index]
    ]

    prediction = int(
        model.predict(
            original_sample
        )[0]
    )

    probability = float(
        model.predict_proba(
            original_sample
        )[0, 1]
    )

    # ------------------------------------------------------------------------
    # Contributions triées
    # ------------------------------------------------------------------------

    contributions = []

    for i, feature in enumerate(
        feature_names
    ):

        contributions.append(
            {
                "feature": feature,
                "shap_value": float(
                    sample_shap[i]
                ),
                "absolute_shap": float(
                    abs(sample_shap[i])
                ),
            }
        )

    contributions.sort(
        key=lambda x: x[
            "absolute_shap"
        ],
        reverse=True,
    )

    return {
        "test_index": int(
            index
        ),
        "prediction": prediction,
        "prediction_name": (
            "meaningful"
            if prediction == 1
            else "not meaningful"
        ),
        "probability_meaningful": probability,
        "base_value": base_value,
        "features": contributions,
    }


# ============================================================================
# SAUVEGARDE JSON
# ============================================================================

def save_local_json(
    explanation,
    model_name,
):
    """
    Sauvegarde l'explication locale au format JSON.
    """

    output_path = (
        OUTPUT_DIR
        / f"{model_name}_local.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            explanation,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Explication locale sauvegardée : "
        f"{output_path}"
    )


# ============================================================================
# MAIN
# ============================================================================

def main():

    print("=" * 70)
    print(
        "MEANINGFUL CONNECTIVITY — "
        "SHAP EXPLAINABILITY"
    )
    print("=" * 70)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------------------
    # Dataset
    # ------------------------------------------------------------------------

    X, y, df = load_dataset()

    print()
    print(
        f"Dataset       : "
        f"{DATASET_PATH}"
    )

    print(
        f"Observations  : "
        f"{len(df)}"
    )

    # ------------------------------------------------------------------------
    # Split identique à run_experiments.py
    # ------------------------------------------------------------------------

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=y,
        )
    )

    print(
        f"Train         : "
        f"{len(X_train)}"
    )

    print(
        f"Test          : "
        f"{len(X_test)}"
    )

    print()

    # ------------------------------------------------------------------------
    # Modèles
    # ------------------------------------------------------------------------

    models = build_models()

    for model_name, model in models.items():

        print("-" * 70)
        print(
            f"SHAP — {model_name}"
        )
        print("-" * 70)

        # --------------------------------------------------------------------
        # Entraînement
        # --------------------------------------------------------------------

        model.fit(
            X_train,
            y_train,
        )

        # --------------------------------------------------------------------
        # SHAP
        # --------------------------------------------------------------------

        (
            explainer,
            raw_shap_values,
            X_train_transformed,
            X_test_transformed,
            feature_names,
        ) = build_shap_explanation(
            model,
            X_train,
            X_test,
        )

        # --------------------------------------------------------------------
        # Classe positive
        # --------------------------------------------------------------------

        shap_values = (
            extract_positive_class_shap_values(
                raw_shap_values,
                n_samples=len(
                    X_test_transformed
                ),
                n_features=len(
                    feature_names
                ),
            )
        )

        # --------------------------------------------------------------------
        # Global summary
        # --------------------------------------------------------------------

        save_summary_plot(
            shap_values,
            X_test_transformed,
            feature_names,
            model_name,
        )

        # --------------------------------------------------------------------
        # Global importance
        # --------------------------------------------------------------------

        importance = (
            save_importance_plot(
                shap_values,
                feature_names,
                model_name,
            )
        )

        # --------------------------------------------------------------------
        # Local explanation
        # --------------------------------------------------------------------

        local_explanation = (
            save_local_explanation(
                explainer,
                raw_shap_values,
                X_test_transformed,
                feature_names,
                X_test,
                model,
                model_name,
            )
        )

        # --------------------------------------------------------------------
        # Vérité terrain
        # --------------------------------------------------------------------

        local_index = (
            local_explanation[
                "test_index"
            ]
        )

        true_label = int(
            y_test.iloc[
                local_index
            ]
        )

        local_explanation[
            "true_label"
        ] = true_label

        local_explanation[
            "true_label_name"
        ] = (
            "meaningful"
            if true_label == 1
            else "not meaningful"
        )

        # --------------------------------------------------------------------
        # Sauvegarde
        # --------------------------------------------------------------------

        save_local_json(
            local_explanation,
            model_name,
        )

        # --------------------------------------------------------------------
        # Résumé console
        # --------------------------------------------------------------------

        print()
        print(
            f"Observation locale : "
            f"{local_index}"
        )

        print(
            f"Vraie classe       : "
            f"{local_explanation['true_label_name']}"
        )

        print(
            f"Prédiction         : "
            f"{local_explanation['prediction_name']}"
        )

        print(
            f"P(meaningful)      : "
            f"{local_explanation['probability_meaningful']:.4f}"
        )

        print()
        print(
            "Top features SHAP :"
        )

        for feature in (
            importance
            .sort_values(
                "mean_abs_shap",
                ascending=False,
            )
            .head(5)
            .itertuples()
        ):

            print(
                f"  {feature.feature:<30} "
                f"{feature.mean_abs_shap:.6f}"
            )

        print()

    print("=" * 70)
    print(
        "Analyse SHAP terminée."
    )

    print(
        f"Résultats : "
        f"{OUTPUT_DIR}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()