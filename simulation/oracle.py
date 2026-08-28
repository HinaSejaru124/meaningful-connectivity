from dataclasses import dataclass


@dataclass
class Oracle:
    """Oracle de classification supervisée.

    Le label `meaningful` est calculé uniquement à partir des métriques
    observées après exécution. La topologie et les paramètres réseau n’y
    participent pas directement, selon la contrainte architecturale.
    """

    scenario: object

    def evaluate(self, metrics: dict) -> bool:
        return bool(self.scenario.is_successful(metrics))
