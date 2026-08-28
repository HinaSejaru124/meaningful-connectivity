import pandas as pd

from .config import DATASET_PATH, FEATURES, TARGET


def load_dataset(path=DATASET_PATH):
    df = pd.read_csv(path)

    required_columns = set(FEATURES + [TARGET])
    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            "Colonnes manquantes dans le dataset : "
            + ", ".join(sorted(missing))
        )

    if df.empty:
        raise ValueError("Le dataset est vide.")

    X = df[FEATURES].copy()
    y = df[TARGET].astype(int)

    return X, y, df
