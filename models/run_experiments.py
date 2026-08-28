import pandas as pd

from sklearn.model_selection import train_test_split

from .config import RANDOM_STATE, TEST_SIZE
from .data_loader import load_dataset
from .evaluate import evaluate_model
from .train import build_models


def main():

    print("=" * 70)
    print("MEANINGFUL CONNECTIVITY — MODEL COMPARISON")
    print("=" * 70)

    X, y, df = load_dataset()

    print()
    print(f"Observations : {len(df)}")
    print(f"Features     : {X.shape[1]}")
    print()

    print("Distribution de la cible :")
    print(
        y.value_counts()
        .sort_index()
        .rename(
            index={
                0: "not meaningful",
                1: "meaningful",
            }
        )
    )

    print()

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    print(
        f"Train : {len(X_train)} observations"
    )
    print(
        f"Test  : {len(X_test)} observations"
    )

    print()

    models = build_models()
    results = []

    for name, model in models.items():

        print("-" * 70)
        print(f"Entraînement : {name}")

        model.fit(
            X_train,
            y_train,
        )

        metrics = evaluate_model(
            model,
            X_test,
            y_test,
        )

        metrics["model"] = name
        results.append(metrics)

        print(
            f"Accuracy  : {metrics['accuracy']:.4f}"
        )
        print(
            f"Precision : {metrics['precision']:.4f}"
        )
        print(
            f"Recall    : {metrics['recall']:.4f}"
        )
        print(
            f"F1        : {metrics['f1']:.4f}"
        )
        print(
            f"ROC-AUC   : {metrics['roc_auc']:.4f}"
        )

        print(
            "Confusion matrix : "
            f"TN={metrics['tn']} "
            f"FP={metrics['fp']} "
            f"FN={metrics['fn']} "
            f"TP={metrics['tp']}"
        )

    print()
    print("=" * 70)
    print("COMPARAISON")
    print("=" * 70)

    results_df = pd.DataFrame(results)

    print(
        results_df[
            [
                "model",
                "accuracy",
                "precision",
                "recall",
                "f1",
                "roc_auc",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
