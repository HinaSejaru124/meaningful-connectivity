import pandas as pd

from .config import RANDOM_STATE, TEST_SIZE
from .data_loader import load_dataset
from .evaluate import evaluate_model
from .train import build_grouped_split, build_models, select_model_with_grouped_cv


def main():

    print("=" * 70)
    print("MEANINGFUL CONNECTIVITY — MODEL COMPARISON (session-aware split)")
    print("=" * 70)
    print("Note: le benchmark historique aléatoire non groupé est conservé comme référence préliminaire, mais n'est plus utilisé comme protocole final.")

    _, _, df = load_dataset()

    X_train, X_test, y_train, y_test, train_sessions, test_sessions = build_grouped_split(
        df,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
    )

    print()
    print(f"Observations totales : {len(df)}")
    print(f"Sessions totales     : {df['session_id'].nunique()}")
    print(f"Sessions train       : {len(set(train_sessions))}")
    print(f"Sessions test        : {len(set(test_sessions))}")
    print(f"Observations train   : {len(X_train)}")
    print(f"Observations test    : {len(X_test)}")
    print()
    print("Distribution cible par train/test :")
    print(
        pd.DataFrame(
            {
                "train": {
                    "not_meaningful": int((y_train == 0).sum()),
                    "meaningful": int((y_train == 1).sum()),
                },
                "test": {
                    "not_meaningful": int((y_test == 0).sum()),
                    "meaningful": int((y_test == 1).sum()),
                },
            }
        )
    )

    print()
    print("Validation croisée groupée sur TRAIN (GroupKFold) :")
    selection = select_model_with_grouped_cv(X_train, y_train, train_sessions)
    for item in selection["results"]:
        print(
            f"- {item['model']}: ROC-AUC moyen = {item['cv_roc_auc_mean']:.4f} ± {item['cv_roc_auc_std']:.4f}"
        )

    best_model_name = selection["best_model_name"]
    print(f"Modèle sélectionné : {best_model_name}")

    model = build_models()[best_model_name]
    model.fit(X_train, y_train)

    final_metrics = evaluate_model(model, X_test, y_test)

    print()
    print("Métriques finales sur TEST indépendant :")
    print(f"Accuracy  : {final_metrics['accuracy']:.4f}")
    print(f"Precision : {final_metrics['precision']:.4f}")
    print(f"Recall    : {final_metrics['recall']:.4f}")
    print(f"F1        : {final_metrics['f1']:.4f}")
    print(f"ROC-AUC   : {final_metrics['roc_auc']:.4f}")
    print(
        "Confusion matrix : "
        f"TN={final_metrics['tn']} "
        f"FP={final_metrics['fp']} "
        f"FN={final_metrics['fn']} "
        f"TP={final_metrics['tp']}"
    )

    print()
    print("Comparaison des trois modèles sur le TEST (après sélection interne sur TRAIN) :")
    results = []
    for name, candidate in build_models().items():
        candidate.fit(X_train, y_train)
        metrics = evaluate_model(candidate, X_test, y_test)
        metrics["model"] = name
        results.append(metrics)

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
