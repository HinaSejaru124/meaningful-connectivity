"""
scenarios/quiz.py

Scénario de consultation d'un quiz éducatif : requête HTTP vers un
fichier JSON statique servi par le serveur (représentant la réponse
d'un appel API récupérant les questions). Contrat identique à
PDFScenario — seul le répertoire scanné et les seuils de l'oracle
changent.
"""

from pathlib import Path

from .base import Scenario
from simulation.utils.net_utils import encode_path_component


class QuizScenario(Scenario):
    """
    Scénario de consultation de quiz.

    Les ressources disponibles sont découvertes automatiquement
    depuis htdocs/quiz/. Un quiz réel étant une réponse API légère
    (quelques Ko à quelques dizaines de Ko), la tolérance temporelle
    est bien plus stricte que pour un PDF.
    """

    name = "quiz"
    interaction_level = 1        # au-dessus de "passif" (PDF) : nécessite une réponse rapide
    deadline_seconds = 1.0        # un quiz qui met plus d'1s à charger casse l'interaction

    QUIZ_DIR = Path(__file__).parent.parent / "htdocs" / "quiz"

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.QUIZ_DIR.exists():
            raise RuntimeError(f"Répertoire quiz introuvable : {self.QUIZ_DIR}")

        files = []

        for quiz_file in sorted(self.QUIZ_DIR.glob("*.json"), key=lambda p: p.name):
            size_bytes = quiz_file.stat().st_size

            files.append({
                "name": quiz_file.name,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 3),
            })

        if not files:
            raise RuntimeError(f"Aucun fichier quiz trouvé dans {self.QUIZ_DIR}")

        self._resources_cache = files
        return files

    def run_client_action(
        self,
        client_host,
        server,
        resource: dict,
        client_id: str,
        session_id: str,
    ) -> dict:

        resource_name = resource["name"]
        resource_size_bytes = resource["size_bytes"]
        resource_size_mb = resource["size_mb"]

        output_path = f"/tmp/mc_{session_id}_{client_id}_quiz.json"

        timeout = f"{self.deadline_seconds:g}"

        cmd = (
            f"rm -f {output_path} && "
            "curl -s "
            f"--max-time {timeout} "
            f"-o {output_path} "
            "-w '%{http_code} %{time_total} %{size_download}' "
            f"'http://{server.IP()}:8000/quiz/{encode_path_component(resource_name)}'"
        )

        raw = client_host.cmd(cmd).strip()

        try:
            return self._parse_result(
                raw,
                output_path,
                resource_name,
                resource_size_bytes,
                resource_size_mb,
            )
        finally:
            try:
                Path(output_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _parse_result(
        self,
        raw: str,
        output_path: str,
        resource_name: str,
        resource_size_bytes: int,
        resource_size_mb: float,
    ) -> dict:

        if not raw:
            return {
                "download_time": float(self.deadline_seconds),
                "http_status": 0,
                "downloaded_size_bytes": 0,
                "transfer_completed": False,
                "timed_out": True,
                "within_deadline": False,
                "resource": resource_name,
                "resource_size_mb": resource_size_mb,
                "error": "curl timeout",
            }

        parts = raw.split()

        if len(parts) != 3:
            return {
                "download_time": float("inf"),
                "http_status": 0,
                "downloaded_size_bytes": 0,
                "transfer_completed": False,
                "timed_out": False,
                "within_deadline": False,
                "resource": resource_name,
                "resource_size_mb": resource_size_mb,
                "error": raw,
            }

        try:
            http_status = int(parts[0])
            download_time = float(parts[1])
            curl_downloaded_bytes = int(float(parts[2]))
        except ValueError:
            return {
                "download_time": float("inf"),
                "http_status": 0,
                "downloaded_size_bytes": 0,
                "transfer_completed": False,
                "timed_out": False,
                "within_deadline": False,
                "resource": resource_name,
                "resource_size_mb": resource_size_mb,
                "error": raw,
            }

        output = Path(output_path)
        actual_size_bytes = output.stat().st_size if output.exists() else 0

        # Alignement avec PDFScenario : un statut 200 ne suffit pas, on
        # vérifie que le contenu reçu correspond réellement à la taille
        # attendue (un transfert tronqué avec statut 200 reste rare,
        # mais silencieusement mal classé sans cette vérification).
        transfer_completed = (
            http_status == 200
            and actual_size_bytes == resource_size_bytes
            and curl_downloaded_bytes == resource_size_bytes
        )

        within_deadline = download_time < self.deadline_seconds

        return {
            "download_time": download_time,
            "http_status": http_status,
            # Présent pour parité avec PDFScenario : dans les sessions
            # où le transfert échoue (deadline très serrée à 0.5s),
            # download_time est plafonné par --max-time et ne reflète
            # pas la contention réelle — downloaded_size_bytes reste la
            # métrique informative dans ce régime.
            "downloaded_size_bytes": actual_size_bytes,
            "transfer_completed": transfer_completed,
            "timed_out": download_time >= self.deadline_seconds,
            "within_deadline": within_deadline,
            "resource": resource_name,
            "resource_size_mb": resource_size_mb,
            "error": None if (transfer_completed and within_deadline) else (
                "deadline exceeded"
                if not within_deadline
                else "incomplete transfer"
                if not transfer_completed
                else None
            ),
        }

    def is_successful(self, metrics: dict) -> bool:
        if metrics.get("http_status") != 200:
            return False

        if not metrics.get("transfer_completed", False):
            return False

        if metrics.get("timed_out", False):
            return False

        return metrics.get("download_time", float("inf")) < self.deadline_seconds