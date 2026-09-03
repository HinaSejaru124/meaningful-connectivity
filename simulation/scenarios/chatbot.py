"""
scenarios/chatbot.py

Scénario de conversation avec un assistant/chatbot éducatif. Diffère
de quiz_interactive.py par un point structurel : l'ASYMÉTRIE des
payloads. Un quiz échange des questions de taille homogène ;
ici, chaque tour envoie un petit message utilisateur (POST, taille
fixe et minime) et reçoit une réponse de taille VARIABLE selon le
"tour" de la conversation -- plus proche d'un vrai échange
conversationnel qu'une série de téléchargements identiques.

Mécanique serveur : voir network/topology.py::do_POST -- consomme le
corps de la requête entrante puis sert le fichier statique
correspondant à l'URL comme réponse (réutilise do_GET), permettant une
réponse plus grosse que la requête sans framework applicatif complexe.

Comme video_streaming/webpage/quiz_interactive, tous les tours d'une
conversation sont enchaînés en un seul curl via --next (connexion
réutilisée), écrit dans un script shell temporaire pour éviter la
limite de longueur de ligne du pty Mininet.
"""

from pathlib import Path

from .base import Scenario
from simulation.utils.net_utils import encode_path_component, shell_quote


class ChatbotScenario(Scenario):
    """
    Simule une conversation à plusieurs tours avec un assistant
    éducatif : chaque tour envoie un petit message et reçoit une
    réponse de taille variable, via une connexion HTTP réutilisée.
    """

    name = "chatbot"
    interaction_level = 1        # interactif, comme quiz_interactive -- mais payloads asymétriques
    deadline_seconds = None       # pas de deadline globale : le critère est le taux de tours en retard

    CHATBOT_DIR = Path(__file__).parent.parent / "htdocs" / "chatbot_api"

    # Petit message utilisateur générique envoyé à chaque tour --
    # taille fixe et minime, volontairement statique en V1 (le
    # contenu réel du message n'a pas d'effet sur le réseau mesuré,
    # seule sa taille compte).
    USER_MESSAGE = '{"role":"user","content":"Peux-tu m\'expliquer ce point plus en detail ?"}'

    PER_TURN_DEADLINE_S = 1.5        # un peu plus généreux que quiz_interactive : réponses potentiellement plus grosses
    MAX_LATE_RATIO = 0.10
    CURL_TIMEOUT_PER_TURN = 15
    MAX_TURNS = 20

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    # ------------------------------------------------------------------
    # Découverte : chaque sous-dossier de CHATBOT_DIR est une
    # "conversation" (séquence ordonnée de réponses pré-générées,
    # turn1.json, turn2.json, ...).
    # ------------------------------------------------------------------

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.CHATBOT_DIR.exists():
            raise RuntimeError(f"Répertoire chatbot_api introuvable : {self.CHATBOT_DIR}")

        conversations = []

        conv_dirs = sorted(
            (p for p in self.CHATBOT_DIR.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )

        for conv_dir in conv_dirs:
            turns = sorted(
                (f for f in conv_dir.glob("*.json") if f.is_file()),
                key=lambda f: f.name,
            )[: self.MAX_TURNS]

            if not turns:
                continue

            rel_names = [f.name for f in turns]
            sizes = [f.stat().st_size for f in turns]
            total_bytes = sum(sizes)

            conversations.append({
                "name": conv_dir.name,
                "turns": rel_names,
                "turn_sizes_bytes": sizes,
                "size_bytes": total_bytes,
                "size_mb": round(total_bytes / (1024 * 1024), 3),
            })

        if not conversations:
            raise RuntimeError(
                f"Aucune conversation trouvée dans {self.CHATBOT_DIR} "
                "(chaque sous-dossier doit contenir au moins un .json)"
            )

        self._resources_cache = conversations
        return conversations

    # ------------------------------------------------------------------
    # Construction de la commande curl chaînée (POST à chaque tour)
    # ------------------------------------------------------------------

    def _build_curl_command(self, url_base: str, turns: list[str]) -> str:
        blocks = []

        for i, filename in enumerate(turns):
            if i > 0:
                blocks.append("--next")

            blocks.append(
                f"--max-time {self.CURL_TIMEOUT_PER_TURN} "
                "-X POST "
                f"-d {shell_quote(self.USER_MESSAGE)} "
                "-o /dev/null "
                "-w 'TURN %{http_code} %{time_total}\\n' "
                f"'{url_base}/{encode_path_component(filename)}'"
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

        conv_name = resource["name"]
        turns = resource["turns"]
        resource_size_mb = resource["size_mb"]

        url_base = f"http://{server.IP()}:8000/chatbot_api/{encode_path_component(conv_name)}"
        curl_cmd = self._build_curl_command(url_base, turns)

        script_path = f"/tmp/mc_{session_id}_{client_id}_chatbot.sh"

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

        turn_lines = [line for line in raw.splitlines() if line.startswith("TURN ")]

        turn_times = []
        late_events = 0

        for line in turn_lines:
            parts = line.split()

            if len(parts) != 3:
                late_events += 1
                turn_times.append(float("inf"))
                continue

            try:
                http_status = int(parts[1])
                t_time = float(parts[2])
            except ValueError:
                late_events += 1
                turn_times.append(float("inf"))
                continue

            if http_status != 200 or t_time > self.PER_TURN_DEADLINE_S:
                late_events += 1

            turn_times.append(t_time)

        missing = len(turns) - len(turn_lines)

        if missing < 0:
            # Plus de lignes "TURN " en sortie que de tours attendus :
            # signe d'une commande shell mal formée (ex. un payload
            # -d mal échappé qui casse le découpage --next), pas
            # d'un simple tour perdu. On le distingue explicitement
            # plutôt que de laisser un compte négatif silencieux.
            late_events += len(turn_lines)
            missing = 0
            anomaly = f"{len(turn_lines)} ligne(s) de sortie inattendue(s) (commande shell probablement mal formée)"
        else:
            late_events += missing
            turn_times.extend([float("inf")] * missing)
            anomaly = None if missing == 0 else f"{missing} tour(s) manquant(s) en sortie"

        attempted = len(turns)
        late_ratio = late_events / attempted if attempted else 1.0

        return {
            "late_ratio": late_ratio,
            "turn_times": turn_times,
            "n_turns": attempted,
            "duration_s": sum(t for t in turn_times if t != float("inf")),
            "resource": conv_name,
            "resource_size_mb": resource_size_mb,
            "error": anomaly,
        }

    # ------------------------------------------------------------------
    # Oracle applicatif
    # ------------------------------------------------------------------

    def is_successful(self, metrics: dict) -> bool:
        late_ratio = metrics.get("late_ratio", 1.0)
        n_turns = metrics.get("n_turns", 0)

        # Même garde-fou de granularité que quiz_interactive : évite
        # qu'un seuil devienne mathématiquement inatteignable avec
        # peu de tours.
        if n_turns > 0:
            effective_threshold = max(self.MAX_LATE_RATIO, 1.0 / n_turns)
        else:
            effective_threshold = self.MAX_LATE_RATIO

        return late_ratio <= effective_threshold