"""
scenarios/ai_agent.py

Scénario d'agent IA exécutant une tâche (ex. un élève qui utilise un
assistant de code). Mécanisme structurellement différent de TOUS les
autres scénarios du projet :

1. CONCURRENCE INTRA-CLIENT (nouveau) : les autres scénarios
   n'exécutent qu'une action à la fois par client, en séquence
   (parfois chaînée via curl --next pour réutiliser la connexion,
   mais jamais en parallèle). Ici, une "rafale de lecture" lance
   plusieurs curl EN PARALLÈLE pour un même client -- comme un agent
   qui appelle plusieurs outils/lit plusieurs fichiers d'un coup
   avant de continuer. Toute la rafale tient dans UN SEUL appel
   client_host.cmd() (jobs shell en arrière-plan via `&` + `wait`) :
   lancer plusieurs cmd() concurrents depuis plusieurs threads Python
   sur le MÊME hôte Mininet risquerait de corrompre le canal shell
   partagé de cet hôte (pas conçu pour des appels concurrents).

2. DEUX DIRECTIONS DE TRAFIC DANS LA MÊME SESSION (nouveau) : une
   tâche alterne rafales de lecture (downlink) et étapes d'écriture
   (uplink, upload -- réutilise le mécanisme déjà construit pour
   UploadScenario). Aucun autre scénario ne combine les deux sens
   dans une même tâche.

Oracle fondé sur un taux d'ÉTAPES en retard (pas de fichiers
individuels) : une rafale de lecture est en retard si son fichier le
plus lent dépasse le budget de rafale ; une écriture est en retard si
elle dépasse son propre budget. Même garde-fou de granularité que
quiz_interactive/chatbot (tolère toujours au moins 1 étape en retard).
"""

from pathlib import Path

from .base import Scenario
from ..utils.net_utils import encode_path_component, shell_quote


class AgentScenario(Scenario):
    """
    Simule une tâche d'agent IA : alternance de rafales de lecture
    parallèles et d'étapes d'écriture (upload), au sein d'une même
    session.
    """

    name = "ai_agent"
    interaction_level = 3        # au-dessus de chatbot : rafales asynchrones, mélange lecture/écriture
    deadline_seconds = None       # pas de deadline globale : le critère est le taux d'étapes en retard

    REQUIRES_UPLINK_SHAPING = True   # nécessaire pour les étapes d'écriture

    AGENT_DIR = Path(__file__).parent.parent / "htdocs" / "agent_tasks"

    BURST_DEADLINE_S = 2.0    # budget pour la rafale ENTIÈRE (déterminé par son fichier le plus lent)
    WRITE_DEADLINE_S = 5.0     # budget pour une étape d'écriture individuelle
    MAX_LATE_STEP_RATIO = 0.15
    CURL_TIMEOUT = 15
    MAX_STEPS = 15

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    # ------------------------------------------------------------------
    # Découverte : chaque sous-dossier de AGENT_DIR est une "tâche".
    # À l'intérieur, triés par nom :
    #   - un SOUS-DOSSIER = une rafale de lecture (fichiers à
    #     récupérer en parallèle)
    #   - un FICHIER = une étape d'écriture (uploadée telle quelle,
    #     sa taille sur disque détermine directement le volume envoyé)
    # ------------------------------------------------------------------

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.AGENT_DIR.exists():
            raise RuntimeError(f"Répertoire agent_tasks introuvable : {self.AGENT_DIR}")

        tasks = []

        task_dirs = sorted(
            (p for p in self.AGENT_DIR.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )

        for task_dir in task_dirs:
            entries = sorted(task_dir.iterdir(), key=lambda p: p.name)[: self.MAX_STEPS]
            steps = []
            total_bytes = 0

            for entry in entries:
                if entry.is_dir():
                    files = sorted(
                        (f for f in entry.iterdir() if f.is_file()),
                        key=lambda f: f.name,
                    )
                    if not files:
                        continue
                    sizes = [f.stat().st_size for f in files]
                    total_bytes += sum(sizes)
                    steps.append({
                        "type": "burst",
                        "burst_name": entry.name,
                        "files": [f.name for f in files],
                        "sizes_bytes": sizes,
                    })
                elif entry.is_file():
                    size_bytes = entry.stat().st_size
                    total_bytes += size_bytes
                    steps.append({
                        "type": "write",
                        "filename": entry.name,
                        "local_path": str(entry),
                        "size_bytes": size_bytes,
                    })

            if not steps:
                continue

            tasks.append({
                "name": task_dir.name,
                "steps": steps,
                "size_bytes": total_bytes,
                "size_mb": round(total_bytes / (1024 * 1024), 3),
            })

        if not tasks:
            raise RuntimeError(
                f"Aucune tâche trouvée dans {self.AGENT_DIR} "
                "(chaque sous-dossier doit contenir des rafales [sous-dossiers] "
                "et/ou des fichiers d'écriture)"
            )

        self._resources_cache = tasks
        return tasks

    # ------------------------------------------------------------------
    # Construction du script shell : rafales en parallèle (& + wait),
    # écritures en séquence entre les rafales.
    # ------------------------------------------------------------------

    def _build_script(
        self,
        task_name: str,
        steps: list[dict],
        server_ip: str,
        session_id: str,
        client_id: str,
    ) -> tuple[str, str]:

        results_path = f"/tmp/mc_{session_id}_{client_id}_agent_results.txt"
        lines = ["#!/bin/sh", f"rm -f {results_path}"]

        read_base = f"http://{server_ip}:8000/agent_tasks/{encode_path_component(task_name)}"

        for step_index, step in enumerate(steps):
            if step["type"] == "burst":
                burst_base = f"{read_base}/{encode_path_component(step['burst_name'])}"

                for file_index, filename in enumerate(step["files"]):
                    url = f"{burst_base}/{encode_path_component(filename)}"
                    tag = f"S{step_index}F{file_index}"
                    lines.append(
                        f"curl -s --max-time {self.CURL_TIMEOUT} -o /dev/null "
                        f"-w '{tag} %{{http_code}} %{{time_total}}\\n' "
                        f"'{url}' >> {results_path} &"
                    )

                lines.append("wait")

            else:  # write
                tag = f"S{step_index}W"
                remote_name = f"mc_{session_id}_{client_id}_{step['filename']}"
                url = f"http://{server_ip}:8000/agent_upload/{encode_path_component(remote_name)}"

                lines.append(
                    f"curl -s --max-time {self.CURL_TIMEOUT} "
                    f"-T {shell_quote(step['local_path'])} "
                    f"-w '{tag} %{{http_code}} %{{time_total}}\\n' "
                    f"'{url}' >> {results_path}"
                )

        lines.append(f"cat {results_path}")
        lines.append(f"rm -f {results_path}")

        return "\n".join(lines) + "\n", results_path

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

        task_name = resource["name"]
        steps = resource["steps"]
        resource_size_mb = resource["size_mb"]

        script_body, _ = self._build_script(
            task_name, steps, server.IP(), session_id, client_id
        )

        script_path = f"/tmp/mc_{session_id}_{client_id}_agent.sh"

        try:
            with open(script_path, "w") as f:
                f.write(script_body)
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

        # Regroupe les lignes de sortie par étape (Sn) pour déterminer
        # si CHAQUE étape (rafale entière, ou écriture) a respecté son
        # budget -- une rafale est en retard si SON FICHIER LE PLUS
        # LENT dépasse le budget, pas juste la moyenne.
        step_results: dict[int, list[tuple[int, float]]] = {}

        for line in raw.splitlines():
            parts = line.split()

            if len(parts) != 3 or not parts[0].startswith("S"):
                continue

            tag, http_code, time_str = parts

            try:
                step_index = int(tag[1:].split("F")[0].split("W")[0])
                http_status = int(http_code)
                t = float(time_str)
            except (ValueError, IndexError):
                continue

            step_results.setdefault(step_index, []).append((http_status, t))

        late_steps = 0
        step_max_times = []
        missing_steps = 0

        for step_index, step in enumerate(steps):
            observed = step_results.get(step_index, [])
            expected_count = len(step["files"]) if step["type"] == "burst" else 1

            if len(observed) < expected_count:
                missing_steps += 1
                late_steps += 1
                continue

            max_time = max(t for _, t in observed)
            any_bad_status = any(status not in (200, 201) for status, _ in observed)
            budget = self.BURST_DEADLINE_S if step["type"] == "burst" else self.WRITE_DEADLINE_S

            step_max_times.append(max_time)

            if any_bad_status or max_time > budget:
                late_steps += 1

        total_steps = len(steps)
        late_ratio = late_steps / total_steps if total_steps else 1.0

        return {
            "late_ratio": late_ratio,
            "step_max_times": step_max_times,
            "n_steps": total_steps,
            "duration_s": sum(step_max_times),
            "resource": task_name,
            "resource_size_mb": resource_size_mb,
            "error": None if missing_steps == 0 else f"{missing_steps} étape(s) incomplète(s) en sortie",
        }

    # ------------------------------------------------------------------
    # Oracle applicatif
    # ------------------------------------------------------------------

    def is_successful(self, metrics: dict) -> bool:
        late_ratio = metrics.get("late_ratio", 1.0)
        n_steps = metrics.get("n_steps", 0)

        if n_steps > 0:
            effective_threshold = max(self.MAX_LATE_STEP_RATIO, 1.0 / n_steps)
        else:
            effective_threshold = self.MAX_LATE_STEP_RATIO

        return late_ratio <= effective_threshold