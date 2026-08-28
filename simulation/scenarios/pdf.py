from pathlib import Path

from .base import Scenario
from simulation.utils.net_utils import encode_path_component


class PDFScenario(Scenario):
    """
    Scénario de téléchargement PDF.

    Les ressources disponibles sont découvertes automatiquement
    depuis htdocs/pdf/, triées par nom (déterminisme) et mises en
    cache après le premier appel.

    Contrat applicatif :
        - interaction_level = 0 : consultation passive
        - deadline_seconds = 10 s : temps maximal acceptable
        - meaningful = transfert complet du PDF avant la deadline

    Le statut HTTP 200 ne suffit PAS à considérer le transfert
    comme terminé : la taille réellement reçue est vérifiée.
    """

    name = "pdf"

    # ------------------------------------------------------------------
    # Contrat applicatif
    # ------------------------------------------------------------------

    interaction_level = 0
    deadline_seconds = 10.0

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    PDF_DIR = Path(__file__).parent.parent / "htdocs" / "pdf"

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    # ------------------------------------------------------------------
    # Découverte des ressources
    # ------------------------------------------------------------------

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.PDF_DIR.exists():
            raise RuntimeError(
                f"Répertoire PDF introuvable : {self.PDF_DIR}"
            )

        files = []

        # Tri explicite par nom : glob() ne garantit aucun ordre stable
        # entre exécutions, ce qui casserait la reproductibilité de
        # select_resource(rng) malgré une seed fixée.
        for pdf in sorted(self.PDF_DIR.glob("*.pdf"), key=lambda p: p.name):
            size_bytes = pdf.stat().st_size

            files.append(
                {
                    "name": pdf.name,
                    "size_bytes": size_bytes,
                    "size_mb": round(
                        size_bytes / (1024 * 1024),
                        3,
                    ),
                }
            )

        if not files:
            raise RuntimeError(
                f"Aucun fichier PDF trouvé dans {self.PDF_DIR}"
            )

        self._resources_cache = files
        return files

    # ------------------------------------------------------------------
    # Action client
    # ------------------------------------------------------------------

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

        # Chemin unique par (session, client) : plusieurs clients actifs
        # s'exécutent en parallèle et partagent le même filesystem
        # (les hôtes Mininet ne sont isolés qu'au niveau réseau) — un
        # chemin partagé comme /tmp/out.pdf provoquerait des collisions
        # d'écriture entre clients concurrents.
        output_path = f"/tmp/mc_{session_id}_{client_id}.pdf"

        # curl accepte ici "10" plutôt que "10.0", tout en conservant
        # deadline_seconds comme valeur float dans le contrat.
        timeout = f"{self.deadline_seconds:g}"

        # On demande à curl :
        #   HTTP status
        #   temps total
        #   taille réellement téléchargée
        cmd = (
            f"rm -f {output_path} && "
            "curl -s "
            f"--max-time {timeout} "
            f"-o {output_path} "
            "-w '%{http_code} %{time_total} %{size_download}' "
            f"'http://{server.IP()}:8000/pdf/{encode_path_component(resource_name)}'"
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
            # Best-effort : évite d'accumuler des fichiers dans /tmp au
            # fil d'une grosse campagne de génération.
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

        # ----------------------------------------------------------------
        # Aucun résultat curl
        # ----------------------------------------------------------------

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
                "error": "curl produced no output",
            }

        parts = raw.split()

        # ----------------------------------------------------------------
        # Parsing
        # ----------------------------------------------------------------

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

        # ----------------------------------------------------------------
        # Vérification de la taille réelle du fichier
        # ----------------------------------------------------------------

        output = Path(output_path)
        actual_size_bytes = output.stat().st_size if output.exists() else 0

        # On prend la taille du fichier réellement écrit comme référence
        # principale. %{size_download} sert de mesure complémentaire.
        transfer_completed = (
            http_status == 200
            and actual_size_bytes == resource_size_bytes
            and curl_downloaded_bytes == resource_size_bytes
        )

        within_deadline = download_time < self.deadline_seconds

        return {
            "download_time": download_time,
            "http_status": http_status,
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

    # ------------------------------------------------------------------
    # Oracle applicatif
    # ------------------------------------------------------------------

    def is_successful(self, metrics: dict) -> bool:
        if metrics.get("http_status") != 200:
            return False

        if not metrics.get("transfer_completed", False):
            return False

        if metrics.get("timed_out", False):
            return False

        return metrics.get("download_time", float("inf")) < self.deadline_seconds