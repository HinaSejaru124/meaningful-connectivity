"""
dataset_schema.py

Contrat unique définissant les colonnes autorisées dans le dataset final.

Toute tentative d'écrire une colonne hors de ALLOWED_FEATURE_COLUMNS /
IDENTIFIER_COLUMNS / TARGET_COLUMN lève une erreur explicite plutôt que de
contaminer silencieusement le CSV avec une variable mesurée après la
session (fuite de données).
"""

# Identifiants de groupe. Ce ne sont PAS des features causales au sens ML
# (un modèle ne doit jamais s'entraîner dessus), mais ils sont nécessaires
# pour un split train/test correct : les observations issues de la même
# session ne sont pas indépendantes (elles partagent bandwidth, latency,
# jitter, packet_loss, concurrent_users, service_type, resource_size_mb),
# donc le split doit être groupé par session_id (GroupShuffleSplit /
# GroupKFold), jamais fait ligne par ligne.
IDENTIFIER_COLUMNS = {
    "session_id",
    "client_id",
}

# Variables causales, connues AVANT le lancement de la session.
# Une variable n'entre ici que si elle est à la fois (a) disponible a
# priori et (b) réellement variée par le protocole expérimental actuel.
ALLOWED_FEATURE_COLUMNS = {
    "bandwidth",
    "latency",
    "jitter",
    "packet_loss",
    "concurrent_users",
    "service_type",
    "resource_size_mb",
    "interaction_level",
    "deadline_seconds",
}

# Réservées : légitimes conceptuellement (causales), mais constantes tant
# que la topologie V1 n'introduit pas de variation réelle. Documentées ici
# pour ne pas les réinventer plus tard, mais explicitement PAS dans
# ALLOWED_FEATURE_COLUMNS tant qu'elles ne varient pas.
RESERVED_TOPOLOGY_COLUMNS = {
    "hop_count",
    "shared_bottleneck",
}

# Variables mesurées PENDANT ou APRÈS la session — jamais dans le CSV
# final. Documentées ici pour que ce soit explicite quand quelqu'un
# (nous y compris, dans 3 semaines) se demande pourquoi elles manquent.
FORBIDDEN_MEASURED_COLUMNS = {
    "download_time",
    "server_load",
    "queue_delay",
    "tcp_retransmission_rate",
    "http_status",
    "success",
    "transfer_completed",
    "duration_s",
    "within_deadline",
    "timed_out",
    "downloaded_size_bytes",
    "rebuffer_ratio",
    "segment_times",
    "resource",
    "error",
}

TARGET_COLUMN = "meaningful"


def validate_row(row: dict) -> None:
    """
    Lève une erreur si `row` contient une colonne hors du contrat, ou s'il
    manque une colonne attendue. À appeler dans DatasetWriter.append_row()
    avant toute écriture.

    Le contrat distingue trois catégories de colonnes attendues :
        - IDENTIFIER_COLUMNS (session_id, client_id) : obligatoires,
          jamais des features ML ;
        - ALLOWED_FEATURE_COLUMNS : obligatoires, ce sont les features ;
        - TARGET_COLUMN : obligatoire, c'est le label.
    """

    row_keys = set(row.keys())

    forbidden_found = row_keys & FORBIDDEN_MEASURED_COLUMNS
    if forbidden_found:
        raise ValueError(
            f"Fuite de données détectée : {forbidden_found} sont des "
            f"variables mesurées après la session et ne doivent jamais "
            f"apparaître dans le dataset d'entraînement."
        )

    expected_keys = IDENTIFIER_COLUMNS | ALLOWED_FEATURE_COLUMNS | {TARGET_COLUMN}

    unexpected = row_keys - expected_keys
    if unexpected:
        raise ValueError(
            f"Colonne(s) non déclarée(s) dans le contrat : {unexpected}. "
            f"Ajoute-les explicitement à ALLOWED_FEATURE_COLUMNS (ou "
            f"IDENTIFIER_COLUMNS) dans dataset_schema.py si c'est "
            f"intentionnel."
        )

    missing = expected_keys - row_keys
    if missing:
        raise ValueError(f"Colonne(s) manquante(s) : {missing}")