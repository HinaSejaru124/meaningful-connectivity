#!/usr/bin/env python3

"""
Script de validation minimal pour le pipeline PDF réel.

Usage:
    sudo python3 test_pdf_session.py
"""

import sys


def test_mininet_setup():
    print("\n" + "=" * 70)
    print("TEST 1 : Vérifier que les hosts sont des objets Mininet Host")
    print("=" * 70)

    from simulation.network.topology import TopologyBuilder
    from mininet.node import Host

    builder = TopologyBuilder()

    try:
        topology = builder.build()

        clients = topology["clients"]
        server = topology["server"]

        print(f"✓ TopologyBuilder créé avec {len(clients)} clients")
        print(f"  Type du premier client: {type(clients[0])}")
        print(f"  Nom du premier client: {clients[0].name}")
        print(f"  Type du serveur: {type(server)}")
        print(f"  Nom du serveur: {server.name}")

        assert isinstance(clients[0], Host)
        assert isinstance(server, Host)

        ping = clients[0].cmd("ping -c 2 10.0.0.10")

        print("  Ping h1 -> h_srv:")
        print(ping)

        if "Destination Host Unreachable" in ping:
            raise RuntimeError(
                "h1 ne peut pas joindre h_srv"
            )

        print("✓ TEST 1 RÉUSSI\n")

        return topology

    except Exception:
        if builder.net:
            builder.stop()

        raise


def test_simple_command(topology):
    print("=" * 70)
    print("TEST 2 : Tester une commande simple")
    print("=" * 70)

    client = topology["clients"][0]

    result = client.cmd("hostname").strip()

    print("  Commande: hostname")
    print(f"  Résultat: {result}")
    print("✓ TEST 2 RÉUSSI\n")

    return True


def test_http_download(topology):
    print("=" * 70)
    print("TEST 3 : Tester le téléchargement HTTP réel")
    print("=" * 70)

    client = topology["clients"][0]
    server = topology["server"]

    server_ip = server.IP()

    cmd = (
        "curl -s -o /dev/null "
        "-w '%{http_code} %{time_total}' "
        f"http://{server_ip}:8000/pdf/sample.pdf"
    )

    print(f"  Client: {client.name}")
    print(f"  Serveur IP: {server_ip}")
    print(f"  Commande: {cmd}")

    result = client.cmd(cmd).strip()

    print(f"  Résultat brut: {result}")

    code, duration = result.split()

    print(f"  HTTP Code: {code}")
    print(f"  Time Total: {duration}s")

    if code != "200":
        raise RuntimeError(
            f"HTTP incorrect: {code}"
        )

    print("✓ TEST 3 RÉUSSI\n")

    return True


def test_full_session(topology):

    print("=" * 70)
    print("TEST 4 : Exécuter une session PDF complète")
    print("=" * 70)

    from simulation.scenarios.pdf import PDFScenario
    from simulation.session_generator import SessionGenerator

    sg = SessionGenerator(
        topology=topology
    )

    result = sg.generate_session(
        scenario=PDFScenario(),
        bandwidth=5,
        latency=40,
        jitter=5,
        packet_loss=0,
        concurrent_users=1,
    )

    print(f"  Session ID: {result['session_id']}")
    print(f"  Meaningful: {result['meaningful']}")

    print("✓ TEST 4 RÉUSSI\n")

    return True


def main():

    topology = None

    try:
        print("\n" + "=" * 70)
        print("VALIDATION DU PIPELINE PDF MININET RÉEL")
        print("=" * 70)

        topology = test_mininet_setup()

        test_simple_command(topology)

        test_http_download(topology)

        test_full_session(topology)

        print("=" * 70)
        print("✓ TOUS LES TESTS RÉUSSIS !")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ ÉCHEC : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if topology:
            try:
                topology["net"].stop()
                print("Mininet arrêté proprement")
            except Exception:
                pass


if __name__ == "__main__":
    main()