#!/usr/bin/env python3

"""
AUDIT DATASET — Meaningful Connectivity

Audit de cohérence et de qualité du dataset généré par le pipeline
Meaningful Connectivity.

Arborescence attendue :

dataset/
├── dataset.csv
└── logs/
    ├── session_00000/
    │   ├── config.json
    │   ├── curl.log
    │   ├── iperf.log
    │   ├── metrics.json
    │   └── ping.log
    └── ...

Le script vérifie notamment :

1. Intégrité du dataset.csv
2. Présence et validité des sessions
3. Cohérence CSV <-> config.json
4. Cohérence CSV <-> metrics.json
5. Cohérence des clients actifs
6. Cohérence du nombre d'observations
7. Cohérence des tailles de ressources
8. Cohérence des paramètres réseau
9. Validité des labels meaningful
10. Cohérence du contrat PDF
11. Détection des 404 et autres erreurs HTTP
12. Détection des transferts incomplets
13. Détection des timeouts
14. Détection des doublons
15. Détection des valeurs manquantes / invalides
16. Analyse de la distribution des classes
17. Analyse de la diversité des sessions
18. Vérification de l'indépendance des observations
19. Rapport global de fiabilité

Le script ne modifie absolument aucun fichier.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


# ============================================================================
# CONSTANTES
# ============================================================================

REQUIRED_CSV_COLUMNS = {
    "session_id",
    "client_id",
    "bandwidth",
    "latency",
    "jitter",
    "packet_loss",
    "service_type",
    "resource_size_mb",
    "concurrent_users",
    "interaction_level",
    "deadline_seconds",
    "meaningful",
}

REQUIRED_SESSION_FILES = {
    "config.json",
    "metrics.json",
    "ping.log",
    "iperf.log",
    "curl.log",
}

NUMERIC_COLUMNS = {
    "bandwidth",
    "latency",
    "jitter",
    "packet_loss",
    "resource_size_mb",
    "concurrent_users",
    "interaction_level",
    "deadline_seconds",
    "meaningful",
}

EXPECTED_SERVICES = {
    "pdf",
    "quiz",
    "video_streaming",
}


# ============================================================================
# OUTILS GÉNÉRAUX
# ============================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_section(title: str) -> None:
    print()
    print("-" * 80)
    print(title)
    print("-" * 80)


def ok(message: str) -> None:
    print(f"✓ {message}")


def warning(message: str) -> None:
    print(f"⚠ {message}")


def error(message: str) -> None:
    print(f"✗ {message}")


def info(message: str) -> None:
    print(f"  {message}")


def load_json(path: Path) -> tuple[Any | None, str | None]:
    """
    IMPORTANT :

    Cette fonction retourne TOUJOURS exactement deux valeurs :

        (data, error)

    ou :

        (None, error)

    Cela évite le bug :
        ValueError: too many values to unpack (expected 2)
    """

    if not path.exists():
        return None, f"fichier absent : {path}"

    if not path.is_file():
        return None, f"ce chemin n'est pas un fichier : {path}"

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"lecture impossible : {exc}"

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, (
            f"JSON invalide : ligne {exc.lineno}, "
            f"colonne {exc.colno} : {exc.msg}"
        )

    return data, None


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

            if value.lower() in {"nan", "inf", "+inf", "-inf", "infinity"}:
                return float(value)

        return float(value)

    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None

        return int(value)

    except (TypeError, ValueError):
        return None


def is_finite_number(value: Any) -> bool:
    number = safe_float(value)

    return number is not None and math.isfinite(number)


def values_equal(a: Any, b: Any, tolerance: float = 1e-9) -> bool:
    """
    Comparaison robuste entre valeurs numériques et autres valeurs.
    """

    if a is None or b is None:
        return a == b

    fa = safe_float(a)
    fb = safe_float(b)

    if fa is not None and fb is not None:
        return math.isclose(
            fa,
            fb,
            rel_tol=tolerance,
            abs_tol=tolerance,
        )

    return str(a) == str(b)


def session_sort_key(path: Path) -> tuple[int, str]:
    name = path.name

    if name.startswith("session_"):
        suffix = name[len("session_"):]

        if suffix.isdigit():
            return int(suffix), name

    return 10**12, name


# ============================================================================
# CHARGEMENT DU DATASET CSV
# ============================================================================

def load_dataset_csv(
    dataset_csv: Path,
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []

    if not dataset_csv.exists():
        errors.append(f"dataset CSV absent : {dataset_csv}")
        return rows, errors, warnings

    try:
        with dataset_csv.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:

            reader = csv.DictReader(handle)

            if reader.fieldnames is None:
                errors.append("dataset.csv ne contient aucun header")
                return rows, errors, warnings

            columns = set(reader.fieldnames)

            missing = REQUIRED_CSV_COLUMNS - columns

            if missing:
                errors.append(
                    "Colonnes obligatoires absentes : "
                    + ", ".join(sorted(missing))
                )

            extra = columns - REQUIRED_CSV_COLUMNS

            if extra:
                warnings.append(
                    "Colonnes supplémentaires détectées : "
                    + ", ".join(sorted(extra))
                )

            for line_number, row in enumerate(reader, start=2):

                if not any(
                    value is not None and str(value).strip()
                    for value in row.values()
                ):
                    warnings.append(
                        f"Ligne CSV vide ignorée : ligne {line_number}"
                    )
                    continue

                row["_line"] = str(line_number)
                rows.append(row)

    except OSError as exc:
        errors.append(f"Impossible de lire dataset.csv : {exc}")

    except csv.Error as exc:
        errors.append(f"Erreur CSV : {exc}")

    return rows, errors, warnings


# ============================================================================
# AUDIT CSV
# ============================================================================

def audit_csv_structure(
    rows: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not rows:
        errors.append("dataset.csv ne contient aucune observation")
        return errors, warnings

    duplicate_keys: Counter[tuple[str, str]] = Counter()

    for row in rows:

        line = row.get("_line", "?")

        session_id = row.get("session_id", "").strip()
        client_id = row.get("client_id", "").strip()

        if not session_id:
            errors.append(
                f"Ligne {line} : session_id vide"
            )

        if not client_id:
            errors.append(
                f"Ligne {line} : client_id vide"
            )

        if session_id and client_id:
            duplicate_keys[(session_id, client_id)] += 1

        for column in REQUIRED_CSV_COLUMNS:

            value = row.get(column)

            if value is None or not str(value).strip():
                errors.append(
                    f"Ligne {line} : valeur manquante pour {column}"
                )
                continue

            if column in NUMERIC_COLUMNS:

                number = safe_float(value)

                if number is None:
                    errors.append(
                        f"Ligne {line} : {column} "
                        f"n'est pas numérique : {value!r}"
                    )

                elif not math.isfinite(number):
                    errors.append(
                        f"Ligne {line} : {column} "
                        f"est non fini : {value!r}"
                    )

    for key, count in duplicate_keys.items():

        if count > 1:
            session_id, client_id = key

            errors.append(
                f"Doublon CSV : ({session_id}, {client_id}) "
                f"apparaît {count} fois"
            )

    return errors, warnings


# ============================================================================
# AUDIT DES VALEURS CSV
# ============================================================================

def audit_csv_values(
    rows: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for row in rows:

        line = row.get("_line", "?")

        bandwidth = safe_float(row.get("bandwidth"))
        latency = safe_float(row.get("latency"))
        jitter = safe_float(row.get("jitter"))
        packet_loss = safe_float(row.get("packet_loss"))
        resource_size = safe_float(row.get("resource_size_mb"))
        concurrent = safe_int(row.get("concurrent_users"))
        interaction = safe_int(row.get("interaction_level"))
        deadline = safe_float(row.get("deadline_seconds"))
        meaningful = safe_int(row.get("meaningful"))

        if bandwidth is not None and bandwidth <= 0:
            errors.append(
                f"Ligne {line} : bandwidth <= 0"
            )

        if latency is not None and latency < 0:
            errors.append(
                f"Ligne {line} : latency < 0"
            )

        if jitter is not None and jitter < 0:
            errors.append(
                f"Ligne {line} : jitter < 0"
            )

        if packet_loss is not None and not 0 <= packet_loss <= 100:
            errors.append(
                f"Ligne {line} : packet_loss hors [0,100]"
            )

        if resource_size is not None and resource_size <= 0:
            errors.append(
                f"Ligne {line} : resource_size_mb <= 0"
            )

        if concurrent is not None and concurrent <= 0:
            errors.append(
                f"Ligne {line} : concurrent_users <= 0"
            )

        if deadline is not None and deadline <= 0:
            errors.append(
                f"Ligne {line} : deadline_seconds <= 0"
            )

        if meaningful not in {0, 1}:
            errors.append(
                f"Ligne {line} : meaningful doit être 0 ou 1"
            )

        service = row.get("service_type", "").strip()

        if service not in EXPECTED_SERVICES:
            warnings.append(
                f"Ligne {line} : service_type inhabituel : {service!r}"
            )

    return errors, warnings


# ============================================================================
# DÉCOUVERTE DES SESSIONS
# ============================================================================

def discover_sessions(
    logs_dir: Path,
) -> tuple[list[Path], list[str], list[str]]:
    sessions: list[Path] = []
    errors: list[str] = []
    warnings: list[str] = []

    if not logs_dir.exists():
        errors.append(
            f"répertoire logs absent : {logs_dir}"
        )
        return sessions, errors, warnings

    if not logs_dir.is_dir():
        errors.append(
            f"logs n'est pas un répertoire : {logs_dir}"
        )
        return sessions, errors, warnings

    for path in sorted(
        logs_dir.iterdir(),
        key=session_sort_key,
    ):

        if not path.is_dir():
            continue

        if path.name.startswith("session_"):
            sessions.append(path)

    if not sessions:
        warnings.append(
            "Aucune session trouvée dans dataset/logs/"
        )

    return sessions, errors, warnings


# ============================================================================
# AUDIT DES FICHIERS DE SESSION
# ============================================================================

def audit_session_files(
    sessions: list[Path],
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    session_data: dict[str, dict[str, Any]] = {}

    errors: list[str] = []
    warnings: list[str] = []

    for session_path in sessions:

        session_id = session_path.name

        data: dict[str, Any] = {
            "path": session_path,
            "config": None,
            "metrics": None,
        }

        for filename in REQUIRED_SESSION_FILES:

            path = session_path / filename

            if not path.exists():

                errors.append(
                    f"{session_id} : fichier manquant : {filename}"
                )

                continue

            if path.is_dir():

                errors.append(
                    f"{session_id} : {filename} est un répertoire"
                )

                continue

            if filename == "config.json":

                config, load_error = load_json(path)

                if load_error:
                    errors.append(
                        f"{session_id}/config.json : {load_error}"
                    )

                else:
                    data["config"] = config

            elif filename == "metrics.json":

                metrics, load_error = load_json(path)

                if load_error:
                    errors.append(
                        f"{session_id}/metrics.json : {load_error}"
                    )

                else:
                    data["metrics"] = metrics

            else:

                try:
                    content = path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )

                    data[filename] = content

                except OSError as exc:
                    errors.append(
                        f"{session_id}/{filename} : "
                        f"lecture impossible : {exc}"
                    )

        session_data[session_id] = data

    return session_data, errors, warnings


# ============================================================================
# AUDIT CONFIGS
# ============================================================================

def audit_configs(
    session_data: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for session_id, data in session_data.items():

        config = data.get("config")

        if config is None:
            continue

        if not isinstance(config, dict):
            errors.append(
                f"{session_id}/config.json : "
                "la racine JSON doit être un objet"
            )
            continue

        network = config.get("network")

        if not isinstance(network, dict):
            errors.append(
                f"{session_id} : config.network absent/invalide"
            )
        else:

            for field in (
                "bandwidth",
                "latency",
                "jitter",
                "packet_loss",
            ):

                if field not in network:
                    errors.append(
                        f"{session_id} : "
                        f"config.network.{field} absent"
                    )
                    continue

                value = safe_float(network[field])

                if value is None or not math.isfinite(value):
                    errors.append(
                        f"{session_id} : "
                        f"network.{field} invalide"
                    )

        application = config.get("application")

        if not isinstance(application, dict):
            errors.append(
                f"{session_id} : "
                "config.application absent/invalide"
            )
        else:

            if not application.get("service_type"):
                errors.append(
                    f"{session_id} : service_type absent"
                )

            if not application.get("resource_name"):
                errors.append(
                    f"{session_id} : resource_name absent"
                )

            resource_size = safe_float(
                application.get("resource_size_mb")
            )

            if resource_size is None or resource_size <= 0:
                errors.append(
                    f"{session_id} : resource_size_mb invalide"
                )

        users = config.get("users")

        if not isinstance(users, dict):
            errors.append(
                f"{session_id} : config.users absent/invalide"
            )
        else:

            concurrent = safe_int(
                users.get("concurrent_users")
            )

            active_clients = users.get(
                "active_clients"
            )

            observed_client = users.get(
                "observed_client"
            )

            if concurrent is None or concurrent <= 0:
                errors.append(
                    f"{session_id} : "
                    "concurrent_users invalide"
                )

            if not isinstance(active_clients, list):
                errors.append(
                    f"{session_id} : "
                    "active_clients doit être une liste"
                )
            else:

                if concurrent is not None:
                    if len(active_clients) != concurrent:
                        errors.append(
                            f"{session_id} : "
                            f"concurrent_users={concurrent}, "
                            f"mais {len(active_clients)} "
                            "active_clients"
                        )

                if len(set(active_clients)) != len(active_clients):
                    errors.append(
                        f"{session_id} : "
                        "active_clients contient des doublons"
                    )

                if observed_client not in active_clients:
                    errors.append(
                        f"{session_id} : "
                        "observed_client n'est pas "
                        "dans active_clients"
                    )

        topology = config.get("topology")

        if not isinstance(topology, dict):
            warnings.append(
                f"{session_id} : topology absente"
            )

    return errors, warnings


# ============================================================================
# EXTRACTION DES SAMPLES METRICS
# ============================================================================

def get_metrics_samples(
    metrics: Any,
) -> list[dict[str, Any]]:
    if not isinstance(metrics, dict):
        return []

    samples = metrics.get("samples")

    if not isinstance(samples, list):
        return []

    return [
        sample
        for sample in samples
        if isinstance(sample, dict)
    ]


# ============================================================================
# AUDIT METRICS
# ============================================================================

def audit_metrics(
    session_data: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    warnings: list[str] = []

    metrics_summary: dict[str, dict[str, Any]] = {}

    for session_id, data in session_data.items():

        metrics = data.get("metrics")

        if metrics is None:
            continue

        if not isinstance(metrics, dict):
            errors.append(
                f"{session_id} : metrics.json doit "
                "contenir un objet JSON"
            )
            continue

        samples = get_metrics_samples(metrics)

        observed_clients = safe_int(
            metrics.get("observed_clients")
        )

        if observed_clients is None:
            errors.append(
                f"{session_id} : observed_clients invalide"
            )
            observed_clients = 0

        if observed_clients != len(samples):
            errors.append(
                f"{session_id} : "
                f"observed_clients={observed_clients}, "
                f"mais {len(samples)} samples"
            )

        sample_clients = []

        for index, sample in enumerate(samples):

            client = sample.get("client")

            if not client:
                errors.append(
                    f"{session_id} : sample {index} "
                    "sans client"
                )
            else:
                sample_clients.append(client)

            http_status = safe_int(
                sample.get("http_status")
            )

            downloaded = safe_int(
                sample.get("downloaded_size_bytes")
            )

            download_time = safe_float(
                sample.get("download_time")
            )

            resource_size = safe_float(
                sample.get("resource_size_mb")
            )

            transfer_completed = sample.get(
                "transfer_completed"
            )

            timed_out = sample.get(
                "timed_out"
            )

            within_deadline = sample.get(
                "within_deadline"
            )

            if http_status is None:
                errors.append(
                    f"{session_id} : sample {index} "
                    "http_status invalide"
                )

            if downloaded is None or downloaded < 0:
                errors.append(
                    f"{session_id} : sample {index} "
                    "downloaded_size_bytes invalide"
                )

            if download_time is None:
                errors.append(
                    f"{session_id} : sample {index} "
                    "download_time invalide"
                )

            if resource_size is None or resource_size <= 0:
                errors.append(
                    f"{session_id} : sample {index} "
                    "resource_size_mb invalide"
                )

            if not isinstance(
                transfer_completed,
                bool,
            ):
                errors.append(
                    f"{session_id} : sample {index} "
                    "transfer_completed n'est pas booléen"
                )

            if not isinstance(timed_out, bool):
                errors.append(
                    f"{session_id} : sample {index} "
                    "timed_out n'est pas booléen"
                )

            if not isinstance(
                within_deadline,
                bool,
            ):
                errors.append(
                    f"{session_id} : sample {index} "
                    "within_deadline n'est pas booléen"
                )

        if len(set(sample_clients)) != len(sample_clients):
            errors.append(
                f"{session_id} : clients dupliqués dans metrics"
            )

        metrics_summary[session_id] = {
            "observed_clients": observed_clients,
            "samples": samples,
            "sample_clients": sample_clients,
        }

    return errors, warnings, metrics_summary


# ============================================================================
# COHÉRENCE CONFIG <-> METRICS
# ============================================================================

def audit_config_metrics_consistency(
    session_data: dict[str, dict[str, Any]],
    metrics_summary: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for session_id, data in session_data.items():

        config = data.get("config")
        metric_info = metrics_summary.get(session_id)

        if not isinstance(config, dict):
            continue

        if metric_info is None:
            continue

        users = config.get("users", {})

        if not isinstance(users, dict):
            continue

        active_clients = users.get(
            "active_clients",
            [],
        )

        metric_clients = metric_info["sample_clients"]

        if set(active_clients) != set(metric_clients):
            errors.append(
                f"{session_id} : "
                "active_clients != clients présents "
                "dans metrics.json"
            )

        concurrent = safe_int(
            users.get("concurrent_users")
        )

        observed = metric_info["observed_clients"]

        if concurrent is not None and concurrent != observed:
            errors.append(
                f"{session_id} : "
                f"concurrent_users={concurrent} "
                f"mais observed_clients={observed}"
            )

        application = config.get(
            "application",
            {},
        )

        resource_name = application.get(
            "resource_name"
        )

        resource_size = safe_float(
            application.get(
                "resource_size_mb"
            )
        )

        service_type = application.get(
            "service_type"
        )

        for index, sample in enumerate(
            metric_info["samples"]
        ):

            sample_resource = sample.get(
                "resource"
            )

            sample_size = safe_float(
                sample.get(
                    "resource_size_mb"
                )
            )

            if resource_name != sample_resource:
                errors.append(
                    f"{session_id} : sample {index} "
                    f"resource={sample_resource!r}, "
                    f"config={resource_name!r}"
                )

            if resource_size is not None and sample_size is not None:

                if not math.isclose(
                    resource_size,
                    sample_size,
                    rel_tol=1e-6,
                    abs_tol=0.001,
                ):
                    errors.append(
                        f"{session_id} : sample {index} "
                        "resource_size_mb incohérente"
                    )

    return errors, warnings


# ============================================================================
# COHÉRENCE CSV <-> LOGS
# ============================================================================

def audit_csv_vs_sessions(
    rows: list[dict[str, str]],
    session_data: dict[str, dict[str, Any]],
    metrics_summary: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    csv_by_session: defaultdict[str, list[dict[str, str]]] = (
        defaultdict(list)
    )

    for row in rows:
        csv_by_session[
            row.get("session_id", "").strip()
        ].append(row)

    csv_sessions = set(csv_by_session)
    log_sessions = set(session_data)

    for session_id in sorted(
        csv_sessions - log_sessions
    ):
        errors.append(
            f"{session_id} : présent dans CSV "
            "mais absent de dataset/logs/"
        )

    for session_id in sorted(
        log_sessions - csv_sessions
    ):
        warnings.append(
            f"{session_id} : logs présents "
            "mais aucune ligne CSV"
        )

    for session_id in sorted(
        csv_sessions & log_sessions
    ):

        csv_rows = csv_by_session[session_id]

        metric_info = metrics_summary.get(
            session_id
        )

        if metric_info is None:
            continue

        samples = metric_info["samples"]

        if len(csv_rows) != len(samples):
            errors.append(
                f"{session_id} : "
                f"{len(csv_rows)} lignes CSV contre "
                f"{len(samples)} samples metrics"
            )

        csv_clients = {
            row.get("client_id", "").strip()
            for row in csv_rows
        }

        metric_clients = set(
            metric_info["sample_clients"]
        )

        if csv_clients != metric_clients:
            errors.append(
                f"{session_id} : clients CSV != clients metrics"
            )

        config = session_data[session_id].get(
            "config"
        )

        if not isinstance(config, dict):
            continue

        network = config.get(
            "network",
            {}
        )

        application = config.get(
            "application",
            {}
        )

        users = config.get(
            "users",
            {}
        )

        for row in csv_rows:

            line = row.get("_line", "?")

            comparisons = {
                "bandwidth": network.get("bandwidth"),
                "latency": network.get("latency"),
                "jitter": network.get("jitter"),
                "packet_loss": network.get("packet_loss"),
                "service_type": application.get("service_type"),
                "resource_size_mb": application.get(
                    "resource_size_mb"
                ),
                "concurrent_users": users.get(
                    "concurrent_users"
                ),
            }

            for field, expected in comparisons.items():

                actual = row.get(field)

                if expected is None:
                    continue

                if not values_equal(
                    actual,
                    expected,
                    tolerance=1e-6,
                ):
                    errors.append(
                        f"Ligne {line} ({session_id}) : "
                        f"{field} CSV={actual!r}, "
                        f"config={expected!r}"
                    )

    return errors, warnings


# ============================================================================
# COHÉRENCE LABEL <-> MÉTRIQUES
# ============================================================================

def expected_pdf_label(
    sample: dict[str, Any],
    deadline: float,
) -> int:
    http_status = safe_int(
        sample.get("http_status")
    )

    transfer_completed = sample.get(
        "transfer_completed",
        False,
    )

    timed_out = sample.get(
        "timed_out",
        False,
    )

    download_time = safe_float(
        sample.get("download_time")
    )

    if http_status != 200:
        return 0

    if transfer_completed is not True:
        return 0

    if timed_out is True:
        return 0

    if download_time is None:
        return 0

    return int(download_time < deadline)


def audit_labels(
    rows: list[dict[str, str]],
    session_data: dict[str, dict[str, Any]],
    metrics_summary: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    csv_by_key: dict[tuple[str, str], dict[str, str]] = {}

    for row in rows:

        key = (
            row.get("session_id", "").strip(),
            row.get("client_id", "").strip(),
        )

        csv_by_key[key] = row

    for session_id, metric_info in metrics_summary.items():

        config = session_data[session_id].get(
            "config"
        )

        if not isinstance(config, dict):
            continue

        application = config.get(
            "application",
            {}
        )

        service_type = application.get(
            "service_type"
        )

        if service_type != "pdf":
            continue

        deadline = safe_float(
            session_data[session_id]
            .get("config", {})
            .get("application", {})
            .get("deadline_seconds")
        )

        if deadline is None:
            # Le config actuel ne contient pas forcément
            # deadline_seconds ; le contrat PDF est 10 s.
            deadline = 10.0

        for sample in metric_info["samples"]:

            client = sample.get("client")

            key = (
                session_id,
                str(client),
            )

            row = csv_by_key.get(key)

            if row is None:
                continue

            actual_label = safe_int(
                row.get("meaningful")
            )

            expected_label = expected_pdf_label(
                sample,
                deadline,
            )

            if actual_label != expected_label:
                errors.append(
                    f"{session_id}/{client} : "
                    f"label CSV={actual_label}, "
                    f"label attendu={expected_label} "
                    f"à partir des metrics"
                )

    return errors, warnings


# ============================================================================
# AUDIT SPÉCIFIQUE DES 404
# ============================================================================

def audit_http_errors(
    session_data: dict[str, dict[str, Any]],
    metrics_summary: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    status_counter: Counter[int] = Counter()
    error_counter: Counter[str] = Counter()

    for session_id, metric_info in metrics_summary.items():

        for sample in metric_info["samples"]:

            status = safe_int(
                sample.get("http_status")
            )

            if status is not None:
                status_counter[status] += 1

            sample_error = sample.get(
                "error"
            )

            if sample_error:
                error_counter[
                    str(sample_error)
                ] += 1

            if status == 404:

                resource = sample.get(
                    "resource",
                    "<unknown>",
                )

                warnings.append(
                    f"{session_id}/{sample.get('client')} : "
                    f"HTTP 404 pour {resource!r}"
                )

    if status_counter:
        info(
            "Codes HTTP observés : "
            + ", ".join(
                f"{status}={count}"
                for status, count
                in sorted(status_counter.items())
            )
        )

    if error_counter:
        info(
            "Erreurs applicatives observées : "
            + ", ".join(
                f"{error!r}={count}"
                for error, count
                in error_counter.most_common()
            )
        )

    return errors, warnings


# ============================================================================
# AUDIT DES 404 — DIAGNOSTIC RESSOURCE
# ============================================================================

def audit_resource_availability(
    session_data: dict[str, dict[str, Any]],
    metrics_summary: dict[str, dict[str, Any]],
    dataset_root: Path,
) -> tuple[list[str], list[str]]:
    """
    Vérifie notamment que les ressources demandées existent réellement
    dans htdocs/pdf/.

    Un 404 systématique sur une ressource qui n'existe pas localement
    est un problème de génération de scénario / ressource, et non une
    condition réseau.
    """

    errors: list[str] = []
    warnings: list[str] = []

    pdf_dir = dataset_root.parent / "htdocs" / "pdf"

    if not pdf_dir.exists():
        warnings.append(
            f"Répertoire htdocs/pdf introuvable pour vérification "
            f"locale : {pdf_dir}"
        )
        return errors, warnings

    available = {
        path.name
        for path in pdf_dir.glob("*.pdf")
    }

    for session_id, metric_info in metrics_summary.items():

        config = session_data[session_id].get(
            "config"
        )

        if not isinstance(config, dict):
            continue

        application = config.get(
            "application",
            {}
        )

        service_type = application.get(
            "service_type"
        )

        if service_type != "pdf":
            continue

        resource_name = application.get(
            "resource_name"
        )

        if not resource_name:
            continue

        if resource_name not in available:

            warnings.append(
                f"{session_id} : ressource demandée "
                f"{resource_name!r} absente de htdocs/pdf/"
            )

    return errors, warnings


# ============================================================================
# AUDIT DES TRANSFERTS
# ============================================================================

def audit_transfers(
    metrics_summary: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    incomplete = 0
    timed_out = 0
    successful = 0

    for session_id, metric_info in metrics_summary.items():

        for sample in metric_info["samples"]:

            completed = sample.get(
                "transfer_completed"
            )

            timeout = sample.get(
                "timed_out"
            )

            if completed is True:
                successful += 1
            else:
                incomplete += 1

            if timeout is True:
                timed_out += 1

    info(f"Transferts complets : {successful}")
    info(f"Transferts incomplets : {incomplete}")
    info(f"Timeouts : {timed_out}")

    return errors, warnings


# ============================================================================
# STATISTIQUES DATASET
# ============================================================================

def dataset_statistics(
    rows: list[dict[str, str]],
) -> None:
    print_section("STATISTIQUES DU DATASET")

    if not rows:
        return

    sessions = {
        row.get("session_id", "").strip()
        for row in rows
    }

    clients = {
        row.get("client_id", "").strip()
        for row in rows
    }

    labels = Counter(
        safe_int(row.get("meaningful"))
        for row in rows
    )

    services = Counter(
        row.get("service_type", "").strip()
        for row in rows
    )

    print(f"Observations        : {len(rows)}")
    print(f"Sessions            : {len(sessions)}")
    print(f"Clients distincts   : {len(clients)}")

    print()
    print("Classes :")

    total = len(rows)

    for label in sorted(labels):
        count = labels[label]
        percentage = (
            100.0 * count / total
            if total
            else 0.0
        )

        print(
            f"  meaningful={label}: "
            f"{count} ({percentage:.2f}%)"
        )

    print()
    print("Scénarios :")

    for service, count in services.items():

        percentage = (
            100.0 * count / total
            if total
            else 0.0
        )

        print(
            f"  {service}: "
            f"{count} ({percentage:.2f}%)"
        )

    print()

    if len(labels) == 1:
        warning(
            "Une seule classe est présente. "
            "Un modèle supervisé ne pourra pas apprendre "
            "une frontière meaningful/non-meaningful."
        )

    elif total > 0:

        minority = min(labels.values())

        minority_ratio = minority / total

        if minority_ratio < 0.10:
            warning(
                "Forte asymétrie des classes : "
                "la classe minoritaire représente moins de 10% "
                "des observations."
            )


# ============================================================================
# DIVERSITÉ DES SESSIONS
# ============================================================================

def audit_session_diversity(
    session_data: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    combinations: Counter[
        tuple[
            Any,
            Any,
            Any,
            Any,
            Any,
            Any,
        ]
    ] = Counter()

    for session_id, data in session_data.items():

        config = data.get("config")

        if not isinstance(config, dict):
            continue

        network = config.get(
            "network",
            {}
        )

        application = config.get(
            "application",
            {}
        )

        users = config.get(
            "users",
            {}
        )

        key = (
            network.get("bandwidth"),
            network.get("latency"),
            network.get("jitter"),
            network.get("packet_loss"),
            application.get("service_type"),
            users.get("concurrent_users"),
        )

        combinations[key] += 1

    print_section("DIVERSITÉ DES SESSIONS")

    print(
        f"Combinaisons de paramètres distinctes : "
        f"{len(combinations)}"
    )

    if combinations:

        most_common = combinations.most_common(5)

        print("Combinaisons les plus répétées :")

        for combination, count in most_common:

            print(
                f"  {count}× "
                f"BW={combination[0]}, "
                f"lat={combination[1]}, "
                f"jitter={combination[2]}, "
                f"loss={combination[3]}, "
                f"service={combination[4]}, "
                f"users={combination[5]}"
            )

        max_count = most_common[0][1]

        if max_count >= max(
            5,
            len(session_data) * 0.20,
        ):
            warnings.append(
                "Une combinaison de paramètres réseau "
                "est fortement surreprésentée."
            )

    return errors, warnings


# ============================================================================
# ANALYSE DES PARAMÈTRES
# ============================================================================

def parameter_statistics(
    rows: list[dict[str, str]],
) -> None:
    print_section("DISTRIBUTION DES FEATURES")

    numeric_fields = [
        "bandwidth",
        "latency",
        "jitter",
        "packet_loss",
        "resource_size_mb",
        "concurrent_users",
    ]

    for field in numeric_fields:

        values = []

        for row in rows:

            value = safe_float(
                row.get(field)
            )

            if value is not None and math.isfinite(value):
                values.append(value)

        if not values:
            continue

        print(
            f"{field:20s} "
            f"min={min(values):.3f} "
            f"max={max(values):.3f} "
            f"mean={statistics.mean(values):.3f} "
            f"median={statistics.median(values):.3f}"
        )


# ============================================================================
# AUDIT DES SPLITS POTENTIELS
# ============================================================================

def audit_grouping(
    rows: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    rows_per_session: Counter[str] = Counter(
        row.get("session_id", "").strip()
        for row in rows
    )

    if rows_per_session:

        counts = list(
            rows_per_session.values()
        )

        print_section("STRUCTURE SESSION → OBSERVATIONS")

        print(
            f"Observations/session : "
            f"min={min(counts)}, "
            f"max={max(counts)}, "
            f"moyenne={statistics.mean(counts):.2f}"
        )

        if len(rows_per_session) > 1:

            if len(set(counts)) > 1:
                info(
                    "Le nombre d'observations varie entre sessions."
                )

    return errors, warnings


# ============================================================================
# RAPPORT GLOBAL
# ============================================================================

def quality_score(
    errors: list[str],
    warnings: list[str],
    rows: list[dict[str, str]],
    sessions: list[Path],
) -> None:

    print_section("ÉVALUATION GLOBALE")

    n_errors = len(errors)
    n_warnings = len(warnings)

    print(f"Erreurs détectées   : {n_errors}")
    print(f"Avertissements      : {n_warnings}")
    print(f"Observations        : {len(rows)}")
    print(f"Sessions            : {len(sessions)}")

    print()

    if n_errors == 0:

        if n_warnings == 0:

            print(
                "🟢 DATASET COHÉRENT"
            )

            print(
                "Aucune incohérence structurelle ou "
                "applicative détectée par cet audit."
            )

        else:

            print(
                "🟢 DATASET STRUCTURELLEMENT COHÉRENT"
            )

            print(
                f"{n_warnings} avertissement(s) "
                "nécessitent néanmoins une inspection."
            )

    elif n_errors <= 5:

        print(
            "🟠 DATASET À INSPECTER"
        )

        print(
            "Quelques incohérences ont été détectées. "
            "Elles doivent être comprises avant "
            "l'entraînement du modèle."
        )

    else:

        print(
            "🔴 DATASET NON FIABLE EN L'ÉTAT"
        )

        print(
            "Des incohérences importantes empêchent "
            "de considérer le dataset comme propre."
        )

    print()
    print(
        "IMPORTANT : cet audit vérifie la cohérence "
        "interne et la qualité expérimentale du dataset."
    )

    print(
        "Il ne constitue pas une preuve statistique que "
        "le dataset généralisera correctement à des "
        "conditions réseau réelles."
    )


# ============================================================================
# AFFICHAGE DES ERREURS
# ============================================================================

def print_findings(
    errors: list[str],
    warnings: list[str],
) -> None:

    if errors:

        print_section(
            f"ERREURS — {len(errors)}"
        )

        for item in errors:
            print(f"✗ {item}")

    if warnings:

        print_section(
            f"AVERTISSEMENTS — {len(warnings)}"
        )

        for item in warnings:
            print(f"⚠ {item}")


# ============================================================================
# MAIN AUDIT
# ============================================================================

def audit_dataset(
    dataset_root: Path,
) -> int:

    print_header(
        "AUDIT DATASET — MEANINGFUL CONNECTIVITY"
    )

    print(
        f"Dataset : {dataset_root.resolve()}"
    )

    dataset_csv = (
        dataset_root / "dataset.csv"
    )

    logs_dir = (
        dataset_root / "logs"
    )

    all_errors: list[str] = []
    all_warnings: list[str] = []

    # ------------------------------------------------------------------
    # 1. CSV
    # ------------------------------------------------------------------

    print_section("1. CHARGEMENT DU DATASET CSV")

    rows, errors, warnings = load_dataset_csv(
        dataset_csv
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if rows:
        ok(
            f"{len(rows)} observations chargées"
        )

    # ------------------------------------------------------------------
    # 2. STRUCTURE CSV
    # ------------------------------------------------------------------

    print_section("2. AUDIT DE STRUCTURE DU CSV")

    errors, warnings = audit_csv_structure(
        rows
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok("Structure CSV cohérente")

    # ------------------------------------------------------------------
    # 3. VALEURS CSV
    # ------------------------------------------------------------------

    print_section("3. AUDIT DES VALEURS")

    errors, warnings = audit_csv_values(
        rows
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok("Valeurs CSV valides")

    # ------------------------------------------------------------------
    # 4. SESSIONS
    # ------------------------------------------------------------------

    print_section("4. DÉCOUVERTE DES SESSIONS")

    sessions, errors, warnings = discover_sessions(
        logs_dir
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    ok(
        f"{len(sessions)} sessions découvertes"
    )

    # ------------------------------------------------------------------
    # 5. FICHIERS
    # ------------------------------------------------------------------

    print_section("5. AUDIT DES FICHIERS DE SESSION")

    session_data, errors, warnings = audit_session_files(
        sessions
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok(
            "Tous les fichiers requis sont présents "
            "et lisibles"
        )

    # ------------------------------------------------------------------
    # 6. CONFIG
    # ------------------------------------------------------------------

    print_section("6. AUDIT DES CONFIGURATIONS")

    errors, warnings = audit_configs(
        session_data
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok("Configurations cohérentes")

    # ------------------------------------------------------------------
    # 7. METRICS
    # ------------------------------------------------------------------

    print_section("7. AUDIT DES MÉTRIQUES")

    errors, warnings, metrics_summary = audit_metrics(
        session_data
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok("metrics.json cohérents")

    # ------------------------------------------------------------------
    # 8. CONFIG <-> METRICS
    # ------------------------------------------------------------------

    print_section(
        "8. COHÉRENCE CONFIG.JSON ↔ METRICS.JSON"
    )

    errors, warnings = audit_config_metrics_consistency(
        session_data,
        metrics_summary,
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok(
            "Configuration et observations "
            "sont cohérentes"
        )

    # ------------------------------------------------------------------
    # 9. CSV <-> LOGS
    # ------------------------------------------------------------------

    print_section(
        "9. COHÉRENCE DATASET.CSV ↔ LOGS"
    )

    errors, warnings = audit_csv_vs_sessions(
        rows,
        session_data,
        metrics_summary,
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok(
            "CSV et logs correspondent"
        )

    # ------------------------------------------------------------------
    # 10. LABELS
    # ------------------------------------------------------------------

    print_section(
        "10. AUDIT DES LABELS MEANINGFUL"
    )

    errors, warnings = audit_labels(
        rows,
        session_data,
        metrics_summary,
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    if not errors:
        ok(
            "Labels cohérents avec l'oracle PDF"
        )

    # ------------------------------------------------------------------
    # 11. HTTP
    # ------------------------------------------------------------------

    print_section(
        "11. AUDIT DES RÉPONSES HTTP"
    )

    errors, warnings = audit_http_errors(
        session_data,
        metrics_summary,
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # ------------------------------------------------------------------
    # 12. RESSOURCES
    # ------------------------------------------------------------------

    print_section(
        "12. AUDIT DE DISPONIBILITÉ DES RESSOURCES"
    )

    errors, warnings = audit_resource_availability(
        session_data,
        metrics_summary,
        dataset_root,
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # ------------------------------------------------------------------
    # 13. TRANSFERTS
    # ------------------------------------------------------------------

    print_section(
        "13. AUDIT DES TRANSFERTS"
    )

    errors, warnings = audit_transfers(
        metrics_summary
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # ------------------------------------------------------------------
    # 14. STATISTIQUES
    # ------------------------------------------------------------------

    dataset_statistics(rows)

    parameter_statistics(rows)

    # ------------------------------------------------------------------
    # 15. DIVERSITÉ
    # ------------------------------------------------------------------

    errors, warnings = audit_session_diversity(
        session_data
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # ------------------------------------------------------------------
    # 16. GROUPING
    # ------------------------------------------------------------------

    errors, warnings = audit_grouping(
        rows
    )

    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # ------------------------------------------------------------------
    # 17. RAPPORT FINAL
    # ------------------------------------------------------------------

    print_findings(
        all_errors,
        all_warnings,
    )

    quality_score(
        all_errors,
        all_warnings,
        rows,
        sessions,
    )

    print()

    # Retour shell :
    #
    # 0 = aucun problème
    # 1 = avertissements mais pas d'erreur
    # 2 = erreurs détectées

    if all_errors:
        return 2

    if all_warnings:
        return 1

    return 0


# ============================================================================
# CLI
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Audite la cohérence du dataset "
            "Meaningful Connectivity."
        )
    )

    parser.add_argument(
        "--dataset-dir",
        default="dataset",
        help=(
            "Répertoire contenant dataset.csv et logs/ "
            "(défaut : dataset)"
        ),
    )

    args = parser.parse_args()

    dataset_root = Path(
        args.dataset_dir
    ).resolve()

    if not dataset_root.exists():

        print(
            f"✗ Répertoire dataset introuvable : "
            f"{dataset_root}"
        )

        sys.exit(2)

    exit_code = audit_dataset(
        dataset_root
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()