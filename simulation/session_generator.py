import json
import random
import time
from pathlib import Path

from simulation.app.runner import ApplicationRunner
from simulation.dataset_writer import DatasetWriter
from simulation.measurement.collector import MeasurementCollector
from simulation.network.link import LinkConfigurator
from simulation.oracle import Oracle


class SessionGenerator:
    """
    Orchestre l'ensemble du pipeline d'une session.

    Pipeline :
    1. sélection clients actifs + ressource partagée de la session ;
    2. configuration réseau downstream (et vérification qu'elle a
       réellement pris) ;
    3. configuration réseau uplink SI le scénario le demande
       (REQUIRES_UPLINK_SHAPING, ex. upload) ;
    4. mesures réseau (ping/iperf, sur un client observé, pour les logs) ;
    5. exécution scénario applicatif, EN PARALLÈLE sur tous les clients actifs ;
    6. collecte métriques ;
    7. oracle, appliqué INDIVIDUELLEMENT à chaque client ;
    8. sauvegarde logs ;
    9. écriture dataset — une ligne par utilisateur actif, pas une par session ;
    10. nettoyage du shaping uplink (finally, garanti même en cas d'échec).

    Ordre d'écriture volontairement ATOMIQUE : les logs (config.json,
    metrics.json, ping.log, iperf.log, curl.log) sont écrits AVANT les
    lignes CSV. Si une étape de logging échoue, l'exception remonte
    avant que la moindre ligne n'ait été ajoutée à dataset.csv.

    Nettoyage uplink GARANTI (finally) : les hôtes Mininet sont
    réutilisés d'une session à l'autre (topologie construite une seule
    fois pour tout le run). Un shaping uplink laissé en place
    contaminerait silencieusement les sessions suivantes utilisant les
    mêmes clients avec des paramètres réseau obsolètes.

    Toute la randomisation (choix des clients actifs, choix de la
    ressource) passe par un unique random.Random seedé transmis par
    l'appelant, afin que --seed rende la génération réellement
    reproductible de bout en bout.
    """

    def __init__(
        self,
        topology: dict,
        dataset_dir: str = "dataset",
        rng: random.Random | None = None,
    ):
        self.dataset_dir = Path(dataset_dir)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        self.logs_dir = self.dataset_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.dataset_writer = DatasetWriter(
            str(self.dataset_dir / "dataset.csv")
        )

        self.topology = topology
        self.rng = rng if rng is not None else random.Random()

        # Compteur de session robuste : dérivé du max des index déjà
        # présents sur disque plutôt que d'un simple len(glob(...)),
        # qui collisionnerait silencieusement (et écraserait un
        # dossier existant) si un index intermédiaire manquait après
        # une génération interrompue.
        self._next_session_index = self._compute_next_session_index()

    def _compute_next_session_index(self) -> int:
        existing_indices = []

        for path in self.logs_dir.glob("session_*"):
            suffix = path.name.removeprefix("session_")
            if suffix.isdigit():
                existing_indices.append(int(suffix))

        return (max(existing_indices) + 1) if existing_indices else 0

    def _next_session_id(self) -> str:
        session_id = f"session_{self._next_session_index:05d}"
        self._next_session_index += 1
        return session_id

    def generate_session(
        self,
        scenario,
        bandwidth: float,
        latency: float,
        jitter: float,
        packet_loss: float,
        concurrent_users: int = 4,
    ) -> dict:

        topology = self.topology

        # Tous les tirages aléatoires de la session (clients actifs,
        # client observé pour les logs, ressource) ont lieu ICI, dans
        # le thread principal, AVANT toute exécution parallèle. Fait
        # AVANT le shaping réseau : le shaping uplink conditionnel a
        # besoin de connaître active_clients.
        active_clients = self.rng.sample(
            topology["clients"],
            k=concurrent_users,
        )

        observed_client = self.rng.choice(active_clients)

        # Même service ET même ressource pour tous les utilisateurs
        # concurrents de la session (voir scenarios/base.py) : isole
        # l'effet de la concurrence de celui de la taille de ressource.
        resource = scenario.select_resource(self.rng)

        link_configurator = LinkConfigurator(
            bandwidth=bandwidth,
            latency=latency,
            jitter=jitter,
            packet_loss=packet_loss,
        )

        link_config = link_configurator.apply(topology)

        if not link_config.get("applied", False):
            # Sans ce contrôle, la session continuerait avec des
            # conditions réseau non appliquées (tc en échec silencieux)
            # tout en enregistrant dans le CSV les valeurs PRÉVUES —
            # un mislabeling silencieux qui ne casse rien visiblement.
            raise RuntimeError(
                "La configuration réseau (tc) n'a pas été appliquée "
                f"correctement : {link_config}"
            )

        requires_uplink = getattr(scenario, "REQUIRES_UPLINK_SHAPING", False)
        uplink_config = None

        if requires_uplink:
            uplink_config = link_configurator.apply_uplink(topology, active_clients)

            not_applied = [
                name for name, result in uplink_config.items()
                if not result.get("applied", False)
            ]

            if not_applied:
                raise RuntimeError(
                    "Le shaping uplink (upload) n'a pas été appliqué "
                    f"correctement pour : {not_applied} — {uplink_config}"
                )

        try:
            ping_result = self._measure_ping(
                observed_client,
                topology["server"]
            )

            iperf_result = self._measure_iperf(
                observed_client,
                topology["server"]
            )

            runner = ApplicationRunner(
                server=topology["server"]
            )

            session_id = self._next_session_id()

            run_results = runner.run(
                scenario,
                active_clients,
                resource,
                session_id,
            )

            measurement = MeasurementCollector.collect(run_results)

            oracle = Oracle(scenario)

            # --------------------------------------------------------
            # 1. Logs d'abord (traçabilité / reproduction).
            # --------------------------------------------------------

            session_path = self.logs_dir / session_id
            session_path.mkdir(parents=True, exist_ok=True)

            config = {
                "network": {
                    "bandwidth": bandwidth,
                    "latency": latency,
                    "jitter": jitter,
                    "packet_loss": packet_loss,
                    "uplink_shaped": requires_uplink,
                },

                "application": {
                    "service_type": scenario.name,
                    "resource_name": resource.get("name"),
                    "resource_size_mb": resource.get("size_mb"),
                },

                "users": {
                    "concurrent_users": concurrent_users,
                    "observed_client": observed_client.name,
                    "active_clients": [c.name for c in active_clients],
                },

                "topology": {
                    "type": "single_switch_star",
                    "switch": "s1",
                    "server": "h_srv",
                    "server_ip": topology["server_ip"],
                    "bottleneck": {
                        "from": "s1",
                        "to": "h_srv",
                        "direction": "downstream",
                    },
                },
            }

            (session_path / "config.json").write_text(
                json.dumps(config, indent=2),
                encoding="utf-8"
            )

            MeasurementCollector.save_metrics(measurement, str(session_path))

            (session_path / "ping.log").write_text(ping_result, encoding="utf-8")
            (session_path / "iperf.log").write_text(iperf_result, encoding="utf-8")
            (session_path / "curl.log").write_text(
                self._get_curl_log(run_results),
                encoding="utf-8"
            )

            # --------------------------------------------------------
            # 2. Dataset ML ensuite : une observation par client actif,
            # pas une par session. Écrit en dernier, une fois tous les
            # logs correctement en place.
            # --------------------------------------------------------

            rows = []

            for sample in measurement["samples"]:
                meaningful = oracle.evaluate(sample)

                row = {
                    "session_id": session_id,
                    "client_id": sample["client"],
                    "bandwidth": float(bandwidth),
                    "latency": float(latency),
                    "jitter": float(jitter),
                    "packet_loss": float(packet_loss),
                    "service_type": scenario.name,
                    "resource_size_mb": round(
                        float(sample.get("resource_size_mb", resource.get("size_mb", 0.0))),
                        3,
                    ),
                    "concurrent_users": int(concurrent_users),
                    "interaction_level": scenario.interaction_level,
                    "deadline_seconds": scenario.deadline_seconds,
                    "meaningful": int(meaningful),
                }

                self.dataset_writer.append_row(row)
                rows.append(row)

            return {
                "session_id": session_id,
                "observed_client": observed_client,
                "resource_name": resource.get("name"),
                "resource_size_mb": resource.get("size_mb"),
                "rows": rows,
                "total_observations": len(rows),
                "meaningful_count": sum(r["meaningful"] for r in rows),
                "logs_dir": str(session_path),
                "link_config": link_config,
                "uplink_config": uplink_config,
            }

        finally:
            # Nettoyage GARANTI, même si une exception a été levée
            # plus haut : un shaping uplink oublié contaminerait les
            # sessions suivantes qui réutilisent les mêmes clients.
            if requires_uplink:
                link_configurator.reset_uplink(active_clients)

    def _measure_ping(self, client, server):
        try:
            return client.cmd(
                f"ping -c 3 {server.IP()} 2>&1"
            )
        except Exception as e:
            return f"Ping error: {e}\n"

    def _measure_iperf(self, client, server):
        try:
            server.cmd(
                "timeout 10 iperf -s -p 5001 &"
            )

            time.sleep(0.5)

            return client.cmd(
                f"iperf -c {server.IP()} -p 5001 -t 3 2>&1"
            )

        except Exception as e:
            return f"Iperf error: {e}\n"

    def _get_curl_log(self, run_results):
        lines = []

        for entry in run_results:
            client = entry.get("client", "unknown")
            metrics = entry.get("metrics", {})

            lines.append(
                f"[{client}] "
                f"HTTP {metrics.get('http_status', '?')} - "
                f"{metrics.get('download_time', '?')}s\n"
            )

        return "".join(lines)