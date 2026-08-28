"""
app/runner.py

Orchestre l'exécution des actions applicatives sur les clients actifs
d'une session, EN PARALLÈLE : concurrent_users représente des
utilisateurs actifs simultanément, pas des actions exécutées
successivement. Une boucle for séquentielle ne produit pas de
contention réseau réelle et ne représente donc pas correctement le
phénomène que le dataset doit capturer.

La ressource utilisée est déjà sélectionnée au niveau de la session
(voir scenarios/base.py::select_resource) et transmise ici telle
quelle : aucun tirage aléatoire ne doit avoir lieu dans les threads,
pour ne pas casser la reproductibilité du RNG seedé du générateur.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ApplicationRunner:
    """Orchestre l'exécution des actions applicatives sur les clients actifs."""

    server: object

    def run(
        self,
        scenario,
        active_clients: Iterable,
        resource: dict,
        session_id: str,
        max_workers: int | None = None,
    ) -> list[dict]:

        active_clients = list(active_clients)

        if not active_clients:
            return []

        results_by_client: dict[str, dict] = {}

        with ThreadPoolExecutor(
            max_workers=max_workers or len(active_clients)
        ) as executor:

            future_to_client = {
                executor.submit(
                    scenario.run_client_action,
                    client_host,
                    self.server,
                    resource,
                    client_host.name,
                    session_id,
                ): client_host
                for client_host in active_clients
            }

            for future in as_completed(future_to_client):
                client_host = future_to_client[future]

                try:
                    metrics = future.result()
                except Exception as exc:
                    # Une exception inattendue dans un client ne doit
                    # pas faire échouer les autres clients concurrents
                    # ni toute la session : on l'isole et on la trace
                    # explicitement dans les métriques de ce client.
                    # L'oracle défensif (metrics.get(..., default))
                    # traitera ceci comme non-meaningful.
                    metrics = {
                        "resource": resource.get("name"),
                        "resource_size_mb": resource.get("size_mb", 0.0),
                        "error": f"unhandled exception: {exc}",
                    }

                results_by_client[client_host.name] = metrics

        # Ordre stable (celui de active_clients) plutôt que l'ordre
        # d'achèvement des threads, pour des logs/CSV reproductibles à
        # lire et diffables entre exécutions.
        return [
            {"client": client_host.name, "metrics": results_by_client[client_host.name]}
            for client_host in active_clients
        ]