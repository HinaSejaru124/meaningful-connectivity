import json
from pathlib import Path


class MeasurementCollector:
    """Collecte les mesures d’une session et les stocke en JSON pour traçabilité."""

    @staticmethod
    def collect(run_results: list[dict]) -> dict:
        metrics = []
        for result in run_results:
            metrics.append(
                {
                    "client": result["client"],
                    **result["metrics"],
                }
            )
        return {
            "observed_clients": len(metrics),
            "samples": metrics,
        }

    @staticmethod
    def save_metrics(metrics: dict, logs_dir: str) -> Path:
        path = Path(logs_dir) / "metrics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        return path
