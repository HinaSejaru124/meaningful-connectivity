import argparse
import random
import sys
from pathlib import Path

from simulation.network.topology import TopologyBuilder
from simulation.session_generator import SessionGenerator

from simulation.scenarios.pdf import PDFScenario
from simulation.scenarios.quiz import QuizScenario
from simulation.scenarios.video_streaming import VideoStreamingScenario
from simulation.scenarios.webpage import WebPageScenario
from simulation.scenarios.upload import UploadScenario
from simulation.scenarios.quiz_interactive import InteractiveQuizScenario
from simulation.scenarios.chatbot import ChatbotScenario
from simulation.scenarios.ai_agent import AgentScenario


# ============================================================================
# CONFIGURATION DE LA GÉNÉRATION
# ============================================================================

SCENARIOS = {
    "pdf": PDFScenario,
    "quiz": QuizScenario,
    "video_streaming": VideoStreamingScenario,
    "webpage": WebPageScenario,
    "upload": UploadScenario,
    "quiz_interactive": InteractiveQuizScenario,
    "chatbot": ChatbotScenario,
    "ai_agent": AgentScenario,
}


def generate_network_parameters(
    rng: random.Random,
    scenario_name: str,
) -> dict:
    """
    Génère les paramètres réseau d'une session.

    La distribution dépend du scénario afin d'éviter
    une surreprésentation artificielle des cas évidemment
    non-meaningful.

    Les paramètres restent des features connues avant session.
    """

    if scenario_name == "pdf":

        zone = rng.random()

        if zone < 0.60:
            # Zone principale :
            # réseaux suffisamment variés pour explorer
            # la frontière meaningful / non-meaningful.
            bandwidth = rng.uniform(2.0, 20.0)
            latency = rng.uniform(10.0, 250.0)
            jitter = rng.uniform(0.0, 80.0)
            packet_loss = rng.uniform(0.0, 10.0)

        elif zone < 0.80:
            # Très bonnes conditions.
            bandwidth = rng.uniform(10.0, 20.0)
            latency = rng.uniform(10.0, 80.0)
            jitter = rng.uniform(0.0, 30.0)
            packet_loss = rng.uniform(0.0, 3.0)

        else:
            # Mauvaises conditions, mais pas systématiquement
            # catastrophiques.
            bandwidth = rng.uniform(0.5, 8.0)
            latency = rng.uniform(150.0, 350.0)
            jitter = rng.uniform(30.0, 100.0)
            packet_loss = rng.uniform(5.0, 15.0)

    else:
        # Distribution actuelle pour Quiz / Video.
        bandwidth = rng.uniform(0.5, 20.0)
        latency = rng.uniform(10.0, 400.0)
        jitter = rng.uniform(0.0, 150.0)
        packet_loss = rng.uniform(0.0, 15.0)

    return {
        "bandwidth": round(bandwidth, 3),
        "latency": round(latency, 3),
        "jitter": round(jitter, 3),
        "packet_loss": round(packet_loss, 3),
    }


def generate_concurrent_users(
    rng: random.Random,
    total_clients: int,
) -> int:
    """
    Nombre de clients actifs pour la session.
    """

    return rng.randint(
        1,
        total_clients,
    )


def build_scenario_list(
    scenario_name: str | None,
    sessions_per_scenario: int,
) -> list:
    """
    Construit la liste ordonnée des scénarios à exécuter.

    Si aucun scénario n'est spécifié, tous les scénarios sont générés.
    """

    if scenario_name is not None:
        if scenario_name not in SCENARIOS:
            raise ValueError(
                f"Scénario inconnu : {scenario_name}. "
                f"Choix disponibles : {', '.join(SCENARIOS)}"
            )

        return [
            SCENARIOS[scenario_name]()
            for _ in range(sessions_per_scenario)
        ]

    scenarios = []

    for scenario_class in SCENARIOS.values():
        for _ in range(sessions_per_scenario):
            scenarios.append(
                scenario_class()
            )

    return scenarios


# ============================================================================
# GÉNÉRATION
# ============================================================================

def generate_dataset(
    sessions_per_scenario: int,
    scenario_name: str | None,
    seed: int | None,
    total_clients: int,
    dataset_dir: str,
    append: bool,
) -> None:

    rng = random.Random(seed)

    if seed is not None:
        print(f"Seed utilisée : {seed}")

    print()
    print("=" * 70)
    print("GÉNÉRATION DU DATASET")
    print("=" * 70)
    print()

    # ------------------------------------------------------------------------
    # 0. GARDE-FOU APPEND vs NOUVEAU DATASET
    # ------------------------------------------------------------------------

    dataset_csv = Path(dataset_dir) / "dataset.csv"

    if dataset_csv.exists() and not append:
        print(
            f"✗ {dataset_csv} existe déjà.\n"
            f"  Utilise --append pour continuer à écrire dedans, ou "
            f"choisis un --dataset-dir différent pour repartir d'un "
            f"dataset propre (évite de mélanger silencieusement "
            f"d'anciennes campagnes avec la nouvelle)."
        )
        sys.exit(1)

    if dataset_csv.exists() and append:
        print(f"↻ Ajout à un dataset existant : {dataset_csv}")
        print()

    # ------------------------------------------------------------------------
    # 1. TOPOLOGIE UNIQUE
    # ------------------------------------------------------------------------

    print("[1/4] Construction de la topologie...")

    topology_builder = TopologyBuilder(
        total_clients=total_clients
    )

    topology = topology_builder.build()

    print(
        f"✓ Topologie construite : "
        f"h_srv + {total_clients} clients"
    )

    print()

    # ------------------------------------------------------------------------
    # 2. SESSION GENERATOR
    # ------------------------------------------------------------------------

    generator = SessionGenerator(
        topology=topology,
        dataset_dir=dataset_dir,
        rng=rng,
    )

    # ------------------------------------------------------------------------
    # 3. CONSTRUCTION DE LA LISTE DES SESSIONS
    # ------------------------------------------------------------------------

    scenarios = build_scenario_list(
        scenario_name=scenario_name,
        sessions_per_scenario=sessions_per_scenario,
    )

    print(
        f"[2/4] Sessions prévues : {len(scenarios)}"
    )

    if scenario_name:
        print(
            f"      Scénario : {scenario_name}"
        )
    else:
        print(
            "      Scénarios : "
            + ", ".join(SCENARIOS.keys())
        )

    print()

    # ------------------------------------------------------------------------
    # 4. GÉNÉRATION
    # ------------------------------------------------------------------------
    #
    # Les sessions restent générées l'une après l'autre : c'est la
    # concurrence DES UTILISATEURS AU SEIN d'une session qui est
    # parallélisée (voir ApplicationRunner), pas les sessions entre
    # elles. Paralléliser les sessions casserait le partage de
    # topologie/link et la reproductibilité de l'ordre des tirages RNG.
    # ------------------------------------------------------------------------

    print("[3/4] Génération des sessions...")
    print()

    successful_sessions = 0
    failed_sessions = 0
    total_observations = 0
    total_meaningful = 0

    for index, scenario in enumerate(
        scenarios,
        start=1,
    ):

        scenario_name_current = scenario.name

        params = generate_network_parameters(rng, scenario_name_current)

        concurrent_users = generate_concurrent_users(
            rng,
            total_clients,
        )

        print("-" * 70)
        print(
            f"SESSION {index}/{len(scenarios)}"
        )
        print(
            f"Scénario : {scenario_name_current}"
        )
        print(
            f"BW={params['bandwidth']} Mbit/s | "
            f"latence={params['latency']} ms | "
            f"jitter={params['jitter']} ms | "
            f"perte={params['packet_loss']}%"
        )
        print(
            f"Clients actifs : {concurrent_users}"
        )

        try:

            result = generator.generate_session(
                scenario=scenario,
                bandwidth=params["bandwidth"],
                latency=params["latency"],
                jitter=params["jitter"],
                packet_loss=params["packet_loss"],
                concurrent_users=concurrent_users,
            )

            successful_sessions += 1
            total_observations += result["total_observations"]
            total_meaningful += result["meaningful_count"]

            print()
            print(
                f"✓ Session : {result['session_id']}"
            )

            print(
                f"  Ressource : "
                f"{result.get('resource_name', 'unknown')}"
            )

            print(
                f"  Taille : "
                f"{(result.get('resource_size_mb') or 0.0):.3f} Mo"
            )

            print(
                f"  Observations : "
                f"{result['total_observations']} "
                f"({result['meaningful_count']} meaningful)"
            )

            print(
                f"  Logs : "
                f"{result['logs_dir']}"
            )

        except Exception as exc:

            failed_sessions += 1

            print()
            print(
                f"✗ ÉCHEC SESSION {index}"
            )
            print(
                f"  Scénario : {scenario_name_current}"
            )
            print(
                f"  Erreur : {exc}"
            )

            # On continue volontairement avec la session suivante.
            # Une session défaillante ne doit pas tuer toute la génération.
            continue

    # ------------------------------------------------------------------------
    # FIN
    # ------------------------------------------------------------------------

    print()
    print("=" * 70)
    print("GÉNÉRATION TERMINÉE")
    print("=" * 70)

    print(
        f"Sessions réussies     : {successful_sessions}"
    )

    print(
        f"Sessions échouées     : {failed_sessions}"
    )

    print(
        f"Observations écrites  : {total_observations} "
        f"({total_meaningful} meaningful)"
    )

    print(
        f"Groupes indépendants  : {successful_sessions} "
        f"(un split train/test doit être groupé par session_id, "
        f"pas par ligne)"
    )

    print(
        f"Dataset : "
        f"{dataset_csv}"
    )

    print()

    if failed_sessions == 0:
        print("✓ Toutes les sessions ont été générées.")
    else:
        print(
            "⚠ Certaines sessions ont échoué. "
            "Le dataset contient uniquement les sessions réussies."
        )

    # ------------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------------

    print()
    print("[4/4] Arrêt de la topologie...")

    try:
        topology["net"].stop()
        print("✓ Topologie arrêtée.")
    except Exception as exc:
        print(
            f"⚠ Erreur lors de l'arrêt : {exc}"
        )


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Génère automatiquement le dataset "
            "Meaningful Connectivity."
        )
    )

    parser.add_argument(
        "-n",
        "--sessions",
        type=int,
        default=100,
        help=(
            "Nombre de sessions PAR scénario "
            "(défaut : 100). Une session produit plusieurs "
            "observations (une par utilisateur concurrent actif)."
        ),
    )

    parser.add_argument(
        "-s",
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default=None,
        help=(
            "Générer uniquement ce scénario. "
            "Par défaut : tous les scénarios."
        ),
    )

    parser.add_argument(
        "--clients",
        type=int,
        default=10,
        help=(
            "Nombre de clients Mininet "
            "(défaut : 10)"
        ),
    )

    parser.add_argument(
        "--dataset-dir",
        default="dataset",
        help=(
            "Répertoire du dataset "
            "(défaut : dataset)"
        ),
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Seed pour rendre la génération reproductible."
        ),
    )

    parser.add_argument(
        "--append",
        action="store_true",
        help=(
            "Autorise l'ajout à un dataset.csv existant dans "
            "--dataset-dir. Sans ce flag, la génération s'arrête si "
            "un dataset.csv existe déjà, pour éviter de mélanger "
            "silencieusement d'anciennes campagnes."
        ),
    )

    args = parser.parse_args()

    if args.sessions <= 0:
        parser.error(
            "--sessions doit être strictement positif."
        )

    if args.clients <= 0:
        parser.error(
            "--clients doit être strictement positif."
        )

    generate_dataset(
        sessions_per_scenario=args.sessions,
        scenario_name=args.scenario,
        seed=args.seed,
        total_clients=args.clients,
        dataset_dir=args.dataset_dir,
        append=args.append,
    )


if __name__ == "__main__":
    main()