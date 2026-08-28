from pathlib import Path

DATASET_PATH = Path("dataset/dataset.csv")
RANDOM_STATE = 42
TEST_SIZE = 0.2

TARGET = "meaningful"

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
