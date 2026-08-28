import csv
from pathlib import Path

from simulation.dataset_schema import (
    ALLOWED_FEATURE_COLUMNS,
    IDENTIFIER_COLUMNS,
    TARGET_COLUMN,
    validate_row,
)


class DatasetWriter:
    """Écrit une ligne dans le dataset d'apprentissage.

    Une ligne = une observation individuelle (un utilisateur, dans une
    session donnée). Seules les variables connues avant le début de la
    session sont stockées comme features. Les mesures post-session
    restent conservées dans les logs de reproduction, pas dans le
    tableau d'entraînement.

    session_id / client_id sont conservés pour permettre un split
    train/test groupé par session (les observations d'une même session
    ne sont pas indépendantes) — ce ne sont PAS des features ML.
    """

    def __init__(self, dataset_path: str = "dataset/dataset.csv"):
        self.dataset_path = Path(dataset_path)
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)

        # Ordre déterministe : identifiants d'abord, puis features
        # triées, puis cible en dernière colonne — dérivé du contrat
        # central, jamais recopié à la main.
        self.fieldnames = (
            sorted(IDENTIFIER_COLUMNS)
            + sorted(ALLOWED_FEATURE_COLUMNS)
            + [TARGET_COLUMN]
        )

    def append_row(self, row: dict) -> Path:
        validate_row(row)

        file_exists = self.dataset_path.exists()

        with self.dataset_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow(row)

        return self.dataset_path