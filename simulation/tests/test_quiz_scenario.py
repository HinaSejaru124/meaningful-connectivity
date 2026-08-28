#!/usr/bin/env python3
"""Valide QuizScenario de bout en bout, en isolant l'effet réseau.

Contrairement à la génération en volume (qui tire un fichier quiz au
hasard parmi ceux disponibles, cf. QuizScenario.run_client_action), ce
test fixe volontairement UN SEUL fichier pour toutes ses sessions, afin
de ne faire varier qu'une chose à la fois : les conditions réseau. Sans
ça, un résultat surprenant serait ambigu — impossible de savoir s'il
vient du réseau ou du fichier tiré (piège déjà rencontré sur PDFScenario).

Réutilise la même topologie Mininet pour tout le run (construite une
seule fois), comme test_link_configurator.py.
"""

import sys
from pathlib import Path

from simulation.network.topology import TopologyBuilder
from simulation.scenarios.quiz import QuizScenario
from simulation.session_generator import SessionGenerator


class FixedQuizScenario(QuizScenario):
    """
    Variante de test : sert toujours le même fichier quiz, pour isoler
    l'effet des conditions réseau. Ne redéfinit que la découverte des
    fichiers — is_successful() et le seuil deadline_seconds restent
    exactement ceux de QuizScenario, on ne teste pas l'oracle lui-même.
    """

    def __init__(self, fixed_filename: str):
        self._fixed_filename = fixed_filename

    def _discover_files(self) -> list[dict]:
        path = self.QUIZ_DIR / self._fixed_filename
        if not path.exists():
            raise RuntimeError(
                f"Fichier quiz fixe introuvable : {path} — "
                f"vérifie FIXED_QUIZ_FILE en tête de ce script."
            )
        return [{
            "name": path.name,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 5),
        }]


# À ajuster : nom du fichier quiz existant sous htdocs/quiz/ à utiliser
# pour isoler ce test. Doit exister avant de lancer le script.
FIXED_QUIZ_FILE = "quiz_small.json"


def run_quiz_session(topology: dict, bandwidth, latency, jitter, packet_loss, concurrent_users=2) -> dict:
    scenario = FixedQuizScenario(FIXED_QUIZ_FILE)
    generator = SessionGenerator(topology, dataset_dir="dataset")
    return generator.generate_session(
        scenario=scenario,
        bandwidth=bandwidth,
        latency=latency,
        jitter=jitter,
        packet_loss=packet_loss,
        concurrent_users=concurrent_users,
    )


def test_quiz_good_network(topology: dict) -> bool:
    print("\n" + "=" * 70)
    print("TEST 1 : Quiz sous BON réseau -> attendu meaningful=1")
    print("=" * 70)
    print("  Paramètres: BW=20 Mbit/s, Latence=10ms, Jitter=1ms, Perte=0%")

    result = run_quiz_session(
        topology, bandwidth=20.0, latency=10.0, jitter=1.0, packet_loss=0.0,
    )
    print(f"  Fichier utilisé : {FIXED_QUIZ_FILE}")
    print(f"  Résultat oracle : meaningful={result['meaningful']}")
    print(f"  Ligne dataset   : {result['row']}")

    if result["meaningful"] != 1:
        print("  ✗ Attendu meaningful=1 sous bon réseau.")
        return False
    print("  ✓ OK")
    return True


def test_quiz_bad_network(topology: dict) -> bool:
    print("\n" + "=" * 70)
    print("TEST 2 : Quiz sous MAUVAIS réseau -> attendu meaningful=0")
    print("=" * 70)
    print("  Paramètres: BW=0.3 Mbit/s, Latence=400ms, Jitter=50ms, Perte=15%")

    result = run_quiz_session(
        topology, bandwidth=0.3, latency=400.0, jitter=50.0, packet_loss=15.0,
    )
    print(f"  Fichier utilisé : {FIXED_QUIZ_FILE}")
    print(f"  Résultat oracle : meaningful={result['meaningful']}")
    print(f"  Ligne dataset   : {result['row']}")

    if result["meaningful"] != 0:
        print("  ✗ Attendu meaningful=0 sous mauvais réseau — le seuil "
              "deadline_seconds est probablement encore trop généreux "
              "pour la taille de ce fichier (cf. discussion sur 0.5s vs 2s).")
        return False
    print("  ✓ OK")
    return True


def test_quiz_frontier_scan(topology: dict) -> bool:
    """
    Balaie une plage de latences intermédiaires pour vérifier qu'une
    frontière meaningful=1 -> 0 existe réellement quelque part, et
    n'est pas juste un artefact des deux extrêmes testés ci-dessus.
    """
    print("\n" + "=" * 70)
    print("TEST 3 : Recherche de la frontière meaningful=1/0 (latence croissante)")
    print("=" * 70)
    print("  Réseau fixe: BW=1.0 Mbit/s, Jitter=5ms, Perte=1% — latence variable")

    latencies = [10, 50, 100, 150, 200, 300, 400]
    labels = []
    for lat in latencies:
        result = run_quiz_session(
            topology, bandwidth=1.0, latency=float(lat), jitter=5.0, packet_loss=1.0,
        )
        labels.append(result["meaningful"])
        print(f"  latence={lat:>4}ms -> meaningful={result['meaningful']} "
              f"(download_time via logs: voir {result['logs_dir']}/curl.log)")

    if len(set(labels)) < 2:
        print(f"\n  ✗ Aucune frontière observée sur cette plage — tous les "
              f"labels valent {labels[0]}. Le seuil deadline_seconds "
              f"({FixedQuizScenario(FIXED_QUIZ_FILE).deadline_seconds}s) "
              f"est probablement mal calibré pour ce fichier, ou la plage "
              f"de latence testée est trop étroite.")
        return False

    print(f"\n  ✓ Frontière trouvée : les labels varient bien ({labels}) "
          f"sur la plage de latence testée.")
    return True


if __name__ == "__main__":
    builder = TopologyBuilder(total_clients=3)
    topology = builder.build()
    print(f"✓ Topologie construite une seule fois pour l'ensemble du run: "
          f"{topology['server'].name} + {len(topology['clients'])} clients")

    try:
        results = {
            "Quiz meaningful=1 sous bon réseau": test_quiz_good_network(topology),
            "Quiz meaningful=0 sous mauvais réseau": test_quiz_bad_network(topology),
            "Frontière meaningful=1/0 existe réellement": test_quiz_frontier_scan(topology),
        }

        print("\n" + "=" * 70)
        print("RÉSUMÉ")
        print("=" * 70)
        for label, passed in results.items():
            print(f"  {'✓' if passed else '✗'} {label}")

        success = all(results.values())
        print("\n✓ Tous les tests sont passés !" if success else "\n✗ Certains tests ont échoué.")
        print("=" * 70)
        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"\n✗ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        print("\n[cleanup] Arrêt de la topologie Mininet...")
        topology["net"].stop()