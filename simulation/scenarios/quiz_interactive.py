"""
scenarios/quiz_interactive.py

Scénario de quiz VRAIMENT interactif : contrairement à QuizScenario
(un seul fichier JSON statique récupéré en un coup), ce scénario
simule un échange en plusieurs temps — N questions récupérées
séquentiellement, chacune représentant un aller-retour applicatif
(l'utilisateur reçoit une question, "réfléchit", passe à la
suivante).

Pourquoi c'est un mécanisme réellement différent des scénarios de
téléchargement (PDF/quiz/webpage/audio) :
    - Le critère n'est plus "un gros transfert complet avant une
      deadline", mais "chaque petite transaction individuelle arrive
      assez vite pour ne pas casser le rythme interactif".
    - Les payloads sont minuscules (quelques Ko par question) — donc,
      contrairement à video_streaming, ce scénario ne devrait PAS être
      sujet à l'effondrement de débit TCP sous jitter/latence identifié
      lors de l'enquête vidéo (ce phénomène concernait des flux
      soutenus sur plusieurs secondes, pas des transactions courtes
      isolées — confirmé empiriquement par les tests de segment isolé
      de 250 Ko qui restaient nettement plus rapides qu'un transfert
      complet dans les mêmes conditions).

Simplification V1 : pas de délai de "réflexion" simulé entre les
questions (chaque question est récupérée immédiatement après la
précédente) — ça garde les sessions courtes et le mécanisme simple à
auditer. Un vrai temps de réflexion pourrait être ajouté en V2 sans
changer la logique réseau.
"""

from pathlib import Path

from .base import Scenario
from simulation.utils.net_utils import encode_path_component


class InteractiveQuizScenario(Scenario):
    """
    Simule un quiz interactif à plusieurs questions : chaque question
    est un aller-retour applicatif distinct, récupéré via une
    connexion HTTP réutilisée (même leçon que video_streaming/webpage
    : un seul curl chaîné, pas un curl par question).
    """

    name = "quiz_interactive"
    interaction_level = 1        # interactif, comme le quiz simple — mais mesuré différemment
    deadline_seconds = None       # pas de deadline globale : le critère est le taux de questions en retard

    QUIZ_API_DIR = Path(__file__).parent.parent / "htdocs" / "quiz_api"

    PER_QUESTION_DEADLINE_S = 1.0   # budget par question, cohérent avec la tolérance du quiz simple
    MAX_LATE_RATIO = 0.10            # tolère jusqu'à 10% des questions en retard
    CURL_TIMEOUT_PER_QUESTION = 15
    MAX_QUESTIONS = 20

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    # ------------------------------------------------------------------
    # Découverte : chaque sous-dossier de QUIZ_API_DIR est un "quiz"
    # (ensemble ordonné de questions).
    # ------------------------------------------------------------------

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.QUIZ_API_DIR.exists():
            raise RuntimeError(f"Répertoire quiz_api introuvable : {self.QUIZ_API_DIR}")

        quiz_sets = []

        set_dirs = sorted(
            (p for p in self.QUIZ_API_DIR.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )

        for set_dir in set_dirs:
            questions = sorted(
                (f for f in set_dir.glob("*.json") if f.is_file()),
                key=lambda f: f.name,
            )[: self.MAX_QUESTIONS]

            if not questions:
                continue

            rel_names = [f.name for f in questions]
            sizes = [f.stat().st_size for f in questions]
            total_bytes = sum(sizes)

            quiz_sets.append({
                "name": set_dir.name,
                "questions": rel_names,
                "question_sizes_bytes": sizes,
                "size_bytes": total_bytes,
                "size_mb": round(total_bytes / (1024 * 1024), 3),
            })

        if not quiz_sets:
            raise RuntimeError(
                f"Aucun quiz trouvé dans {self.QUIZ_API_DIR} "
                "(chaque sous-dossier doit contenir au moins un .json)"
            )

        self._resources_cache = quiz_sets
        return quiz_sets

    # ------------------------------------------------------------------
    # Construction de la commande curl chaînée
    # ------------------------------------------------------------------

    def _build_curl_command(self, url_base: str, questions: list[str]) -> str:
        blocks = []

        for i, filename in enumerate(questions):
            if i > 0:
                blocks.append("--next")

            blocks.append(
                f"--max-time {self.CURL_TIMEOUT_PER_QUESTION} "
                "-o /dev/null "
                "-w 'Q %{http_code} %{time_total}\\n' "
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

        quiz_name = resource["name"]
        questions = resource["questions"]
        resource_size_mb = resource["size_mb"]

        url_base = f"http://{server.IP()}:8000/quiz_api/{encode_path_component(quiz_name)}"
        curl_cmd = self._build_curl_command(url_base, questions)

        script_path = f"/tmp/mc_{session_id}_{client_id}_quizapi.sh"

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

        q_lines = [line for line in raw.splitlines() if line.startswith("Q ")]

        question_times = []
        late_events = 0

        for line in q_lines:
            parts = line.split()

            if len(parts) != 3:
                late_events += 1
                question_times.append(float("inf"))
                continue

            try:
                http_status = int(parts[1])
                q_time = float(parts[2])
            except ValueError:
                late_events += 1
                question_times.append(float("inf"))
                continue

            if http_status != 200 or q_time > self.PER_QUESTION_DEADLINE_S:
                late_events += 1

            question_times.append(q_time)

        missing = len(questions) - len(q_lines)
        late_events += missing
        question_times.extend([float("inf")] * missing)

        attempted = len(questions)
        late_ratio = late_events / attempted if attempted else 1.0

        return {
            "late_ratio": late_ratio,
            "question_times": question_times,
            "n_questions": attempted,
            "duration_s": sum(t for t in question_times if t != float("inf")),
            "resource": quiz_name,
            "resource_size_mb": resource_size_mb,
            "error": None if missing == 0 else f"{missing} question(s) manquante(s) en sortie",
        }

    # ------------------------------------------------------------------
    # Oracle applicatif
    # ------------------------------------------------------------------

    def is_successful(self, metrics: dict) -> bool:
        late_ratio = metrics.get("late_ratio", 1.0)
        n_questions = metrics.get("n_questions", 0)

        # Garde-fou de granularité : avec peu de questions, le palier
        # minimal non nul (1/n_questions) peut dépasser
        # MAX_LATE_RATIO, rendant le seuil inatteignable par
        # construction (une seule question en retard fait échouer
        # TOUTE session, indépendamment du réseau — même piège que
        # rencontré sur video_streaming avec un nombre de segments
        # trop faible). On tolère donc explicitement au moins 1
        # question en retard, quel que soit le nombre de questions.
        if n_questions > 0:
            effective_threshold = max(self.MAX_LATE_RATIO, 1.0 / n_questions)
        else:
            effective_threshold = self.MAX_LATE_RATIO

        return late_ratio <= effective_threshold