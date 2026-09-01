
from pathlib import Path


# Racine du projet
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Dataset d'entraînement
DATASET_PATH = PROJECT_ROOT / "dataset" / "dataset.csv"
MODEL_DIR = PROJECT_ROOT / "models" / "artifacts"

# Reproductibilité
RANDOM_STATE = 42
TEST_SIZE = 0.2

# Cible
TARGET = "meaningful"

# Features utilisées par les modèles
FEATURES = [
    "bandwidth",
    "concurrent_users",
    "deadline_seconds",
    "interaction_level",
    "jitter",
    "latency",
    "packet_loss",
    "resource_size_mb",
    "service_type",
]

DEFAULT_MODEL = "gradient_boosting"

AVAILABLE_MODELS = (
    "logistic_regression",
    "random_forest",
    "gradient_boosting",
)

API_TITLE = "Meaningful Connectivity — Explainable Assessment API"
API_DESCRIPTION = (
    "API d'évaluation de la Meaningful Connectivity. "
    "Elle expose les prédictions des modèles de classification "
    "et leurs explications."
)
API_VERSION = "1.0.0"

