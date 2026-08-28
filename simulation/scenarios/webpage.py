"""
scenarios/webpage.py

Scénario de consultation d'une page web éducative. Contrairement aux
autres scénarios (un seul objet par ressource), une "page" ici est un
ENSEMBLE de fichiers (HTML + assets : CSS, images...) — plus proche
d'un vrai chargement de page que d'un simple téléchargement de fichier
unique.

Reprend la leçon du scénario vidéo (voir historique) : tous les
objets d'une même page sont récupérés en UN SEUL appel curl (requêtes
chaînées via --next), pas un curl par objet, pour réutiliser la
connexion TCP au lieu de payer un handshake par fichier.

Simplification V1 : les objets sont récupérés SÉQUENTIELLEMENT (comme
un navigateur HTTP/1.1 sans connexions parallèles), pas en parallèle
comme le ferait un navigateur moderne avec plusieurs connexions
simultanées. Le temps mesuré (somme des temps individuels) est donc
une approximation prudente (pire cas) du temps de chargement réel.
"""

from pathlib import Path

from .base import Scenario
from simulation.utils.net_utils import encode_path_component


class WebPageScenario(Scenario):
    """
    Simule le chargement d'une page web éducative : un document HTML
    accompagné de ses ressources associées (CSS, images...), tous
    récupérés via une connexion HTTP réutilisée.
    """

    name = "webpage"
    interaction_level = 0        # passif, comme PDF : consultation, pas d'interactivité utilisateur
    deadline_seconds = 5.0        # référentiel UX courant pour un chargement de page complet

    WEBPAGE_DIR = Path(__file__).parent.parent / "htdocs" / "webpage"
    CURL_TIMEOUT_PER_OBJECT = 15

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    # ------------------------------------------------------------------
    # Découverte des ressources : chaque sous-dossier de WEBPAGE_DIR
    # est une "page" (ensemble de fichiers).
    # ------------------------------------------------------------------

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.WEBPAGE_DIR.exists():
            raise RuntimeError(f"Répertoire webpage introuvable : {self.WEBPAGE_DIR}")

        pages = []

        page_dirs = sorted(
            (p for p in self.WEBPAGE_DIR.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )

        for page_dir in page_dirs:
            files = sorted(
                (f for f in page_dir.rglob("*") if f.is_file()),
                key=lambda f: str(f.relative_to(page_dir)),
            )

            if not files:
                continue

            rel_paths = [str(f.relative_to(page_dir)) for f in files]
            file_sizes = [f.stat().st_size for f in files]
            total_bytes = sum(file_sizes)

            pages.append({
                "name": page_dir.name,
                "files": rel_paths,
                "file_sizes_bytes": file_sizes,
                "size_bytes": total_bytes,
                "size_mb": round(total_bytes / (1024 * 1024), 3),
            })

        if not pages:
            raise RuntimeError(
                f"Aucune page trouvée dans {self.WEBPAGE_DIR} "
                "(chaque sous-dossier doit contenir au moins un fichier)"
            )

        self._resources_cache = pages
        return pages

    # ------------------------------------------------------------------
    # Construction de la commande curl chaînée
    # ------------------------------------------------------------------

    def _build_curl_command(self, url_base: str, files: list[str]) -> str:
        blocks = []

        for i, filename in enumerate(files):
            if i > 0:
                blocks.append("--next")

            # filename peut contenir des "/" (sous-dossiers, via
            # rglob) : on encode chaque segment séparément pour ne
            # pas transformer les "/" structurels en %2F.
            encoded_filename = "/".join(
                encode_path_component(part) for part in filename.split("/")
            )

            blocks.append(
                f"--max-time {self.CURL_TIMEOUT_PER_OBJECT} "
                "-o /dev/null "
                "-w 'OBJ %{http_code} %{time_total} %{size_download}\\n' "
                f"'{url_base}/{encoded_filename}'"
            )

        return "curl -s " + " ".join(blocks)

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

        page_name = resource["name"]
        files = resource["files"]
        expected_sizes = resource["file_sizes_bytes"]
        resource_size_mb = resource["size_mb"]

        url_base = f"http://{server.IP()}:8000/webpage/{encode_path_component(page_name)}"
        curl_cmd = self._build_curl_command(url_base, files)

        script_path = f"/tmp/mc_{session_id}_{client_id}_webpage.sh"

        try:
            with open(script_path, "w") as f:
                f.write("#!/bin/sh\n")
                f.write(curl_cmd + "\n")
        except OSError as exc:
            raise RuntimeError(
                f"Impossible d'écrire {script_path} : {exc}"
            ) from exc

        try:
            raw = client_host.cmd(f"sh {script_path}")
        finally:
            try:
                Path(script_path).unlink(missing_ok=True)
            except OSError:
                pass

        obj_lines = [line for line in raw.splitlines() if line.startswith("OBJ ")]

        total_time = 0.0
        downloaded_total_bytes = 0
        objects_ok = 0
        all_ok = True

        for i, line in enumerate(obj_lines):
            parts = line.split()

            if len(parts) != 4:
                all_ok = False
                continue

            try:
                http_status = int(parts[1])
                obj_time = float(parts[2])
                obj_bytes = int(float(parts[3]))
            except ValueError:
                all_ok = False
                continue

            total_time += obj_time
            downloaded_total_bytes += obj_bytes

            expected = expected_sizes[i] if i < len(expected_sizes) else None

            if http_status != 200 or (expected is not None and obj_bytes != expected):
                all_ok = False
            else:
                objects_ok += 1

        missing = len(files) - len(obj_lines)
        if missing > 0:
            all_ok = False

        within_deadline = total_time < self.deadline_seconds

        return {
            "objects_total": len(files),
            "objects_ok": objects_ok,
            "objects_missing": missing,
            "transfer_completed": all_ok,
            "download_time": total_time,
            "downloaded_size_bytes": downloaded_total_bytes,
            "timed_out": not within_deadline,
            "within_deadline": within_deadline,
            "resource": page_name,
            "resource_size_mb": resource_size_mb,
            "error": None if (all_ok and within_deadline) else (
                "deadline exceeded"
                if not within_deadline
                else "objects incomplete"
            ),
        }

    # ------------------------------------------------------------------
    # Oracle applicatif
    # ------------------------------------------------------------------

    def is_successful(self, metrics: dict) -> bool:
        if not metrics.get("transfer_completed", False):
            return False

        return metrics.get("download_time", float("inf")) < self.deadline_seconds