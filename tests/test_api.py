from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "models_loaded" in payload


def test_predict_rejects_invalid_input():
    response = client.post(
        "/predict",
        json={
            "model": "gradient_boosting",
            "bandwidth": -1,
            "concurrent_users": 2,
            "deadline_seconds": 10,
            "interaction_level": 0,
            "jitter": 5,
            "latency": 50,
            "packet_loss": 1,
            "resource_size_mb": 2,
            "service_type": "pdf",
        },
    )
    assert response.status_code == 422


def test_train_with_missing_dataset_fails_cleanly():
    response = client.post(
        "/models/train",
        json={"dataset_path": "/tmp/definitely_missing_dataset.csv"},
    )
    assert response.status_code == 404
    assert "dataset" in response.json()["detail"].lower()


def test_explain_without_loaded_model_fails_cleanly():
    payload = {
        "model": "gradient_boosting",
        "bandwidth": 2.5,
        "concurrent_users": 4,
        "deadline_seconds": 10,
        "interaction_level": 0,
        "jitter": 12.3,
        "latency": 85.0,
        "packet_loss": 1.2,
        "resource_size_mb": 3.4,
        "service_type": "pdf",
    }
    response = client.post("/explain", json=payload)
    assert response.status_code in {400, 404}
