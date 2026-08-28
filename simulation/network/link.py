"""
network/link.py

Configuration dynamique du lien serveur via tc.
Utilise netem pour :
- latence
- jitter
- pertes
et tbf pour :
- limitation de bande passante.

Shaping uplink (upload)
------------------------
apply()/reset() (déjà existants) shapent l'interface SERVEUR : c'est
le goulot descendant PARTAGÉ entre tous les clients concurrents (voir
docstring d'origine du projet — netem+tbf chaînés sur h_srv↔s1).

apply_uplink()/reset_uplink() (nouveaux) shapent l'égress de CHAQUE
CLIENT individuellement, pour les scénarios d'upload. Choix
méthodologique explicite, à documenter dans le rapport : contrairement
au lien serveur (goulot partagé), l'upload est modélisé ici comme un
lien d'ACCÈS INDIVIDUEL par client (pas de contention uplink partagée
simulée) — plus proche d'une connexion domestique/mobile réelle, où le
débit montant est habituellement plafonné individuellement par le FAI
plutôt que partagé sur un dernier kilomètre commun. Modéliser un vrai
goulot uplink partagé nécessiterait un shaping d'ingress côté serveur
(dispositif IFB en Linux tc), plus complexe et plus fragile — repoussé
à une itération future si le besoin méthodologique se confirme.

Netem (latence/jitter/perte) n'est volontairement PAS dupliqué côté
client : le RTT d'une connexion TCP couvre déjà l'aller-retour complet,
donc l'appliquer une seconde fois sur l'égress client double-compterait
artificiellement la latence/le jitter déjà simulés côté serveur.
"""

from dataclasses import dataclass


@dataclass
class LinkConfigurator:
    bandwidth: float
    latency: float
    jitter: float
    packet_loss: float

    # ------------------------------------------------------------------
    # Lien serveur (goulot partagé, downstream) — inchangé
    # ------------------------------------------------------------------

    def apply(self, topology: dict) -> dict:
        server = topology["server"]
        intf = self._get_bottleneck_intf(server)

        if intf is None:
            raise RuntimeError(
                "Impossible de trouver l'interface serveur."
            )

        reset_output = server.cmd(
            f"tc qdisc del dev {intf} root 2>&1"
        )

        command = self._build_tc_command(intf)
        add_output = server.cmd(command)
        applied = self._verify(intf, server)

        return {
            "interface": intf,
            "command": command,
            "reset_output": reset_output,
            "raw_output": add_output,
            "applied": applied,
            "bandwidth": self.bandwidth,
            "latency": self.latency,
            "jitter": self.jitter,
            "packet_loss": self.packet_loss,
        }

    def _get_bottleneck_intf(self, node):
        for intf in node.intfList():
            if intf.name != "lo":
                return intf.name
        return None

    def _build_tc_command(self, intf):
        rate_kbit = max(
            int(self.bandwidth * 1000),
            1
        )
        burst = max(
            int(rate_kbit / 10),
            32
        )
        buffer = max(
            int(self.latency * 2),
            400
        )
        return (
            f"tc qdisc add dev {intf} "
            f"root handle 1: netem "
            f"delay {self.latency}ms {self.jitter}ms "
            f"distribution normal "
            f"loss {self.packet_loss}% && "
            f"tc qdisc add dev {intf} "
            f"parent 1: handle 2: tbf "
            f"rate {rate_kbit}kbit "
            f"burst {burst}kbit "
            f"latency {buffer}ms"
        )

    def _verify(self, intf, node):
        output = node.cmd(
            f"tc qdisc show dev {intf}"
        )
        return (
            "netem" in output
            and
            "tbf" in output
        )

    # ------------------------------------------------------------------
    # Lien(s) client (accès individuel, upstream) — nouveau
    # ------------------------------------------------------------------

    def apply_uplink(self, topology: dict, clients: list) -> dict:
        """
        Shape l'égress de chaque client de `clients` à `bandwidth`
        Mbit/s (tbf seul, pas de netem — voir docstring du module).
        Retourne un dict {client_name: {"applied": bool, ...}}.
        """

        results = {}

        for client in clients:
            intf = self._get_bottleneck_intf(client)

            if intf is None:
                results[client.name] = {
                    "applied": False,
                    "reason": "no interface found",
                }
                continue

            client.cmd(f"tc qdisc del dev {intf} root 2>&1")

            rate_kbit = max(int(self.bandwidth * 1000), 1)
            burst = max(int(rate_kbit / 10), 32)

            command = (
                f"tc qdisc add dev {intf} root tbf "
                f"rate {rate_kbit}kbit burst {burst}kbit latency 400ms"
            )

            raw_output = client.cmd(command)
            applied = "tbf" in client.cmd(f"tc qdisc show dev {intf}")

            results[client.name] = {
                "applied": applied,
                "interface": intf,
                "raw_output": raw_output,
            }

        return results

    def reset_uplink(self, clients: list) -> None:
        """
        Retire le shaping d'égress des clients. À appeler
        systématiquement après une session ayant utilisé
        apply_uplink() : les hôtes Mininet sont réutilisés d'une
        session à l'autre (topologie construite une seule fois), donc
        un shaping non retiré contaminerait les sessions suivantes
        avec des paramètres upload obsolètes.
        """

        for client in clients:
            intf = self._get_bottleneck_intf(client)
            if intf is not None:
                client.cmd(f"tc qdisc del dev {intf} root 2>&1")