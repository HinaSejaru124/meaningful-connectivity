"""
scenarios/upload.py

Scénario de soumission d'un devoir (upload). Direction du transfert
INVERSÉE par rapport à tous les autres scénarios (client → serveur au
lieu de serveur → client) — nécessite un shaping réseau supplémentaire
sur l'égress de chaque client actif (voir REQUIRES_UPLINK_SHAPING et
network/link.py::apply_uplink, où le choix méthodologique — accès
individuel, pas goulot partagé — est documenté en détail).

Réutilise les fichiers PDF existants comme contenu à uploader (pas de
nouveau répertoire de ressources à créer) : le fichier local est
envoyé via curl -T (PUT), le serveur (voir topology.py::do_PUT) lit et
jette le corps de la requête sans le stocker — seul le temps de
transfert nous intéresse ici, pas la persistance du fichier reçu.
"""

from pathlib import Path

from .base import Scenario
from simulation.utils.net_utils import encode_path_component, shell_quote


class UploadScenario(Scenario):
    """
    Simule la soumission d'un devoir : le client envoie un fichier au
    serveur via HTTP PUT. Contrat structurellement identique à
    PDFScenario (transfert complet unique, deadline stricte), mais
    dans le sens inverse.
    """

    name = "upload"
    interaction_level = 0        # soumission ponctuelle, pas d'interactivité continue
    deadline_seconds = 15.0       # plus généreux que PDF : l'upload est souvent plus lent que le download sur une connexion asymétrique

    REQUIRES_UPLINK_SHAPING = True

    # Réutilise les PDF existants comme contenu à soumettre — pas de
    # nouveau dossier de ressources requis.
    UPLOAD_SOURCE_DIR = Path(__file__).parent.parent / "htdocs" / "pdf"

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.UPLOAD_SOURCE_DIR.exists():
            raise RuntimeError(
                f"Répertoire source pour l'upload introuvable : {self.UPLOAD_SOURCE_DIR}"
            )

        files = []

        for f in sorted(self.UPLOAD_SOURCE_DIR.glob("*.pdf"), key=lambda p: p.name):
            size_bytes = f.stat().st_size

            files.append({
                "name": f.name,
                "local_path": str(f),
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 3),
            })

        if not files:
            raise RuntimeError(
                f"Aucun fichier source trouvé dans {self.UPLOAD_SOURCE_DIR}"
            )

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
        local_path = resource["local_path"]
        resource_size_bytes = resource["size_bytes"]
        resource_size_mb = resource["size_mb"]

        # Nom distant unique par (session, client) pour ne pas faire
        # collision si plusieurs clients uploadent "en même temps" (le
        # serveur ne stocke rien, mais autant rester cohérent avec le
        # pattern déjà établi ailleurs dans le projet).
        remote_name = f"mc_{session_id}_{client_id}_{resource_name}"

        timeout = f"{self.deadline_seconds:g}"

        cmd = (
            "curl -s "
            f"--max-time {timeout} "
            f"-T {shell_quote(local_path)} "
            "-w '%{http_code} %{time_total} %{size_upload}' "
            f"'http://{server.IP()}:8000/upload/{encode_path_component(remote_name)}'"
        )

        raw = client_host.cmd(cmd).strip()

        return self._parse_result(raw, resource_name, resource_size_bytes, resource_size_mb)

    def _parse_result(
        self,
        raw: str,
        resource_name: str,
        resource_size_bytes: int,
        resource_size_mb: float,
    ) -> dict:

        if not raw:
            return {
                "upload_time": float(self.deadline_seconds),
                "http_status": 0,
                "uploaded_size_bytes": 0,
                "transfer_completed": False,
                "timed_out": True,
                "within_deadline": False,
                "resource": resource_name,
                "resource_size_mb": resource_size_mb,
                "error": "curl produced no output",
            }

        parts = raw.split()

        if len(parts) != 3:
            return {
                "upload_time": float("inf"),
                "http_status": 0,
                "uploaded_size_bytes": 0,
                "transfer_completed": False,
                "timed_out": False,
                "within_deadline": False,
                "resource": resource_name,
                "resource_size_mb": resource_size_mb,
                "error": raw,
            }

        try:
            http_status = int(parts[0])
            upload_time = float(parts[1])
            uploaded_bytes = int(float(parts[2]))
        except ValueError:
            return {
                "upload_time": float("inf"),
                "http_status": 0,
                "uploaded_size_bytes": 0,
                "transfer_completed": False,
                "timed_out": False,
                "within_deadline": False,
                "resource": resource_name,
                "resource_size_mb": resource_size_mb,
                "error": raw,
            }

        transfer_completed = (
            http_status == 200
            and uploaded_bytes == resource_size_bytes
        )

        within_deadline = upload_time < self.deadline_seconds

        return {
            "upload_time": upload_time,
            "http_status": http_status,
            "uploaded_size_bytes": uploaded_bytes,
            "transfer_completed": transfer_completed,
            "timed_out": upload_time >= self.deadline_seconds,
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

        return metrics.get("upload_time", float("inf")) < self.deadline_seconds