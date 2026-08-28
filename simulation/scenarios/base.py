"""
scenarios/base.py

Classe abstraite représentant un scénario d'usage éducatif.

Chaque scénario concret (PDF, Quiz, Vidéo) porte :
- son propre ensemble de ressources réelles servies par le serveur HTTP,
  découvertes dynamiquement via discover_resources() — resource_size_mb
  est donc une métrique dérivée de la ressource réellement choisie,
  jamais une valeur tirée abstraitement ;
- son propre niveau d'interactivité (interaction_level) et sa propre
  tolérance temporelle (deadline_seconds), fixes pour le scénario ;
- son propre oracle : la règle qui décide si la session est "meaningful".

Sélection de ressource et concurrence
--------------------------------------
La ressource utilisée dans une session est tirée UNE SEULE FOIS par
session, via select_resource(rng), puis partagée par tous les
utilisateurs concurrents de cette session (même service, même ressource).

Cela isole l'effet de la concurrence : au sein d'une session, tout ce qui
concerne le service (type, identité et taille de la ressource) est fixé,
donc toute différence de label entre les utilisateurs de la même session
est attribuable uniquement à la variance induite par la contention
réseau réelle, pas à un facteur confondu (ressources différentes).

Le tirage doit se faire dans le thread principal, AVANT de lancer les
actions clientes en parallèle : un random.Random partagé n'est pas
thread-safe pour la reproductibilité de l'ordre des tirages.

Principe respecté : l'oracle ne se base QUE sur des métriques mesurées
après la session (download_time, transfer_completed, rebuffer_ratio...).
Ces métriques ne doivent JAMAIS être réinjectées comme features d'entrée
du modèle — elles servent uniquement ici, à construire le label. Le
contrat des colonnes autorisées en entrée du modèle est centralisé dans
dataset_schema.ALLOWED_FEATURE_COLUMNS.
"""

import random
from abc import ABC, abstractmethod


class Scenario(ABC):
    """Représente un type de service éducatif (PDF, Quiz, Vidéo...)."""

    name: str = None                      # identifiant court, ex: "pdf"
    interaction_level: int = None          # 0=passif ... 4=temps réel (agent IA)
    deadline_seconds: float = None          # tolérance temporelle du scénario

    # Signale à SessionGenerator qu'il doit shaper l'égress des clients
    # actifs (LinkConfigurator.apply_uplink/reset_uplink) en plus du
    # lien serveur habituel. False par défaut : la grande majorité des
    # scénarios sont purement descendants (downlink), seul un scénario
    # d'upload a besoin de ça.
    REQUIRES_UPLINK_SHAPING: bool = False

    @abstractmethod
    def discover_resources(self) -> list[dict]:
        """
        Retourne la liste des ressources disponibles pour ce scénario.

        Doit être triée de façon déterministe (ex : par nom) afin que
        select_resource(rng) soit réellement reproductible pour une
        seed donnée — l'ordre de retour d'un glob() filesystem n'est
        PAS garanti stable d'une exécution à l'autre.

        Chaque élément doit au minimum contenir : name, size_mb.
        """
        raise NotImplementedError

    def select_resource(self, rng: random.Random) -> dict:
        """
        Tire une ressource pour la session, à partir du RNG seedé du
        générateur. À appeler une seule fois par session, dans le
        thread principal.
        """
        resources = self.discover_resources()
        return rng.choice(resources)

    @abstractmethod
    def run_client_action(
        self,
        client_host,
        server,
        resource: dict,
        client_id: str,
        session_id: str,
    ) -> dict:
        """
        Exécute l'action cliente (téléchargement, requête...) sur
        l'hôte Mininet `client_host`, contre `server` (objet Mininet
        Host, utiliser server.IP() pour son adresse), pour la
        `resource` déjà sélectionnée au niveau de la session.

        client_id/session_id servent à dériver un chemin de fichier
        temporaire unique par utilisateur : plusieurs clients actifs
        s'exécutent en parallèle et ne doivent jamais écrire sur le
        même fichier (les hôtes Mininet ne sont isolés qu'au niveau
        réseau, ils partagent le même filesystem).

        Doit retourner un dict de métriques BRUTES mesurées. Ce dict
        alimente uniquement is_successful() et les logs — jamais
        directement le CSV d'entraînement (voir dataset_schema.py).
        """
        raise NotImplementedError

    @abstractmethod
    def is_successful(self, metrics: dict) -> bool:
        """
        L'ORACLE : décide si la session est 'meaningful' à partir
        des métriques mesurées. Aucune variable d'entrée (bandwidth,
        latency...) n'est utilisée ici — seulement le résultat observé.

        Doit rester défensif (metrics.get(..., default) plutôt que
        metrics[...]) : si une action cliente a échoué de façon
        inattendue et renvoyé des métriques incomplètes, l'oracle doit
        conclure non-meaningful plutôt que lever une exception.
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<Scenario:{self.name}>"