#!/usr/bin/env python3
"""Valide VideoStreamingScenario de bout en bout, en isolant l'effet réseau.

Comme pour test_quiz_scenario.py, un seul fichier est fixé pour toutes les
sessions de ce test, afin de n'isoler qu'une variable : les conditions
réseau. La différence avec PDF/Quiz : le critère de succès n'est pas un
temps total contre une deadline, mais un taux de rebuffering (proportion
de segments arrivés trop tard pour une lecture continue) contre
MAX_REBUFFER_RATIO — donc les tests vérifient ce taux, pas un simple
download_time.

Réutilise la même topologie Mininet pour tout le run (construite une
seule fois).
"""

import sys

from simulation.network.topology import TopologyBuilder
from simulation.scenarios.video_streaming import VideoStreamingScenario
from simulation.session_generator import SessionGenerator


class FixedVideoStreamingScenario(VideoStreamingScenario):
    """
    Variante de test : sert toujours le même fichier vidéo, pour isoler
    l'effet des conditions réseau. Ne redéfinit que la découverte des
    fichiers — is_successful(), SEGMENT_DURATION_S et MAX_REBUFFER_RATIO
    restent exactement ceux de VideoStreamingScenario.
    """

    def __init__(self, fixed_filename: str):
        self._fixed_filename = fixed_filename

    def _discover_files(self) -> list[dict]:
        path = self.VIDEO_DIR / self._fixed_filename
        if not path.exists():
            raise RuntimeError(
                f"Fichier vidéo fixe introuvable : {path} — "
                f"vérifie FIXED_VIDEO_FILE en tête de ce script."
            )
        return [{
            "name": path.name,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 3),
        }]


# À ajuster : nom du fichier existant sous htdocs/video/ à utiliser pour
# isoler ce test (contenu arbitraire, cf. discussion : un .bin quelconque
# suffit, seul le comportement des Range requests compte).
FIXED_VIDEO_FILE = "sample_stream.bin"


def run_video_session(topology: dict, bandwidth, latency, jitter, packet_loss, concurrent_users=2) -> dict:
    scenario = FixedVideoStreamingScenario(FIXED_VIDEO_FILE)
    generator = SessionGenerator(topology, dataset_dir="dataset")
    return generator.generate_session(
        scenario=scenario,
        bandwidth=bandwidth,
        latency=latency,
        jitter=jitter,
        packet_loss=packet_loss,
        concurrent_users=concurrent_users,
    )


def test_video_good_network(topology: dict) -> bool:
    print("\n" + "=" * 70)
    print("TEST 1 : Streaming sous BON réseau -> attendu meaningful=1, rebuffer_ratio bas")
    print("=" * 70)
    print("  Paramètres: BW=20 Mbit/s, Latence=10ms, Jitter=1ms, Perte=0%")

    result = run_video_session(
        topology, bandwidth=20.0, latency=10.0, jitter=1.0, packet_loss=0.0,
    )
    print(f"  Fichier utilisé : {FIXED_VIDEO_FILE}")
    print(f"  Résultat oracle : meaningful={result['meaningful']}")
    print(f"  Ligne dataset   : {result['row']}")

    if result["meaningful"] != 1:
        print("  ✗ Attendu meaningful=1 sous bon réseau.")
        return False
    print("  ✓ OK")
    return True


def test_video_bad_network(topology: dict) -> bool:
    print("\n" + "=" * 70)
    print("TEST 2 : Streaming sous MAUVAIS réseau -> attendu meaningful=0, rebuffer_ratio élevé")
    print("=" * 70)
    print("  Paramètres: BW=0.3 Mbit/s, Latence=400ms, Jitter=80ms, Perte=15%")

    result = run_video_session(
        topology, bandwidth=0.3, latency=400.0, jitter=80.0, packet_loss=15.0,
    )
    print(f"  Fichier utilisé : {FIXED_VIDEO_FILE}")
    print(f"  Résultat oracle : meaningful={result['meaningful']}")
    print(f"  Ligne dataset   : {result['row']}")

    if result["meaningful"] != 0:
        print("  ✗ Attendu meaningful=0 sous mauvais réseau — MAX_REBUFFER_RATIO "
              "est peut-être trop permissif, ou SEGMENT_DURATION_S trop généreux "
              "pour la taille des segments réellement téléchargés (100 Ko/segment).")
        return False
    print("  ✓ OK")
    return True


def test_video_jitter_sensitivity(topology: dict) -> bool:
    """
    Spécifique au streaming (contrairement à PDF/Quiz) : vérifie que le
    JITTER seul, à bande passante et latence moyenne fixes, peut faire
    basculer le label. C'est la propriété centrale qui justifie l'existence
    de ce scénario plutôt que de réutiliser PDFScenario avec un plus gros
    fichier (cf. discussion : jitter critique pour flux temps réel, marginal
    pour transfert statique).
    """
    print("\n" + "=" * 70)
    print("TEST 3 : Sensibilité au jitter (BW et latence moyenne fixes)")
    print("=" * 70)
    print("  Réseau fixe: BW=2.0 Mbit/s, Latence=80ms, Perte=1% — jitter variable")

    jitters = [1, 10, 30, 60, 100, 150]
    ratios = []
    for jit in jitters:
        result = run_video_session(
            topology, bandwidth=2.0, latency=80.0, jitter=float(jit), packet_loss=1.0,
        )
        ratios.append(result["meaningful"])
        print(f"  jitter={jit:>4}ms -> meaningful={result['meaningful']}")

    if len(set(ratios)) < 2:
        print(f"\n  ✗ Aucune sensibilité au jitter observée sur cette plage — "
              f"tous les labels valent {ratios[0]}. Soit la plage est trop "
              f"étroite, soit SEGMENT_DURATION_S/MAX_REBUFFER_RATIO ne "
              f"capturent pas l'effet du jitter comme attendu.")
        return False

    print(f"\n  ✓ Le jitter influence bien le label ({ratios}) à BW/latence fixes — "
          f"confirme que ce scénario capture un phénomène distinct de PDF/Quiz.")
    return True


if __name__ == "__main__":
    builder = TopologyBuilder(total_clients=3)
    topology = builder.build()
    print(f"✓ Topologie construite une seule fois pour l'ensemble du run: "
          f"{topology['server'].name} + {len(topology['clients'])} clients")

    try:
        results = {
            "Streaming meaningful=1 sous bon réseau": test_video_good_network(topology),
            "Streaming meaningful=0 sous mauvais réseau": test_video_bad_network(topology),
            "Sensibilité au jitter confirmée": test_video_jitter_sensitivity(topology),
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
