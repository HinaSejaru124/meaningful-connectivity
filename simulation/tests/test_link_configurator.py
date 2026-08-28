#!/usr/bin/env python3
"""Valide que LinkConfigurator applique réellement les paramètres réseau.

Ce test :
1. Vérifie que le lien serveur<->switch obtient une vraie configuration tc
2. Vérifie que des conditions opposées (bon/mauvais réseau) produisent des
   mesures différentes et, in fine, des labels d'oracle différents
3. Vérifie que les logs par session contiennent de vraies mesures, pas des
   valeurs simulées

Important : une seule topologie Mininet est construite pour l'ensemble du
run et réutilisée par les 3 tests (conformément à la conception retenue :
la topologie est instanciée une seule fois, seuls les paramètres du lien
sont reconfigurés entre deux sessions). La topologie est détruite proprement
à la fin, y compris si un test échoue, pour éviter l'erreur classique
"RTNETLINK answers: File exists" au prochain lancement.
"""

import json
import sys
from pathlib import Path

from simulation.network.topology import TopologyBuilder
from simulation.network.link import LinkConfigurator
from simulation.scenarios.pdf import PDFScenario
from simulation.session_generator import SessionGenerator


def run_scenario_with_conditions(
    topology: dict,
    scenario,
    bandwidth: float,
    latency: float,
    jitter: float,
    packet_loss: float,
    concurrent_users: int = 2,
) -> dict:
    """Exécute une session avec des conditions réseau spécifiques."""
    generator = SessionGenerator(topology, dataset_dir="dataset")
    return generator.generate_session(
        scenario=scenario,
        bandwidth=bandwidth,
        latency=latency,
        jitter=jitter,
        packet_loss=packet_loss,
        concurrent_users=concurrent_users,
    )
    
def test_http_range(topology):
    print("\n" + "=" * 70)
    print("TEST HTTP RANGE")
    print("=" * 70)

    client = topology["clients"][0]
    server = topology["server"]

    url = f"http://{server.IP()}:8000/video/sample_stream.bin"

    print(f"Client : {client.name}")
    print(f"URL    : {url}")
    print("Range  : bytes=0-102399")

    result = client.cmd(
        f"curl -v -r 0-102399 "
        f"-o /tmp/range_test.bin "
        f"-D /tmp/range_headers.txt "
        f"{url} 2>&1"
    )

    print("\n--- CURL ---")
    print(result)

    headers = client.cmd(
        "cat /tmp/range_headers.txt 2>/dev/null"
    )

    print("\n--- HEADERS ---")
    print(headers)

    size = client.cmd(
        "stat -c '%s' /tmp/range_test.bin 2>/dev/null"
    ).strip()

    print("\n--- TAILLE ---")
    print(f"{size} octets")

    print("=" * 70) 


def test_link_configurator(topology: dict) -> bool:
    """Teste que LinkConfigurator applique réellement les paramètres tc."""
    print("\n" + "=" * 70)
    print("TEST 1: Vérification que LinkConfigurator applique les paramètres tc")
    print("=" * 70)

    server = topology["server"]
    print(f"✓ Topologie réutilisée: {server.name} + {len(topology['clients'])} clients")

    print("\n[1.1] Application d'une configuration réseau...")
    test_bandwidth, test_latency, test_jitter, test_loss = 10.0, 50.0, 5.0, 1.0

    configurator = LinkConfigurator(
        bandwidth=test_bandwidth,
        latency=test_latency,
        jitter=test_jitter,
        packet_loss=test_loss,
    )

    try:
        result = configurator.apply(topology)
    except Exception as e:
        print(f"✗ Erreur lors de l'application: {e}")
        return False

    print(f"✓ Configuration appliquée sur l'interface: {result['interface']}")
    print(f"  - Bande passante: {test_bandwidth} Mbit/s")
    print(f"  - Latence: {test_latency} ms")
    print(f"  - Jitter: {test_jitter} ms")
    print(f"  - Perte: {test_loss}%")

    if not result["applied"]:
        print("✗ LinkConfigurator dit avoir appliqué la config, mais la "
              "vérification tc (netem+tbf) ne la retrouve pas sur l'interface.")
        print(f"  Sortie brute de la commande tc: {result['raw_output']!r}")
        return False

    print("\n[1.2] Vérification indépendante via 'tc qdisc show'...")
    tc_output = server.cmd(f"tc qdisc show dev {result['interface']}")
    print(f"  {tc_output.strip()}")
    if "netem" not in tc_output or "tbf" not in tc_output:
        print("✗ La règle netem/tbf n'apparaît pas sur l'interface attendue.")
        return False

    print("✓ Interface confirmée avec une configuration netem + tbf active")
    return True


def test_oracle_with_conditions(topology: dict) -> bool:
    """Teste que l'oracle produit des labels différents selon les conditions réseau."""
    print("\n" + "=" * 70)
    print("TEST 2: Impact des conditions réseau sur les mesures et l'oracle")
    print("=" * 70)

    scenario = PDFScenario()

    print("\n[2.1] Exécution avec de BONNES conditions réseau...")
    print("  Paramètres: BW=20 Mbit/s, Latence=20ms, Jitter=2ms, Perte=0%")
    good_result = run_scenario_with_conditions(
        topology=topology, scenario=scenario,
        bandwidth=20.0, latency=20.0, jitter=2.0, packet_loss=0.0,
        concurrent_users=2,
    )
    good_meaningful = good_result["meaningful"]
    print(f"  Ressource : {good_result['resource_name']}")
    print(f"  Taille    : {good_result['resource_size_mb']:.2f} Mo")

    sample = good_result["row"]
    print(f"  Temps téléchargement : {sample.get('download_time', 'N/A')} s")

    print(f"✓ Résultat oracle (bonnes conditions): meaningful={good_meaningful}")
    print(f"  Ligne dataset: {good_result['row']}")

    print("\n[2.2] Exécution avec de MAUVAISES conditions réseau...")
    print("  Paramètres: BW=0.3 Mbit/s, Latence=400ms, Jitter=50ms, Perte=15%")
    bad_result = run_scenario_with_conditions(
        topology=topology, scenario=scenario,
        bandwidth=0.3, latency=400.0, jitter=50.0, packet_loss=15.0,
        concurrent_users=2,
    )
    bad_meaningful = bad_result["meaningful"]
    print(f"  Ressource : {bad_result['resource_name']}")
    print(f"  Taille    : {bad_result['resource_size_mb']:.2f} Mo")

    sample = bad_result["row"]
    print(f"  Temps téléchargement : {sample.get('download_time', 'N/A')} s")

    print(f"✓ Résultat oracle (mauvaises conditions): meaningful={bad_meaningful}")
    print(f"  Ligne dataset: {bad_result['row']}")

    print("\n[2.3] Analyse des résultats...")
    print(f"  Bonnes conditions: meaningful={good_meaningful}")
    print(f"  Mauvaises conditions: meaningful={bad_meaningful}")

    if good_meaningful == 1 and bad_meaningful == 0:
        print("  ✓ EXCELLENT: l'oracle distingue nettement bon et mauvais réseau")
        return True
    if good_meaningful > bad_meaningful:
        print("  ✓ BON: l'oracle réagit dans le bon sens (bon > mauvais)")
        return True

    print("  ✗ Les conditions réseau n'ont produit aucun effet observable sur "
          "l'oracle — vérifier que tc a un impact réel (cf. TEST 1) avant de "
          "creuser l'oracle lui-même.")
    return False


def test_logs_are_real(topology: dict) -> bool:
    """Teste que les logs contiennent des vraies mesures, pas des placeholders."""
    print("\n" + "=" * 70)
    print("TEST 3: Vérification que les logs contiennent de vraies mesures")
    print("=" * 70)

    print("\n[3.1] Exécution d'une session...")
    scenario = PDFScenario()
    result = run_scenario_with_conditions(
        topology=topology, scenario=scenario,
        bandwidth=10.0, latency=50.0, jitter=5.0, packet_loss=1.0,
        concurrent_users=2,
    )

    logs_dir = Path(result["logs_dir"])
    ok = True

    for filename, placeholder in [
        ("ping.log", "ping ok\n"),
        ("iperf.log", "iperf ok\n"),
        ("curl.log", "curl ok\n"),
    ]:
        log_path = logs_dir / filename
        if not log_path.exists():
            print(f"✗ {filename} est absent de {logs_dir}")
            ok = False
            continue

        content = log_path.read_text(encoding="utf-8")
        is_placeholder = (not content.strip()) or content == placeholder
        if is_placeholder:
            print(f"✗ {filename} est vide ou contient une valeur simulée")
            ok = False
        else:
            preview = content[:150].replace("\n", " | ")
            print(f"✓ {filename} contient de vraies mesures ({len(content)} car.)")
            print(f"  Aperçu: {preview}...")

    if not (logs_dir / "curl.log").exists() or "HTTP" not in (logs_dir / "curl.log").read_text(encoding="utf-8"):
        print("✗ curl.log ne contient pas de statut HTTP identifiable")
        ok = False

    return ok


if __name__ == "__main__":
    builder = TopologyBuilder(total_clients=3)
    topology = builder.build()
    print(f"✓ Topologie construite une seule fois pour l'ensemble du run: "
          f"{topology['server'].name} + {len(topology['clients'])} clients")
    
    test_http_range(topology)

    try:
        results = {
            "LinkConfigurator applique tc": test_link_configurator(topology),
            "Oracle réagit aux conditions réseau": test_oracle_with_conditions(topology),
            "Logs contiennent de vraies mesures": test_logs_are_real(topology),
        }

        print("\n" + "=" * 70)
        print("RÉSUMÉ")
        print("=" * 70)
        for label, passed in results.items():
            mark = "✓" if passed else "✗"
            print(f"  {mark} {label}")

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
        # Nettoyage systématique, même en cas d'échec ou d'exception,
        # pour éviter "RTNETLINK answers: File exists" au prochain run.
        print("\n[cleanup] Arrêt de la topologie Mininet...")
        topology["net"].stop()