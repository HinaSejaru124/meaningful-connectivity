"""
scenarios/video_streaming.py

Scénario de streaming vidéo (lecture progressive). Contrairement à
PDFScenario/QuizScenario (téléchargement complet, un seul curl), ce
scénario simule un lecteur qui consomme le contenu par segments
successifs — la métrique pertinente n'est plus le temps total de
téléchargement, mais le taux de segments arrivés trop tard pour une
lecture continue (rebuffering).

Reste dans le downlink pur (le client ne fait que recevoir), donc
compatible avec LinkConfigurator tel quel — pas de gestion d'uplink.
Streaming/upload bidirectionnel réservés à une V2 explicite.

Dimensionnement des segments
-----------------------------
La taille de chaque segment est dérivée d'un débit cible EXPLICITE
(TARGET_BITRATE_MBIT_S), pas d'une simple division du fichier en un
nombre fixe de segments égaux — ça évite d'exiger implicitement un
débit accidentellement trop élevé (voir historique : un fichier de
~5 Mo divisé en 5 segments de 2s exigeait ~4.4 Mbit/s par client,
déjà en haut de la plage réseau configurée).

Connexion réutilisée entre segments
-------------------------------------
Tous les segments d'un même client sont récupérés en UN SEUL appel
curl (requêtes chaînées via --next), pas un curl par segment. Un
curl par segment ouvre une connexion TCP neuve à chaque fois :
handshake complet + slow-start TCP reparti de zéro, à chaque segment.
Sous jitter/packet_loss non négligeables, cette pénalité par
connexion domine largement le temps de transfert réel des ~250 Ko du
segment lui-même — un client pouvait mesurer 5-8s pour un segment
cible à ~1s, alors même que le bandwidth configuré était généreux et
sans aucune concurrence. Un lecteur vidéo réel réutilise sa connexion
HTTP pour les segments successifs ; on fait pareil ici.

La commande curl --next est écrite dans un script shell temporaire
via écriture directe sur le filesystem partagé (comme
network/topology.py pour le serveur HTTP), plutôt que passée telle
quelle à server.cmd()/client_host.cmd() : au-delà d'une trentaine de
segments chaînés, la commande peut approcher la limite de ligne
canonique du pty Mininet (~4096 octets), qui tronque silencieusement
une commande trop longue.
"""

from pathlib import Path

from .base import Scenario
from simulation.utils.net_utils import encode_path_component


class VideoStreamingScenario(Scenario):
    """
    Simule la lecture progressive d'une vidéo : le fichier est découpé
    en segments dont la taille correspond à TARGET_BITRATE_MBIT_S
    soutenus pendant SEGMENT_DURATION_S, récupérés via une connexion
    HTTP réutilisée entre segments. Un segment qui arrive plus
    lentement que ce débit de lecture nominal compte comme un
    événement de rebuffering.
    """

    name = "video_streaming"
    interaction_level = 2        # au-dessus de quiz : flux continu, tolère un peu de latence ponctuelle mais pas l'interruption
    deadline_seconds = None       # pas de seuil temps-total : le critère est le taux de rebuffering, pas une deadline unique

    VIDEO_DIR = Path(__file__).parent.parent / "htdocs" / "video"

    # Débit nominal représenté par la ressource. Abaissé de 2.0 à 1.0
    # Mbit/s ("basse qualité mobile" plutôt que "SD") suite à l'audit
    # empirique du 14 août 2026 : à 2.0 Mbit/s/client, la demande
    # agrégée sous forte concurrence (8-10 utilisateurs) dépassait
    # quasi systématiquement les tirages de bandwidth de la plage
    # configurée, indépendamment du seuil de rebuffering — quasiment
    # aucune session ne pouvait réussir, même avec un seuil très
    # permissif (0/126 à 5/126 selon les réglages testés). Un débit
    # cible plus bas laisse une marge réaliste sous concurrence.
    TARGET_BITRATE_MBIT_S = 1.0

    # Durée de lecture nominale représentée par un segment. Portée de
    # 1.0 à 2.0s (même audit) : à 1s, la moindre fluctuation de débit
    # (variance TCP normale sous latence/jitter réels, pas juste sous
    # contention) faisait basculer un segment en retard — un budget
    # d'1s ne laisse aucune marge d'amortissement.
    SEGMENT_DURATION_S = 2.0

    # Seuil assoupli de 0.05 à 0.10 (même audit) : avec ~21 segments
    # par ressource, 0.05 exige au maximum 1 segment en retard sur 21
    # (paliers de 1/21≈4.8%) — quasiment aucune marge sur une longue
    # séquence, même sous bon réseau. Un service de streaming réel
    # tolère généralement davantage avant de juger l'expérience
    # mauvaise ; 0.10 reste un seuil raisonnablement strict.
    MAX_REBUFFER_RATIO = 0.10
    CURL_TIMEOUT = 15               # garde-fou dur PAR SEGMENT, largement au-dessus de SEGMENT_DURATION_S : protège contre une requête réellement bloquée, pas le critère de rebuffering lui-même
    MAX_SEGMENTS = 30                # borne le nombre de requêtes chaînées par client sur de gros fichiers

    def __init__(self):
        self._resources_cache: list[dict] | None = None

    def discover_resources(self) -> list[dict]:
        if self._resources_cache is not None:
            return self._resources_cache

        if not self.VIDEO_DIR.exists():
            raise RuntimeError(f"Répertoire vidéo introuvable : {self.VIDEO_DIR}")

        files = []

        for f in sorted(self.VIDEO_DIR.glob("*.bin"), key=lambda p: p.name):
            size_bytes = f.stat().st_size

            files.append({
                "name": f.name,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 3),
            })

        if not files:
            raise RuntimeError(f"Aucun fichier vidéo trouvé dans {self.VIDEO_DIR}")

        self._resources_cache = files
        return files

    def _segment_plan(self, resource_size_bytes: int) -> tuple[int, int]:
        """
        Calcule (segment_bytes, n_segments) à partir du débit cible
        explicite, plutôt que d'une division arbitraire du fichier.
        """

        segment_bytes = max(
            int(self.TARGET_BITRATE_MBIT_S * 1_000_000 / 8 * self.SEGMENT_DURATION_S),
            1,
        )

        n_segments = max(resource_size_bytes // segment_bytes, 1)
        n_segments = min(n_segments, self.MAX_SEGMENTS)

        return segment_bytes, n_segments

    def _ranges(self, resource_size_bytes: int) -> list[tuple[int, int]]:
        segment_bytes, n_segments = self._segment_plan(resource_size_bytes)

        ranges = []
        for seg_index in range(n_segments):
            start = seg_index * segment_bytes
            if start >= resource_size_bytes:
                break
            end = min(start + segment_bytes - 1, resource_size_bytes - 1)
            ranges.append((start, end))

        return ranges

    def _build_curl_command(self, url: str, ranges: list[tuple[int, int]]) -> str:
        """
        Une seule invocation curl, requêtes Range chaînées via --next :
        curl réutilise la connexion TCP entre les requêtes vers le
        même hôte au lieu d'en rouvrir une par segment. -r et
        --max-time sont respécifiés dans CHAQUE bloc : --next remet à
        zéro les options propres à la requête précédente, mieux vaut
        ne pas dépendre d'un comportement de "report" implicite.

        Le marqueur "SEG " en tête de chaque ligne -w permet de
        distinguer la sortie utile du reste (curl ne produit rien
        d'autre en mode -s, mais on reste défensif).
        """

        blocks = []

        for i, (start, end) in enumerate(ranges):
            if i > 0:
                blocks.append("--next")

            blocks.append(
                f"--max-time {self.CURL_TIMEOUT} "
                f"-r {start}-{end} "
                "-o /dev/null "
                "-w 'SEG %{http_code} %{time_total}\\n' "
                f"'{url}'"
            )

        return "curl -s " + " ".join(blocks)

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

        ranges = self._ranges(resource_size_bytes)

        if not ranges:
            return {
                "rebuffer_ratio": 1.0,
                "segment_times": [],
                "n_segments": 0,
                "duration_s": 0.0,
                "resource": resource_name,
                "resource_size_mb": resource_size_mb,
                "error": "resource too small to segment",
            }

        url = f"http://{server.IP()}:8000/video/{encode_path_component(resource_name)}"
        curl_cmd = self._build_curl_command(url, ranges)

        script_path = f"/tmp/mc_{session_id}_{client_id}_video.sh"

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

        seg_lines = [
            line for line in raw.splitlines() if line.startswith("SEG ")
        ]

        segment_times = []
        rebuffer_events = 0

        for line in seg_lines:
            parts = line.split()

            if len(parts) != 3:
                rebuffer_events += 1
                segment_times.append(float("inf"))
                continue

            try:
                http_status = int(parts[1])
                seg_time = float(parts[2])
            except ValueError:
                rebuffer_events += 1
                segment_times.append(float("inf"))
                continue

            if http_status not in (200, 206) or seg_time > self.SEGMENT_DURATION_S:
                rebuffer_events += 1

            segment_times.append(seg_time)

        # Segments manquants dans la sortie (curl interrompu en cours
        # de chaîne, ou script non exécuté correctement) : comptés
        # comme rebuffering plutôt qu'ignorés silencieusement.
        missing = len(ranges) - len(seg_lines)
        rebuffer_events += missing
        segment_times.extend([float("inf")] * missing)

        attempted_segments = len(ranges)
        rebuffer_ratio = rebuffer_events / attempted_segments

        return {
            "rebuffer_ratio": rebuffer_ratio,
            "segment_times": segment_times,
            "n_segments": attempted_segments,
            "duration_s": sum(t for t in segment_times if t != float("inf")),
            "resource": resource_name,
            "resource_size_mb": resource_size_mb,
            "error": None if missing == 0 else f"{missing} segment(s) manquant(s) en sortie",
        }

    def is_successful(self, metrics: dict) -> bool:
        return metrics.get("rebuffer_ratio", 1.0) <= self.MAX_REBUFFER_RATIO