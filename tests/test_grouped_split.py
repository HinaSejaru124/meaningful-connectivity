import pandas as pd

from models.train import build_grouped_split


def test_grouped_split_keeps_sessions_disjoint():
    df = pd.DataFrame(
        {
            "session_id": ["s1", "s1", "s2", "s2", "s3", "s3", "s4", "s4"],
            "bandwidth": [1, 1, 2, 2, 3, 3, 4, 4],
            "concurrent_users": [1, 1, 2, 2, 3, 3, 4, 4],
            "deadline_seconds": [10, 10, 20, 20, 30, 30, 40, 40],
            "interaction_level": [0, 0, 1, 1, 0, 0, 1, 1],
            "jitter": [1, 1, 2, 2, 3, 3, 4, 4],
            "latency": [5, 5, 10, 10, 15, 15, 20, 20],
            "packet_loss": [0, 0, 1, 1, 0, 0, 1, 1],
            "resource_size_mb": [1, 1, 2, 2, 3, 3, 4, 4],
            "service_type": ["pdf", "pdf", "web", "web", "pdf", "pdf", "web", "web"],
            "meaningful": [0, 0, 1, 1, 0, 0, 1, 1],
        }
    )

    X_train, X_test, y_train, y_test, train_sessions, test_sessions = build_grouped_split(
        df,
        test_size=0.5,
        random_state=42,
    )

    assert X_train.shape[0] == y_train.shape[0]
    assert X_test.shape[0] == y_test.shape[0]
    assert set(train_sessions).isdisjoint(set(test_sessions))
    assert "session_id" not in X_train.columns
    assert "session_id" not in X_test.columns
